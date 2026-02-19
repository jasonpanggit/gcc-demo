"""SRE Inventory Integration — bridges ResourceInventoryClient into the SRE Orchestrator.

This module provides drop-in helper functions that the SRE Orchestrator Agent
can use to:
  1. Resolve tool parameters from the resource inventory cache
  2. Perform pre-flight existence checks before tool calls
  3. Enrich parameters using the tool parameter mappings
  4. Gracefully degrade when inventory is unavailable

Usage in SREOrchestratorAgent:

    from utils.sre_inventory_integration import SREInventoryIntegration

    # In __init__()
    self.inventory_integration = SREInventoryIntegration()

    # In _prepare_tool_parameters()
    parameters = await self.inventory_integration.enrich_tool_parameters(
        tool_name, parameters, request
    )

    # In _execute_single_tool() — pre-flight check
    check = await self.inventory_integration.preflight_resource_check(
        tool_name, parameters
    )
    if not check["ok"]:
        return check["result"]
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.config import config
    from app.agentic.eol.utils.resource_inventory_client import (
        get_resource_inventory_client,
        ResourceInventoryClient,
    )
    from app.agentic.eol.utils.tool_parameter_mappings import (
        get_tool_mapping,
        get_resource_types_for_tool,
        get_inventory_populatable_params,
        resolve_parameter_from_inventory,
        build_parameter_resolution_plan,
    )
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]
    from utils.config import config
    from utils.resource_inventory_client import (
        get_resource_inventory_client,
        ResourceInventoryClient,
    )
    from utils.tool_parameter_mappings import (
        get_tool_mapping,
        get_resource_types_for_tool,
        get_inventory_populatable_params,
        resolve_parameter_from_inventory,
        build_parameter_resolution_plan,
    )


logger = get_logger(__name__)


class SREInventoryIntegration:
    """Encapsulates all inventory-related logic for the SRE Orchestrator.

    Feature-flagged via ``config.inventory.enable_inventory``.
    All methods degrade gracefully when inventory is unavailable.
    """

    def __init__(self, strict_mode: bool = False) -> None:
        """Initialize SRE Inventory Integration.

        Args:
            strict_mode: If True, block tool execution when resources are not found in inventory.
                        If False (default), allow tools to proceed (handles cache lag gracefully).
        """
        self._enabled: bool = config.inventory.enable_inventory
        self._client: Optional[ResourceInventoryClient] = None
        self._strict_mode: bool = strict_mode

        # Statistics
        self._stats = {
            "preflight_checks": 0,
            "preflight_cache_hits": 0,
            "preflight_cache_misses": 0,
            "param_enrichments": 0,
            "params_resolved_from_inventory": 0,
            "params_resolved_from_env": 0,
            "fallback_to_direct": 0,
            "errors": 0,
        }

        if self._enabled:
            try:
                self._client = get_resource_inventory_client()
                mode_str = "strict mode" if self._strict_mode else "graceful mode"
                logger.info(f"✅ SRE Inventory Integration initialised ({mode_str})")
            except Exception as exc:
                logger.warning(
                    "⚠️ Failed to initialise inventory client — degrading gracefully: %s", exc
                )
                self._client = None
                self._enabled = False
        else:
            logger.info("ℹ️ SRE Inventory Integration disabled via feature flag")

    @property
    def enabled(self) -> bool:
        """Whether inventory integration is active."""
        return self._enabled and self._client is not None

    # ------------------------------------------------------------------
    # Pre-flight resource existence check
    # ------------------------------------------------------------------

    async def preflight_resource_check(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check whether the target resource exists before calling a tool.

        This avoids expensive tool calls (and confusing error messages) when a
        resource clearly doesn't exist in the inventory.

        Args:
            tool_name: MCP tool name.
            parameters: Current resolved parameters.

        Returns:
            ``{"ok": True}`` if the resource exists or the check was skipped,
            ``{"ok": False, "result": <error dict>}`` with a helpful message
            if the resource is confirmed missing.
        """
        if not self.enabled:
            return {"ok": True}

        self._stats["preflight_checks"] += 1

        # Only check tools that require a specific resource_id
        mapping = get_tool_mapping(tool_name)
        if not mapping:
            return {"ok": True}

        resource_types = get_resource_types_for_tool(tool_name)
        if not resource_types:
            return {"ok": True}  # Subscription-scoped tool, no resource check needed

        resource_id = parameters.get("resource_id")
        if not resource_id:
            return {"ok": True}  # No resource_id to validate

        # Extract resource type from the resource_id path
        resource_type = self._extract_resource_type(resource_id)
        if not resource_type:
            return {"ok": True}  # Can't determine type, skip check

        # Check existence in inventory
        try:
            # Prefer exact resource_id lookup first to avoid false negatives
            # when name/type extraction is lossy (nested resources, case differences).
            exact_match = await self._lookup_resource_by_id(resource_id)
            if exact_match:
                self._stats["preflight_cache_hits"] += 1
                logger.debug("Pre-flight exact ID match for %s (tool: %s)", resource_id, tool_name)
                return {"ok": True}

            exists = await self._client.check_resource_exists(
                resource_type,
                filters={"name": self._extract_resource_name(resource_id)},
            )

            if exists:
                self._stats["preflight_cache_hits"] += 1
                logger.debug("Pre-flight check passed for %s (tool: %s)", resource_id, tool_name)
                return {"ok": True}

            self._stats["preflight_cache_misses"] += 1
            logger.debug(
                "Pre-flight check: resource not found in inventory for %s (tool: %s)",
                resource_id, tool_name,
            )

            # Resource not in inventory — behavior depends on strict_mode
            if self._strict_mode:
                # Strict mode: Block tool execution if resource not found
                resource_name = self._extract_resource_name(resource_id)
                return {
                    "ok": False,
                    "result": {
                        "success": False,
                        "error": f"Resource '{resource_name}' not found in inventory",
                        "suggestion": "Verify the resource exists and inventory is up-to-date. Run resource discovery or provide a valid resource ID.",
                        "resource_id": resource_id,
                        "resource_type": resource_type
                    }
                }
            else:
                # Graceful mode: Allow tool to proceed (handles cache lag)
                logger.debug("Graceful mode: allowing tool execution despite cache miss")
                return {"ok": True}

        except Exception as exc:
            self._stats["errors"] += 1
            logger.warning("Pre-flight existence check failed for %s: %s", resource_id, exc)
            return {"ok": True}  # Don't block on inventory errors

    # ------------------------------------------------------------------
    # Parameter enrichment from inventory
    # ------------------------------------------------------------------

    async def enrich_tool_parameters(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Enrich tool parameters from the resource inventory.

        Resolution order (first wins):
            1. Already-provided parameters
            2. Inventory cache lookups (via tool parameter mappings)
            3. Environment variable fallbacks
            4. Mapping defaults

        Args:
            tool_name: MCP tool name.
            parameters: Existing parameters (not mutated).
            request: Original request context (optional).

        Returns:
            Enriched copy of parameters.
        """
        if not self.enabled:
            return parameters

        self._stats["param_enrichments"] += 1

        enriched = dict(parameters)

        # Step 1: Use ResourceInventoryClient.resolve_tool_parameters() for
        #         name→resource_group resolution and subscription defaults
        try:
            enriched = await self._client.resolve_tool_parameters(tool_name, enriched)
        except Exception as exc:
            self._stats["errors"] += 1
            logger.warning("Inventory resolve_tool_parameters failed for %s: %s", tool_name, exc)
            self._stats["fallback_to_direct"] += 1

        # Step 2: Use TOOL_PARAMETER_MAPPINGS to fill remaining gaps
        populatable = get_inventory_populatable_params(tool_name)
        for param in populatable:
            if param.name in enriched and enriched[param.name]:
                continue  # Already resolved

            # Try inventory lookup if we have a resource_id
            resource_id = enriched.get("resource_id")
            if resource_id and param.inventory_field:
                inventory_resource = await self._lookup_resource_by_id(resource_id)
                if inventory_resource:
                    value = resolve_parameter_from_inventory(param, inventory_resource)
                    if value is not None:
                        enriched[param.name] = value
                        self._stats["params_resolved_from_inventory"] += 1
                        logger.debug(
                            "Resolved %s='%s' from inventory for tool %s",
                            param.name, value, tool_name,
                        )

        # Step 3: Environment variable fallbacks for still-missing params
        mapping = get_tool_mapping(tool_name)
        if mapping:
            for param in mapping.parameters:
                if param.name in enriched and enriched[param.name]:
                    continue
                if param.env_var:
                    env_val = os.getenv(param.env_var)
                    if env_val:
                        enriched[param.name] = env_val
                        self._stats["params_resolved_from_env"] += 1
                        logger.debug(
                            "Resolved %s from env var %s for tool %s",
                            param.name, param.env_var, tool_name,
                        )
                # Apply defaults
                if param.name not in enriched and param.default is not None:
                    enriched[param.name] = param.default

        return enriched

    # ------------------------------------------------------------------
    # Resource discovery for tool context
    # ------------------------------------------------------------------

    async def discover_resources_for_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Discover applicable resources for a tool from inventory.

        Uses the tool's declared resource_types to query the inventory.
        Returns resources sorted by relevance (name match first if query
        context provides a name hint).

        Args:
            tool_name: MCP tool name.
            parameters: Current parameters (may contain resource_group, name hints).

        Returns:
            List of matching inventory resources (may be empty).
        """
        if not self.enabled:
            return []

        resource_types = get_resource_types_for_tool(tool_name)
        if not resource_types:
            return []

        all_matches: List[Dict[str, Any]] = []
        filters: Dict[str, Any] = {}

        # Apply resource_group filter if available
        rg = parameters.get("resource_group")
        if rg:
            filters["resource_group"] = rg

        for resource_type in resource_types:
            try:
                resources = await self._client.get_resources(
                    resource_type,
                    filters=filters if filters else None,
                )
                all_matches.extend(resources)
            except Exception as exc:
                logger.debug("Discovery for %s failed: %s", resource_type, exc)

        return all_matches

    # ------------------------------------------------------------------
    # Statistics & diagnostics
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
        """Return integration statistics for monitoring dashboards."""
        stats = dict(self._stats)
        stats["enabled"] = self.enabled
        stats["client_available"] = self._client is not None
        if self._client:
            stats["client_stats"] = self._client.get_statistics()
        return stats

    def get_resolution_plan(
        self,
        tool_name: str,
        provided_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyse what can be resolved for a tool (diagnostic helper).

        Returns a breakdown of resolved / from_inventory / from_env / missing.
        """
        return build_parameter_resolution_plan(tool_name, provided_params)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _lookup_resource_by_id(
        self,
        resource_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Look up a single resource from inventory by its full ID."""
        if not self._client:
            return None

        resource_type = self._extract_resource_type(resource_id)
        resource_name = self._extract_resource_name(resource_id)

        if not resource_type or not resource_name:
            return None

        try:
            matches = await self._client.get_resource_by_name(
                resource_name,
                resource_type=resource_type,
            )
            target_id = resource_id.rstrip("/").lower()
            # Return exact ID match if found
            for m in matches:
                candidate_resource_id = str(m.get("resource_id") or "").rstrip("/").lower()
                candidate_id = str(m.get("id") or "").rstrip("/").lower()
                if candidate_resource_id == target_id or candidate_id == target_id:
                    return m
            # Otherwise return first match
            return matches[0] if matches else None
        except Exception:
            return None

    @staticmethod
    def _extract_resource_type(resource_id: str) -> Optional[str]:
        """Extract Azure resource type from a resource ID path."""
        parts = resource_id.split("/")
        try:
            provider_idx = next(
                i for i, p in enumerate(parts) if p.lower() == "providers"
            )
            if provider_idx + 2 < len(parts):
                return f"{parts[provider_idx + 1]}/{parts[provider_idx + 2]}"
        except (StopIteration, IndexError):
            pass
        return None

    @staticmethod
    def _extract_resource_name(resource_id: str) -> Optional[str]:
        """Extract the resource name (last segment) from a resource ID."""
        parts = resource_id.rstrip("/").split("/")
        return parts[-1] if parts else None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_integration: Optional[SREInventoryIntegration] = None


def get_sre_inventory_integration(strict_mode: bool = False) -> SREInventoryIntegration:
    """Get or create the SREInventoryIntegration singleton.

    Args:
        strict_mode: If True, block tool execution when resources not found in inventory.
                    If False (default), allow graceful fallback.

    Returns:
        SREInventoryIntegration instance.
    """
    global _integration
    if _integration is None:
        _integration = SREInventoryIntegration(strict_mode=strict_mode)
    return _integration
