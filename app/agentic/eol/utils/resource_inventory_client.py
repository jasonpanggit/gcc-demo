"""
Resource Inventory Client - High-level API for agents to query Azure resource inventory.

Provides a clean interface on top of ResourceInventoryCache and
ResourceDiscoveryEngine so that agents and routers can:
  - Check if a resource exists (fast L1 cache path)
  - Query resources by type with filters
  - Look up resources by name (with collision handling)
  - Auto-populate missing tool parameters from cached inventory
  - Retrieve resource dependency relationships

Usage::

    from utils.resource_inventory_client import get_resource_inventory_client

    client = get_resource_inventory_client()
    vms = await client.get_resources("Microsoft.Compute/virtualMachines", subscription_id="...")
    exists = await client.check_resource_exists("Microsoft.Compute/virtualMachines",
                                                 filters={"name": "my-vm"})
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ImportError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

from .config import config
from .resource_inventory_cache import get_resource_inventory_cache, ResourceInventoryCache

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _matches_filters(resource: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Return True if *resource* satisfies all *filters*.

    Supported filter keys:
        - ``name`` / ``resource_name``  — case-insensitive substring
        - ``resource_group``            — case-insensitive exact
        - ``location``                  — case-insensitive exact
        - ``tags``                      — dict; all specified tags must match
        - ``properties``                — dict; dot-notation check on selected_properties
    """
    for key, expected in filters.items():
        if key in ("name", "resource_name"):
            actual = resource.get("resource_name") or resource.get("name", "")
            if expected.lower() not in actual.lower():
                return False

        elif key == "resource_group":
            actual = resource.get("resource_group") or resource.get("resourceGroup", "")
            if actual.lower() != expected.lower():
                return False

        elif key == "location":
            actual = resource.get("location", "")
            if actual.lower() != expected.lower():
                return False

        elif key == "tags" and isinstance(expected, dict):
            res_tags = resource.get("tags") or {}
            for tk, tv in expected.items():
                if res_tags.get(tk) != tv:
                    return False

        elif key == "properties" and isinstance(expected, dict):
            sel = resource.get("selected_properties") or resource.get("properties") or {}
            for pk, pv in expected.items():
                if sel.get(pk) != pv:
                    return False

    return True


# ---------------------------------------------------------------------------
# ResourceInventoryClient
# ---------------------------------------------------------------------------

