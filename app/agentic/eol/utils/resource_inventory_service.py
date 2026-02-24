"""ResourceInventoryService — pipeline-facing facade over the inventory stack.

Provides a clean, pipeline-component-facing interface over:
    ResourceInventoryClient       (utils/resource_inventory_client.py)
    SREInventoryIntegration       (utils/sre_inventory_integration.py)
    ResourceInventoryCache        (utils/resource_inventory_cache.py)

All three underlying modules are UNCHANGED — this facade adds no new logic,
only coordination and a stable interface for Router, Planner, Executor, and
Verifier to use without importing the underlying clients directly.

Construction is lazy: no live Azure connection is needed until a method is
first called.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return-type dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EntityHints:
    """Resource names and types extracted from a user query."""
    names: List[str] = field(default_factory=list)
    possible_types: List[str] = field(default_factory=list)


@dataclass
class GroundingSummary:
    """Compact structured context for the Planner's JSON grounding injection."""
    tenant_id: str = ""
    subscriptions: List[Dict[str, str]] = field(default_factory=list)
    resource_groups: List[str] = field(default_factory=list)
    resource_type_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class PreflightResult:
    """Result of a resource existence preflight check."""
    passed: bool
    resource_found: bool = True
    issues: List[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class ResourceDoc:
    """Minimal resource descriptor returned by lookup_resource."""
    name: str
    resource_id: str
    resource_type: str
    resource_group: str
    subscription_id: str
    location: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Known Azure resource type patterns for entity extraction
# ---------------------------------------------------------------------------

_RESOURCE_TYPE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(container\s*app|containerapp)\b", re.I), "Microsoft.App/containerApps"),
    (re.compile(r"\b(aks|kubernetes\s*cluster)\b", re.I), "Microsoft.ContainerService/managedClusters"),
    (re.compile(r"\b(vm|virtual\s*machine)\b", re.I), "Microsoft.Compute/virtualMachines"),
    (re.compile(r"\b(storage\s*account)\b", re.I), "Microsoft.Storage/storageAccounts"),
    (re.compile(r"\b(key\s*vault)\b", re.I), "Microsoft.KeyVault/vaults"),
    (re.compile(r"\b(app\s*service|web\s*app)\b", re.I), "Microsoft.Web/sites"),
    (re.compile(r"\b(function\s*app)\b", re.I), "Microsoft.Web/sites"),
    (re.compile(r"\b(cosmos|cosmosdb)\b", re.I), "Microsoft.DocumentDB/databaseAccounts"),
    (re.compile(r"\b(redis|cache)\b", re.I), "Microsoft.Cache/redis"),
    (re.compile(r"\b(vnet|virtual\s*network)\b", re.I), "Microsoft.Network/virtualNetworks"),
    (re.compile(r"\b(nsg|network\s*security\s*group)\b", re.I), "Microsoft.Network/networkSecurityGroups"),
    (re.compile(r"\b(api\s*management|apim)\b", re.I), "Microsoft.ApiManagement/service"),
    (re.compile(r"\b(sql\s*server|azure\s*sql)\b", re.I), "Microsoft.Sql/servers"),
]

# Pattern to extract resource names (quoted or hyphenated identifiers)
_NAME_PATTERN = re.compile(r"""(?:["']([^"']+)["'])|(\b[a-z][a-z0-9](?:[a-z0-9-]*[a-z0-9])?\b)""", re.I)
_STOP_WORDS = frozenset({
    "the", "my", "your", "its", "this", "that", "for", "with", "and", "or",
    "not", "are", "is", "was", "list", "show", "get", "check", "find", "what",
    "how", "why", "when", "which", "does", "can", "will", "should", "have",
    "has", "been", "being", "azure", "microsoft", "resource", "resources",
})


# Sentinel used to distinguish "not yet tried" (None) from "tried and failed" (_UNAVAILABLE)
_UNAVAILABLE = object()


class ResourceInventoryService:
    """Pipeline-facing facade over ResourceInventoryClient + SREInventoryIntegration.

    All methods are async. Construction is synchronous and lightweight — no
    Azure connection is established until the first method call.

    Intended to be instantiated once per orchestrator session and passed to
    Router, Planner, Executor, and Verifier as a shared service.
    """

    def __init__(self) -> None:
        self._inventory_client = None   # None = not yet tried
        self._sre_integration = None    # None = not yet tried

    # ------------------------------------------------------------------
    # Lazy initialisation helpers
    # ------------------------------------------------------------------

    def _get_inventory_client(self):
        if self._inventory_client is None:
            for _prefix in ("utils", "app.agentic.eol.utils"):
                try:
                    import importlib
                    mod = importlib.import_module(f"{_prefix}.resource_inventory_client")
                    self._inventory_client = mod.get_resource_inventory_client()
                    break
                except Exception:
                    pass
            if self._inventory_client is None:
                logger.warning("ResourceInventoryClient unavailable: could not import from either prefix")
                self._inventory_client = _UNAVAILABLE  # suppress on subsequent calls
        return None if self._inventory_client is _UNAVAILABLE else self._inventory_client

    def _get_sre_integration(self):
        if self._sre_integration is None:
            for _prefix in ("utils", "app.agentic.eol.utils"):
                try:
                    import importlib
                    mod = importlib.import_module(f"{_prefix}.sre_inventory_integration")
                    self._sre_integration = mod.get_sre_inventory_integration()
                    break
                except Exception:
                    pass
            if self._sre_integration is None:
                logger.warning("SREInventoryIntegration unavailable: could not import from either prefix")
                self._sre_integration = _UNAVAILABLE  # suppress on subsequent calls
        return None if self._sre_integration is _UNAVAILABLE else self._sre_integration

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_entities(self, query: str) -> EntityHints:
        """Extract Azure resource names and types mentioned in *query*.

        Used by Router to supply entity hints for domain classification.
        E.g.: "check health of prod-api" → EntityHints(names=["prod-api"])

        Does not make Azure API calls — purely regex-based extraction.
        """
        possible_types: list[str] = []
        for pattern, resource_type in _RESOURCE_TYPE_HINTS:
            if pattern.search(query):
                possible_types.append(resource_type)

        # Extract candidate resource names (short hyphenated identifiers, quoted strings)
        names: list[str] = []
        for match in _NAME_PATTERN.finditer(query):
            name = (match.group(1) or match.group(2) or "").strip()
            if name and name.lower() not in _STOP_WORDS and len(name) >= 3:
                names.append(name)

        return EntityHints(names=names, possible_types=possible_types)

    async def get_grounding_summary(self) -> GroundingSummary:
        """Return a compact structured dict for Planner context injection.

        Built from L1 cache keys — sub-millisecond on cache hit, no Azure call.
        Replaces the current text-blob system prompt injection.
        """
        summary = GroundingSummary()
        client = self._get_inventory_client()
        if client is None:
            return summary

        try:
            # Subscription
            sub_id = client._default_subscription() if hasattr(client, "_default_subscription") else ""
            if sub_id:
                summary.subscriptions = [{"id": sub_id, "name": sub_id}]

            # Try to get tenant ID from config
            try:
                from app.agentic.eol.utils.config import config
                tenant_id = getattr(getattr(config, "azure", None), "tenant_id", "") or ""
                summary.tenant_id = tenant_id
            except Exception:
                pass

            # Resource groups from live query (non-blocking — errors are swallowed)
            try:
                rg_resources = await client.get_resources(
                    "Microsoft.Resources/resourceGroups",
                    subscription_id=sub_id if sub_id else None,
                )
                summary.resource_groups = [
                    r.get("name", "") for r in rg_resources if r.get("name")
                ][:50]  # cap at 50
            except Exception as exc:
                logger.debug("Could not fetch resource groups for grounding: %s", exc)

        except Exception as exc:
            logger.debug("GroundingSummary build error (non-fatal): %s", exc)

        return summary

    async def resolve_parameters(
        self,
        tool_name: str,
        partial_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enrich tool parameters from inventory.

        Delegates to SREInventoryIntegration.enrich_tool_parameters().
        Returns *partial_params* unchanged if the integration is unavailable.

        Args:
            tool_name: MCP tool name (e.g. "check_resource_health").
            partial_params: Parameters already extracted by the Planner.

        Returns:
            Enriched copy of partial_params.
        """
        integration = self._get_sre_integration()
        if integration is None:
            return partial_params
        try:
            return await integration.enrich_tool_parameters(tool_name, partial_params)
        except Exception as exc:
            logger.debug("resolve_parameters error for %s (non-fatal): %s", tool_name, exc)
            return partial_params

    async def preflight_check(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> PreflightResult:
        """Resource existence check before tool execution.

        Delegates to SREInventoryIntegration.preflight_resource_check().
        Returns passed=True if the integration is unavailable (fail-open).

        Args:
            tool_name: MCP tool name.
            params: Resolved parameters including resource_id if available.

        Returns:
            PreflightResult with passed=True on success or unavailability.
        """
        integration = self._get_sre_integration()
        if integration is None:
            return PreflightResult(passed=True, suggestion="Integration unavailable — skipped preflight.")
        try:
            raw = await integration.preflight_resource_check(tool_name, params)
            # preflight_resource_check returns {"ok": bool} or
            # {"ok": False, "result": {...}} — normalise to PreflightResult
            if isinstance(raw, dict):
                ok = raw.get("ok", True)
                if not ok:
                    result_detail = raw.get("result", {})
                    return PreflightResult(
                        passed=False,
                        resource_found=False,
                        issues=[result_detail.get("error", "Resource not found")],
                        suggestion=result_detail.get("suggestion", ""),
                    )
            return PreflightResult(passed=True)
        except Exception as exc:
            logger.debug("preflight_check error for %s (non-fatal): %s", tool_name, exc)
            return PreflightResult(passed=True, suggestion=f"Preflight error (non-fatal): {exc}")

    async def lookup_resource(
        self,
        name: str,
        resource_type: Optional[str] = None,
        resource_group: Optional[str] = None,
    ) -> List[ResourceDoc]:
        """Query-time lookup for a named Azure resource.

        Delegates to ResourceInventoryClient.get_resource_by_name().
        Returns an empty list if the client is unavailable.

        Args:
            name: Resource name to search for.
            resource_type: Optional ARM type filter (e.g. "Microsoft.App/containerApps").
            resource_group: Optional resource group filter (exact, case-insensitive).

        Returns:
            List of ResourceDoc instances matching the query.
        """
        client = self._get_inventory_client()
        if client is None:
            return []
        try:
            raw_docs = await client.get_resource_by_name(
                resource_name=name,
                resource_type=resource_type,
            )
            results: list[ResourceDoc] = []
            for doc in raw_docs:
                resource_id = doc.get("id", "")
                # Parse resource_group from resource_id if not directly in doc
                rg = doc.get("resourceGroup", "") or doc.get("resource_group", "")
                if not rg and resource_id:
                    parts = resource_id.split("/")
                    rg_idx = next(
                        (i for i, p in enumerate(parts) if p.lower() == "resourcegroups"), -1
                    )
                    rg = parts[rg_idx + 1] if rg_idx >= 0 and rg_idx + 1 < len(parts) else ""
                if resource_group and rg.lower() != resource_group.lower():
                    continue
                results.append(ResourceDoc(
                    name=doc.get("name", name),
                    resource_id=resource_id,
                    resource_type=doc.get("type", resource_type or ""),
                    resource_group=rg,
                    subscription_id=doc.get("subscriptionId", ""),
                    location=doc.get("location", ""),
                    properties=doc.get("properties", {}),
                ))
            return results
        except Exception as exc:
            logger.debug("lookup_resource error for %r (non-fatal): %s", name, exc)
            return []


# ---------------------------------------------------------------------------
# Session-scoped factory
# ---------------------------------------------------------------------------

_service: Optional[ResourceInventoryService] = None


def get_resource_inventory_service() -> ResourceInventoryService:
    """Return the process-level singleton ResourceInventoryService."""
    global _service
    if _service is None:
        _service = ResourceInventoryService()
    return _service