class ResourceInventoryClient:
    """High-level, agent-friendly API for Azure resource inventory lookups.

    Integrates with:
        - :class:`ResourceInventoryCache` for fast dual-layer caching
        - :class:`ResourceDiscoveryEngine` for live Azure queries on cache miss
    """

    def __init__(self, cache: Optional[ResourceInventoryCache] = None) -> None:
        self._cache = cache or get_resource_inventory_cache()
        self._engine: Any = None  # lazily imported / initialised

    # -- engine (lazy) -------------------------------------------------------

    def _get_engine(self):
        """Lazily import and create a ResourceDiscoveryEngine."""
        if self._engine is not None:
            return self._engine
        try:
            from .resource_discovery_engine import ResourceDiscoveryEngine
            self._engine = ResourceDiscoveryEngine()
            return self._engine
        except Exception as exc:
            logger.warning("ResourceDiscoveryEngine unavailable: %s", exc)
            return None

    def _default_subscription(self) -> str:
        """Resolve the default subscription from config / environment."""
        sub = getattr(config.azure, "subscription_id", None)
        return sub or os.getenv("AZURE_SUBSCRIPTION_ID", "")

    # =====================================================================
    # Public API
    # =====================================================================

    async def check_resource_exists(
        self,
        resource_type: str,
        filters: Optional[Dict[str, Any]] = None,
        subscription_id: Optional[str] = None,
    ) -> bool:
        """Fast existence check (targets < 1 ms on L1 cache hit).

        Args:
            resource_type: Azure resource type (e.g. ``Microsoft.Compute/virtualMachines``).
            filters: Optional filter criteria (name, resource_group, location, tags, properties).
            subscription_id: Subscription to search (defaults to config).

        Returns:
            ``True`` if at least one matching resource exists in cache.
        """
        sub = subscription_id or self._default_subscription()
        if not sub:
            return False

        resources = await self._cache.get(sub, resource_type)
        if resources is None:
            return False

        if not filters:
            return len(resources) > 0

        return any(_matches_filters(r, filters) for r in resources)

    async def get_resources(
        self,
        resource_type: str,
        subscription_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Query resources by type with optional filters.

        On cache miss (or when *refresh* is True) the client will attempt a
        live discovery via the ResourceDiscoveryEngine and cache the results.

        Args:
            resource_type: Azure resource type string.
            subscription_id: Target subscription (defaults to config).
            filters: Filter criteria applied client-side.
            refresh: Force a live discovery even if cache is populated.

        Returns:
            List of matching resource documents (may be empty).
        """
        sub = subscription_id or self._default_subscription()
        if not sub:
            logger.warning("No subscription_id available for get_resources")
            return []

        # Check cache first (unless forced refresh)
        resources: Optional[List[Dict[str, Any]]] = None
        if not refresh:
            resources = await self._cache.get(sub, resource_type)

        # Live discovery fallback
        if resources is None:
            engine = self._get_engine()
            if engine:
                try:
                    discovered = await engine.full_resource_discovery(
                        sub, resource_types=[resource_type],
                    )
                    await self._cache.set(sub, resource_type, discovered)
                    resources = discovered
                except Exception as exc:
                    logger.warning(
                        "Live discovery failed for %s in %s: %s",
                        resource_type, sub, exc,
                    )
                    resources = []
            else:
                resources = []

        # Apply client-side filters
        if filters:
            resources = [r for r in resources if _matches_filters(r, filters)]

        return resources

    async def get_resource_by_name(
        self,
        resource_name: str,
        resource_type: Optional[str] = None,
        subscription_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Look up resources by name.

        Returns a list because multiple resources can share the same display
        name (different resource groups, subscriptions, etc.).  Callers should
        inspect the list length:
            - 0 → not found
            - 1 → unambiguous match
            - 2+ → collision; present options to the user / agent

        Args:
            resource_name: The display name to search for (case-insensitive).
            resource_type: Optional type to narrow the search.
            subscription_id: Target subscription (defaults to config).

        Returns:
            List of matching resource documents.
        """
        sub = subscription_id or self._default_subscription()
        if not sub:
            return []

        name_filter = {"name": resource_name}
        matches: List[Dict[str, Any]] = []

        if resource_type:
            matches = await self.get_resources(resource_type, sub, filters=name_filter)
        else:
            # Scan all cached resource types
            # We check L1 keys that match the subscription prefix
            cache = self._cache
            prefix = f"resource_inv:{sub}:"
            candidate_types: List[str] = []
            with cache._l1_lock:
                for key in cache._l1:
                    if key.startswith(prefix):
                        parts = key.split(":")
                        if len(parts) >= 3:
                            rtype = parts[2]
                            if rtype not in candidate_types:
                                candidate_types.append(rtype)

            for rtype in candidate_types:
                rmatches = await self.get_resources(rtype, sub, filters=name_filter)
                matches.extend(rmatches)

        if len(matches) > 1:
            logger.info(
                "Name collision for '%s': %d matches found — caller should disambiguate",
                resource_name, len(matches),
            )

        return matches

    async def resolve_tool_parameters(
        self,
        tool_name: str,
        partial_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Auto-populate missing parameters from cached inventory.

        Inspects the parameter dict for common Azure parameter patterns
        (``subscription_id``, ``resource_group``, ``resource_name``) and fills
        them from environment defaults or cached lookups when missing.

        Args:
            tool_name: SRE / MCP tool name (for logging context).
            partial_params: Parameters already provided.

        Returns:
            Enriched copy of *partial_params* (original is not mutated).
        """
        resolved = dict(partial_params)

        # -- subscription_id --
        if not resolved.get("subscription_id"):
            default_sub = self._default_subscription()
            if default_sub:
                resolved["subscription_id"] = default_sub

        # -- resource_group from resource_name --
        if resolved.get("resource_name") and not resolved.get("resource_group"):
            resource_type = resolved.get("resource_type", "")
            sub = resolved.get("subscription_id", "")
            if sub:
                matches = await self.get_resource_by_name(
                    resolved["resource_name"],
                    resource_type=resource_type or None,
                    subscription_id=sub,
                )
                if len(matches) == 1:
                    rg = matches[0].get("resource_group", "")
                    if rg:
                        resolved["resource_group"] = rg
                        logger.debug(
                            "Resolved resource_group='%s' for tool %s",
                            rg, tool_name,
                        )
                elif len(matches) > 1:
                    resolved["_disambiguation_required"] = True
                    resolved["_matches"] = [
                        {
                            "resource_name": m.get("resource_name"),
                            "resource_group": m.get("resource_group"),
                            "location": m.get("location"),
                            "resource_type": m.get("resource_type"),
                        }
                        for m in matches
                    ]
                    logger.info(
                        "Disambiguation needed for tool %s: %d candidates for '%s'",
                        tool_name, len(matches), resolved["resource_name"],
                    )

        # -- resource_group from environment fallback --
        if not resolved.get("resource_group"):
            env_rg = os.getenv("AZURE_RESOURCE_GROUP") or getattr(
                config.azure, "resource_group_name", None
            )
            if env_rg:
                resolved["resource_group"] = env_rg

        return resolved

    async def get_resource_relationships(
        self,
        resource_id: str,
        depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Retrieve dependency relationships for a resource.

        Delegates to the ResourceDiscoveryEngine relationship extractor.

        Args:
            resource_id: Full Azure resource ID.
            depth: Maximum traversal depth (default 2, capped at 2).

        Returns:
            List of relationship edges (source, target, relationship_type, depth).
        """
        engine = self._get_engine()
        if not engine:
            logger.warning("Cannot extract relationships — discovery engine unavailable")
            return []

        resource_doc = {"resource_id": resource_id}

        # Try to infer subscription_id from the resource ID
        parts = resource_id.split("/")
        if len(parts) >= 3 and parts[1].lower() == "subscriptions":
            resource_doc["subscription_id"] = parts[2]

        # Try to infer resource type
        try:
            provider_idx = next(
                i for i, p in enumerate(parts)
                if p.lower() == "providers"
            )
            if provider_idx + 2 < len(parts):
                resource_doc["resource_type"] = f"{parts[provider_idx + 1]}/{parts[provider_idx + 2]}"
        except (StopIteration, IndexError):
            pass

        try:
            return await engine.extract_relationships(resource_doc, depth=depth)
        except Exception as exc:
            logger.warning("Relationship extraction failed for %s: %s", resource_id, exc)
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """Return combined client + cache statistics."""
        return {
            "cache": self._cache.get_statistics(),
            "engine_available": self._engine is not None or self._get_engine() is not None,
            "default_subscription": self._default_subscription(),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_client: Optional[ResourceInventoryClient] = None
_client_lock = threading.Lock()


def get_resource_inventory_client() -> ResourceInventoryClient:
    """Get or create the ResourceInventoryClient singleton."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ResourceInventoryClient()
    return _client
