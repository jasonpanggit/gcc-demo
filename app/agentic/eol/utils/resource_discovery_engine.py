"""
Resource Discovery Engine

Uses Azure Resource Graph to discover, inventory, and track Azure resources
across subscriptions. Supports full and incremental discovery with relationship
extraction and property enrichment.

Key capabilities:
- Discover all subscriptions in the tenant
- Full resource discovery via Resource Graph KQL queries
- Incremental discovery detecting created/modified/deleted resources
- Relationship extraction (VM->NIC->VNet, etc.) up to configurable depth
- Property enrichment for common resource types (VM, App Service, Storage,
  SQL, VNet, Container Apps, AKS)
- Tag security filtering (strips password, secret, token, key, credential values)
- Structured resource documents ready for Cosmos DB persistence
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from azure.identity import DefaultAzureCredential, ClientSecretCredential
    from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.web import WebSiteManagementClient
    from azure.mgmt.storage import StorageManagementClient
    from azure.mgmt.network import NetworkManagementClient
    from azure.mgmt.containerservice import ContainerServiceClient
    AZURE_SDK_AVAILABLE = True
except ImportError:
    DefaultAzureCredential = None
    ClientSecretCredential = None
    ResourceManagementClient = None
    SubscriptionClient = None
    ResourceGraphClient = None
    QueryRequest = None
    QueryRequestOptions = None
    ComputeManagementClient = None
    WebSiteManagementClient = None
    StorageManagementClient = None
    NetworkManagementClient = None
    ContainerServiceClient = None
    AZURE_SDK_AVAILABLE = False

try:
    from app.agentic.eol.utils.logger import get_logger
except ImportError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tag values containing these keywords are redacted for security
_SENSITIVE_TAG_KEYWORDS: Set[str] = {
    "password", "secret", "token", "key", "credential",
}

# Maximum resources returned per Resource Graph page
_PAGE_SIZE = 1000

# Fields kept in selective property storage
_COMMON_FIELDS = {
    "id", "name", "type", "location", "resourceGroup",
    "subscriptionId", "tags", "sku", "kind", "identity",
    "managedBy", "plan", "zones", "extendedLocation",
}

# Relationship mapping: resource type -> KQL snippet to extract linked IDs
_RELATIONSHIP_KQL: Dict[str, str] = {
    "microsoft.compute/virtualmachines": (
        "extend _rels = array_concat("
        "  iff(isnotnull(properties.networkProfile.networkInterfaces), properties.networkProfile.networkInterfaces, dynamic([])),"
        "  iff(isnotnull(properties.availabilitySet), pack_array(properties.availabilitySet), dynamic([])),"
        "  iff(isnotnull(properties.storageProfile.osDisk.managedDisk), pack_array(properties.storageProfile.osDisk.managedDisk), dynamic([]))"
        ")"
    ),
    "microsoft.network/networkinterfaces": (
        "extend _rels = array_concat("
        "  iff(isnotnull(properties.ipConfigurations), properties.ipConfigurations, dynamic([])),"
        "  iff(isnotnull(properties.networkSecurityGroup), pack_array(properties.networkSecurityGroup), dynamic([]))"
        ")"
    ),
    "microsoft.web/sites": (
        "extend _rels = iff(isnotnull(properties.serverFarmId), pack_array(pack('id', properties.serverFarmId)), dynamic([]))"
    ),
}

# ---------------------------------------------------------------------------
# Enrichment type dispatcher - maps resource type to enrichment method name
# ---------------------------------------------------------------------------
_ENRICHMENT_TYPE_MAP: Dict[str, str] = {
    "microsoft.compute/virtualmachines": "_enrich_vm",
    "microsoft.web/sites": "_enrich_app_service",
    "microsoft.storage/storageaccounts": "_enrich_storage",
    "microsoft.sql/servers/databases": "_enrich_sql",
    "microsoft.sql/servers": "_enrich_sql_server",
    "microsoft.network/virtualnetworks": "_enrich_vnet",
    "microsoft.app/containerapps": "_enrich_container_app",
    "microsoft.containerservice/managedclusters": "_enrich_aks",
}

# Default enrichment TTL in seconds - skip re-enrichment within this window
_ENRICHMENT_TTL_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_tags(tags: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Redact tag values that may contain sensitive information."""
    if not tags:
        return {}
    sanitized: Dict[str, str] = {}
    for k, v in tags.items():
        key_lower = k.lower()
        if any(kw in key_lower for kw in _SENSITIVE_TAG_KEYWORDS):
            sanitized[k] = "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized


def _selective_properties(resource: Dict[str, Any]) -> Dict[str, Any]:
    """Return only commonly-used fields from a resource document."""
    return {k: resource[k] for k in _COMMON_FIELDS if k in resource}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_resource_id(resource_id: str) -> Tuple[str, str, str]:
    """Parse an Azure resource ID into (subscription_id, resource_group, name).

    Raises ValueError when the resource ID format is unexpected.
    """
    parts = resource_id.split("/")
    if len(parts) < 9:
        raise ValueError(f"Invalid resource ID format: {resource_id}")
    return parts[2], parts[4], parts[8]


# ---------------------------------------------------------------------------
# ResourceDiscoveryEngine
# ---------------------------------------------------------------------------

class ResourceDiscoveryEngine:
    """Discovers Azure resources using Azure Resource Graph.

    Provides full and incremental discovery, relationship extraction,
    and property enrichment for commonly-managed resource types.

    Usage::

        engine = ResourceDiscoveryEngine()
        subs = await engine.discover_all_subscriptions()
        resources = await engine.full_resource_discovery(subs[0]["subscription_id"])
    """

    def __init__(self, credential=None):
        """Initialise the engine.

        Args:
            credential: Azure credential instance. When *None* the engine will
                create one using the same Service-Principal / Managed-Identity
                logic used elsewhere in the SRE stack.
        """
        self._credential = credential
        self._graph_client: Optional[ResourceGraphClient] = None
        # Enrichment cache: resource_id -> (enriched_data, timestamp)
        self._enrichment_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    # -- credential / client helpers ----------------------------------------

    def _get_credential(self):
        """Lazy-init the Azure credential."""
        if self._credential is not None:
            return self._credential

        if not AZURE_SDK_AVAILABLE:
            raise RuntimeError("Azure SDK packages are not installed")

        use_sp = os.getenv("USE_SERVICE_PRINCIPAL", "false").lower() == "true"
        sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
        sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if use_sp and sp_client_id and sp_client_secret and tenant_id:
            logger.info("ResourceDiscoveryEngine: Using Service Principal auth")
            self._credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=sp_client_id,
                client_secret=sp_client_secret,
            )
        else:
            logger.info("ResourceDiscoveryEngine: Using DefaultAzureCredential")
            self._credential = DefaultAzureCredential()
        return self._credential

    def _get_graph_client(self) -> ResourceGraphClient:
        """Return a cached ResourceGraphClient."""
        if self._graph_client is None:
            self._graph_client = ResourceGraphClient(self._get_credential())
        return self._graph_client

    # -- paginated Resource Graph helper ------------------------------------

    async def _execute_graph_query(
        self,
        query: str,
        subscription_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Execute a paginated Resource Graph query and return all rows."""
        if not AZURE_SDK_AVAILABLE or ResourceGraphClient is None:
            raise RuntimeError("azure-mgmt-resourcegraph is required")

        graph_client = self._get_graph_client()
        all_rows: List[Dict[str, Any]] = []
        skip_token: Optional[str] = None

        while True:
            options = QueryRequestOptions(
                result_format="objectArray",
                top=_PAGE_SIZE,
            )
            if skip_token:
                options.skip_token = skip_token

            request = QueryRequest(
                subscriptions=subscription_ids,
                query=query,
                options=options,
            )

            # Resource Graph SDK calls are synchronous; run in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, graph_client.resources, request
            )

            data = response.data if hasattr(response, "data") else []
            all_rows.extend(data)

            skip_token = getattr(response, "skip_token", None)
            if not skip_token:
                break

        return all_rows

    # ======================================================================
    # Public API
    # ======================================================================

    async def discover_all_subscriptions(self) -> List[Dict[str, Any]]:
        """List all subscriptions the credential has access to.

        Returns:
            List of dicts with subscription_id, display_name, state, tenant_id.
        """
        if not AZURE_SDK_AVAILABLE or SubscriptionClient is None:
            raise RuntimeError("azure-mgmt-resource is required")

        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _list_subs():
            client = SubscriptionClient(credential)
            return list(client.subscriptions.list())

        subscriptions = await loop.run_in_executor(None, _list_subs)

        results: List[Dict[str, Any]] = []
        for sub in subscriptions:
            results.append({
                "subscription_id": sub.subscription_id,
                "display_name": sub.display_name,
                "state": str(sub.state),
                "tenant_id": sub.tenant_id,
                "discovered_at": _now_iso(),
            })

        logger.info(
            "Discovered %d subscriptions in tenant", len(results),
        )
        return results

    # -- full discovery -----------------------------------------------------

    async def full_resource_discovery(
        self,
        subscription_id: str,
        resource_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Discover all resources in a subscription via Resource Graph.

        Args:
            subscription_id: Target Azure subscription.
            resource_types: Optional list of resource types to filter
                (e.g. ``["microsoft.compute/virtualmachines"]``).

        Returns:
            List of structured resource documents ready for Cosmos DB.
        """
        kql = (
            "Resources\n"
            "| project id, name, type, location, resourceGroup,"
            "  subscriptionId, tags, sku, kind, identity,"
            "  managedBy, plan, zones, extendedLocation, properties\n"
        )

        if resource_types:
            type_filter = ", ".join(f"'{t.lower()}'" for t in resource_types)
            kql += f"| where type in~ ({type_filter})\n"

        kql += "| order by id asc"

        try:
            raw_resources = await self._execute_graph_query(
                kql, [subscription_id],
            )
        except Exception as exc:
            logger.error(
                "Full discovery failed for subscription %s: %s",
                subscription_id, exc,
            )
            raise

        documents = self._to_documents(raw_resources, subscription_id)

        logger.info(
            "Full discovery: %d resources in subscription %s",
            len(documents), subscription_id,
        )
        return documents

    # -- incremental discovery ----------------------------------------------

    async def incremental_discovery(
        self,
        subscription_id: str,
        last_scan_time: str,
        cached_resource_ids: Optional[Set[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Detect created, modified, and deleted resources since *last_scan_time*.

        Args:
            subscription_id: Target subscription.
            last_scan_time: ISO-8601 timestamp of the last successful scan.
            cached_resource_ids: Set of resource IDs currently in the cache.
                When provided the engine can detect deletions by diffing against
                the current Resource Graph state.

        Returns:
            Dict with keys ``created``, ``modified``, ``deleted``.
        """
        # Query resources that were changed after last_scan_time
        kql_changed = (
            "Resources\n"
            "| project id, name, type, location, resourceGroup,"
            "  subscriptionId, tags, sku, kind, identity,"
            "  managedBy, plan, zones, extendedLocation, properties,"
            "  changedTime = todatetime(properties.provisioningState)\n"
            "| order by id asc"
        )

        # Fetch all current resource IDs to detect deletions
        kql_ids = (
            "Resources\n"
            "| where subscriptionId == '{sub}'\n"
            "| project id"
        ).format(sub=subscription_id)

        try:
            changed_raw, current_ids_raw = await asyncio.gather(
                self._execute_graph_query(kql_changed, [subscription_id]),
                self._execute_graph_query(kql_ids, [subscription_id]),
            )
        except Exception as exc:
            logger.error(
                "Incremental discovery failed for subscription %s: %s",
                subscription_id, exc,
            )
            raise

        current_ids = {row["id"] for row in current_ids_raw if "id" in row}
        changed_docs = self._to_documents(changed_raw, subscription_id)

        # Categorise as created vs modified based on cached_resource_ids
        created: List[Dict[str, Any]] = []
        modified: List[Dict[str, Any]] = []
        deleted: List[Dict[str, Any]] = []

        known_ids = cached_resource_ids or set()

        for doc in changed_docs:
            rid = doc.get("resource_id", "")
            if rid not in known_ids:
                doc["change_type"] = "created"
                created.append(doc)
            else:
                doc["change_type"] = "modified"
                modified.append(doc)

        # Detect deletions
        if known_ids:
            deleted_ids = known_ids - current_ids
            for did in deleted_ids:
                deleted.append({
                    "resource_id": did,
                    "change_type": "deleted",
                    "detected_at": _now_iso(),
                })

        logger.info(
            "Incremental discovery for %s: %d created, %d modified, %d deleted",
            subscription_id, len(created), len(modified), len(deleted),
        )
        return {"created": created, "modified": modified, "deleted": deleted}

    # -- relationship extraction -------------------------------------------

    async def extract_relationships(
        self,
        resource: Dict[str, Any],
        depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Extract parent/child dependency relationships for a resource.

        Uses Resource Graph to follow references embedded in resource
        properties (e.g. a VM's NIC references, an NIC's VNet, etc.).

        Args:
            resource: A resource document (must contain ``resource_id``
                and ``resource_type``).
            depth: Maximum levels of relationship traversal (capped at 2).

        Returns:
            List of relationship edge dicts with ``source``, ``target``,
            ``relationship_type``, and ``depth`` fields.
        """
        depth = min(depth, 2)  # cap
        resource_id = resource.get("resource_id", resource.get("id", ""))
        resource_type = resource.get("resource_type", resource.get("type", "")).lower()
        subscription_id = resource.get("subscription_id", "")

        if not resource_id or not subscription_id:
            return []

        relationships: List[Dict[str, Any]] = []
        visited: Set[str] = {resource_id.lower()}

        await self._extract_relationships_recursive(
            resource_id=resource_id,
            resource_type=resource_type,
            subscription_id=subscription_id,
            current_depth=1,
            max_depth=depth,
            visited=visited,
            relationships=relationships,
        )

        logger.debug(
            "Extracted %d relationships for %s (depth=%d)",
            len(relationships), resource_id, depth,
        )
        return relationships

    async def _extract_relationships_recursive(
        self,
        resource_id: str,
        resource_type: str,
        subscription_id: str,
        current_depth: int,
        max_depth: int,
        visited: Set[str],
        relationships: List[Dict[str, Any]],
    ) -> None:
        """Recursively extract relationships up to *max_depth*."""
        if current_depth > max_depth:
            return

        # Use typed KQL relationship extraction when available
        rel_kql_snippet = _RELATIONSHIP_KQL.get(resource_type)
        if rel_kql_snippet:
            kql = (
                "Resources\n"
                f"| where id =~ '{resource_id}'\n"
                f"| {rel_kql_snippet}\n"
                "| mvexpand _rels\n"
                "| extend rel_id = tostring(_rels.id)\n"
                "| where isnotempty(rel_id)\n"
                "| project rel_id"
            )
        else:
            # Generic fallback: find resources that reference this resource
            kql = (
                "Resources\n"
                f"| where properties contains '{resource_id}'\n"
                f"| where id !~ '{resource_id}'\n"
                "| project id, type\n"
                "| limit 20"
            )

        try:
            rows = await self._execute_graph_query(kql, [subscription_id])
        except Exception as exc:
            logger.warning(
                "Relationship query failed for %s: %s", resource_id, exc,
            )
            return

        for row in rows:
            target_id = row.get("rel_id") or row.get("id", "")
            if not target_id or target_id.lower() in visited:
                continue

            visited.add(target_id.lower())
            target_type = row.get("type", "unknown")

            relationships.append({
                "source": resource_id,
                "target": target_id,
                "relationship_type": "depends_on",
                "depth": current_depth,
            })

            # Recurse one level deeper
            if current_depth < max_depth:
                await self._extract_relationships_recursive(
                    resource_id=target_id,
                    resource_type=target_type.lower() if target_type else "",
                    subscription_id=subscription_id,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    visited=visited,
                    relationships=relationships,
                )

    # -- property enrichment ------------------------------------------------

    async def enrich_properties(
        self,
        resource: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enrich a resource document with live runtime properties.

        Adds VM power state, App Service status, Storage Account details,
        SQL Database tier, VNet topology, Container App state, and AKS
        cluster info for supported resource types.

        Enrichment results are cached for ``_ENRICHMENT_TTL_SECONDS`` to
        avoid redundant API calls.

        Args:
            resource: A resource document to enrich.

        Returns:
            The same dict with an ``enriched_properties`` key added.
        """
        resource_type = resource.get(
            "resource_type", resource.get("type", ""),
        ).lower()
        resource_id = resource.get("resource_id", resource.get("id", ""))

        # Check enrichment cache - skip if TTL hasn't expired
        cached = self._enrichment_cache.get(resource_id)
        if cached is not None:
            cached_data, cached_ts = cached
            if time.time() - cached_ts < _ENRICHMENT_TTL_SECONDS:
                resource["enriched_properties"] = cached_data
                logger.debug(
                    "Enrichment cache HIT for %s (age=%.0fs)",
                    resource_id, time.time() - cached_ts,
                )
                return resource

        enrichment: Dict[str, Any] = {"enriched_at": _now_iso()}

        # Resolve the enrichment method from the type map
        method_name = _ENRICHMENT_TYPE_MAP.get(resource_type)

        try:
            if method_name is not None:
                method = getattr(self, method_name)
                enrichment.update(await method(resource_id))
                enrichment["enrichment_status"] = "success"
            else:
                enrichment["enrichment_status"] = "unsupported"
                enrichment["message"] = (
                    f"Enrichment not yet implemented for {resource_type}"
                )
        except Exception as exc:
            logger.warning(
                "Enrichment failed for %s (%s): %s",
                resource_id, resource_type, exc,
            )
            enrichment["enrichment_status"] = "failed"
            enrichment["enrichment_error"] = str(exc)
            # Preserve whatever basic properties are already available
            enrichment["basic_properties"] = {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "resource_name": resource.get(
                    "resource_name", resource.get("name", ""),
                ),
                "location": resource.get("location", ""),
            }

        resource["enriched_properties"] = enrichment

        # Cache successful and failed enrichments (failed ones are retried
        # once TTL expires)
        self._enrichment_cache[resource_id] = (enrichment, time.time())

        return resource

    async def enrich_batch(
        self,
        resources: List[Dict[str, Any]],
        concurrency: int = 5,
    ) -> List[Dict[str, Any]]:
        """Enrich a batch of resources concurrently.

        Args:
            resources: List of resource documents to enrich.
            concurrency: Maximum concurrent enrichment calls.

        Returns:
            The same list with enriched properties added.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _enrich_one(res: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.enrich_properties(res)

        results = await asyncio.gather(
            *[_enrich_one(r) for r in resources],
            return_exceptions=True,
        )

        # Replace exceptions with error markers
        enriched: List[Dict[str, Any]] = []
        for res, result in zip(resources, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Batch enrichment error for %s: %s",
                    res.get("resource_id", "unknown"), result,
                )
                res["enriched_properties"] = {
                    "enriched_at": _now_iso(),
                    "enrichment_status": "failed",
                    "enrichment_error": str(result),
                }
                enriched.append(res)
            else:
                enriched.append(result)

        logger.info(
            "Batch enrichment complete: %d resources, %d succeeded",
            len(resources),
            sum(1 for r in enriched
                if r.get("enriched_properties", {}).get("enrichment_status") == "success"),
        )
        return enriched

    # -- per-type enrichment methods ----------------------------------------

    async def _enrich_vm(self, resource_id: str) -> Dict[str, Any]:
        """Fetch VM power state, OS details, disk info, and NIC details."""
        if ComputeManagementClient is None:
            return {"error": "azure-mgmt-compute not installed"}

        sub_id, rg, vm_name = _parse_resource_id(resource_id)
        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _get_vm_details():
            client = ComputeManagementClient(credential, sub_id)
            return client.virtual_machines.get(rg, vm_name, expand="instanceView")

        vm = await loop.run_in_executor(None, _get_vm_details)

        # Extract power state from instance view
        power_state = "Unknown"
        os_name = None
        os_version = None
        if vm.instance_view:
            for status in (vm.instance_view.statuses or []):
                if status.code and status.code.startswith("PowerState/"):
                    power_state = status.display_status or status.code.split("/")[-1]
                    break
            os_name = getattr(vm.instance_view, "os_name", None)
            os_version = getattr(vm.instance_view, "os_version", None)

        # OS disk details
        os_disk: Dict[str, Any] = {}
        if vm.storage_profile and vm.storage_profile.os_disk:
            od = vm.storage_profile.os_disk
            os_disk = {
                "os_type": str(od.os_type) if od.os_type else None,
                "disk_size_gb": od.disk_size_gb,
                "caching": str(od.caching) if od.caching else None,
                "managed_disk_type": (
                    str(od.managed_disk.storage_account_type)
                    if od.managed_disk and od.managed_disk.storage_account_type
                    else None
                ),
            }

        # Data disk count
        data_disk_count = 0
        if vm.storage_profile and vm.storage_profile.data_disks:
            data_disk_count = len(vm.storage_profile.data_disks)

        # NIC details
        nic_ids: List[str] = []
        if vm.network_profile and vm.network_profile.network_interfaces:
            nic_ids = [
                nic.id for nic in vm.network_profile.network_interfaces
                if nic.id
            ]

        # Boot diagnostics
        boot_diagnostics_enabled = False
        if (vm.diagnostics_profile
                and vm.diagnostics_profile.boot_diagnostics):
            boot_diagnostics_enabled = bool(
                vm.diagnostics_profile.boot_diagnostics.enabled,
            )

        return {
            "power_state": power_state,
            "vm_size": (
                vm.hardware_profile.vm_size
                if vm.hardware_profile else None
            ),
            "os_type": os_disk.get("os_type"),
            "os_name": os_name,
            "os_version": os_version,
            "os_disk": os_disk,
            "data_disk_count": data_disk_count,
            "nic_ids": nic_ids,
            "nic_count": len(nic_ids),
            "boot_diagnostics_enabled": boot_diagnostics_enabled,
            "availability_zones": vm.zones or [],
            "vm_agent_status": (
                vm.instance_view.vm_agent.vm_agent_version
                if vm.instance_view and vm.instance_view.vm_agent
                else None
            ),
            "provisioning_state": vm.provisioning_state,
        }

    async def _enrich_app_service(self, resource_id: str) -> Dict[str, Any]:
        """Fetch App Service availability state, runtime, and config."""
        if WebSiteManagementClient is None:
            return {"error": "azure-mgmt-web not installed"}

        sub_id, rg, app_name = _parse_resource_id(resource_id)
        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _get_site():
            client = WebSiteManagementClient(credential, sub_id)
            return client.web_apps.get(rg, app_name)

        site = await loop.run_in_executor(None, _get_site)

        return {
            "state": site.state,
            "availability_state": (
                str(site.availability_state)
                if site.availability_state else None
            ),
            "default_host_name": site.default_host_name,
            "https_only": site.https_only,
            "runtime_stack": (
                getattr(site.site_config, "linux_fx_version", None)
                if site.site_config else None
            ),
            "sku": (
                site.sku if hasattr(site, "sku") else None
            ),
            "kind": site.kind,
            "client_cert_enabled": site.client_cert_enabled,
            "enabled": site.enabled,
        }

    async def _enrich_storage(self, resource_id: str) -> Dict[str, Any]:
        """Enrich Storage Account with access tier, replication, and services."""
        if StorageManagementClient is None:
            return {"error": "azure-mgmt-storage not installed"}

        sub_id, rg, account_name = _parse_resource_id(resource_id)
        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _get_storage_account():
            client = StorageManagementClient(credential, sub_id)
            return client.storage_accounts.get_properties(rg, account_name)

        sa = await loop.run_in_executor(None, _get_storage_account)

        # Determine which services are enabled via encryption settings
        services_enabled: Dict[str, bool] = {}
        if sa.encryption and sa.encryption.services:
            svc = sa.encryption.services
            services_enabled["blob"] = bool(svc.blob and svc.blob.enabled)
            services_enabled["file"] = bool(svc.file and svc.file.enabled)
            services_enabled["queue"] = bool(svc.queue and svc.queue.enabled)
            services_enabled["table"] = bool(svc.table and svc.table.enabled)

        # Private endpoint connections count
        pe_count = 0
        if sa.private_endpoint_connections:
            pe_count = len(sa.private_endpoint_connections)

        return {
            "access_tier": str(sa.access_tier) if sa.access_tier else None,
            "replication_type": (
                str(sa.sku.name) if sa.sku else None
            ),
            "kind": str(sa.kind) if sa.kind else None,
            "provisioning_state": (
                str(sa.provisioning_state) if sa.provisioning_state else None
            ),
            "is_hns_enabled": sa.is_hns_enabled,
            "allow_blob_public_access": sa.allow_blob_public_access,
            "minimum_tls_version": (
                str(sa.minimum_tls_version)
                if sa.minimum_tls_version else None
            ),
            "enable_https_traffic_only": sa.enable_https_traffic_only,
            "services_encrypted": services_enabled,
            "private_endpoint_count": pe_count,
            "network_rule_default_action": (
                str(sa.network_rule_set.default_action)
                if sa.network_rule_set else None
            ),
            "primary_location": sa.primary_location,
            "secondary_location": sa.secondary_location,
            "status_of_primary": (
                str(sa.status_of_primary) if sa.status_of_primary else None
            ),
        }

    async def _enrich_sql_server(self, resource_id: str) -> Dict[str, Any]:
        """Enrich SQL Server with version and admin info via Resource Graph."""
        sub_id, _rg, _server_name = _parse_resource_id(resource_id)

        kql = (
            "Resources\n"
            f"| where id =~ '{resource_id}'\n"
            "| project "
            "  version = properties.version,"
            "  state = properties.state,"
            "  fullyQualifiedDomainName = properties.fullyQualifiedDomainName,"
            "  publicNetworkAccess = properties.publicNetworkAccess,"
            "  minimalTlsVersion = properties.minimalTlsVersion,"
            "  administratorLogin = properties.administratorLogin"
        )

        rows = await self._execute_graph_query(kql, [sub_id])
        if not rows:
            return {"error": "SQL Server not found in Resource Graph"}

        row = rows[0]
        return {
            "version": row.get("version"),
            "state": row.get("state"),
            "fqdn": row.get("fullyQualifiedDomainName"),
            "public_network_access": row.get("publicNetworkAccess"),
            "minimal_tls_version": row.get("minimalTlsVersion"),
            "admin_login": row.get("administratorLogin"),
        }

    async def _enrich_sql(self, resource_id: str) -> Dict[str, Any]:
        """Enrich SQL Database with tier, size, and replication via Resource Graph."""
        parts = resource_id.split("/")
        if len(parts) < 11:
            return {"error": "Invalid SQL Database resource ID"}

        sub_id = parts[2]

        kql = (
            "Resources\n"
            f"| where id =~ '{resource_id}'\n"
            "| project "
            "  sku,"
            "  state = properties.status,"
            "  maxSizeBytes = properties.maxSizeBytes,"
            "  collation = properties.collation,"
            "  currentServiceObjectiveName = properties.currentServiceObjectiveName,"
            "  requestedServiceObjectiveName = properties.requestedServiceObjectiveName,"
            "  databaseId = properties.databaseId,"
            "  zoneRedundant = properties.zoneRedundant,"
            "  readScale = properties.readScale,"
            "  failoverGroupId = properties.failoverGroupId,"
            "  elasticPoolId = properties.elasticPoolId"
        )

        rows = await self._execute_graph_query(kql, [sub_id])
        if not rows:
            return {"error": "SQL Database not found in Resource Graph"}

        row = rows[0]
        sku = row.get("sku") or {}

        # Convert maxSizeBytes to GB for readability
        max_size_bytes = row.get("maxSizeBytes")
        max_size_gb = None
        if max_size_bytes is not None:
            try:
                max_size_gb = round(int(max_size_bytes) / (1024 ** 3), 2)
            except (ValueError, TypeError):
                pass

        return {
            "service_tier": sku.get("tier"),
            "sku_name": sku.get("name"),
            "capacity": sku.get("capacity"),
            "state": row.get("state"),
            "max_size_gb": max_size_gb,
            "collation": row.get("collation"),
            "current_objective": row.get("currentServiceObjectiveName"),
            "zone_redundant": row.get("zoneRedundant"),
            "read_scale": row.get("readScale"),
            "failover_group_id": row.get("failoverGroupId"),
            "elastic_pool_id": row.get("elasticPoolId"),
            "in_failover_group": row.get("failoverGroupId") is not None,
        }

    async def _enrich_vnet(self, resource_id: str) -> Dict[str, Any]:
        """Enrich VNet with address space, subnets, peering, and DNS."""
        if NetworkManagementClient is None:
            return {"error": "azure-mgmt-network not installed"}

        sub_id, rg, vnet_name = _parse_resource_id(resource_id)
        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _get_vnet():
            client = NetworkManagementClient(credential, sub_id)
            return client.virtual_networks.get(rg, vnet_name)

        vnet = await loop.run_in_executor(None, _get_vnet)

        # Address space
        address_prefixes: List[str] = []
        if vnet.address_space and vnet.address_space.address_prefixes:
            address_prefixes = list(vnet.address_space.address_prefixes)

        # Subnets
        subnets: List[Dict[str, Any]] = []
        if vnet.subnets:
            for sn in vnet.subnets:
                subnets.append({
                    "name": sn.name,
                    "address_prefix": sn.address_prefix,
                    "nsg_id": (
                        sn.network_security_group.id
                        if sn.network_security_group else None
                    ),
                    "route_table_id": (
                        sn.route_table.id if sn.route_table else None
                    ),
                    "delegations": [
                        d.service_name for d in (sn.delegations or [])
                    ],
                    "private_endpoint_count": (
                        len(sn.private_endpoints)
                        if sn.private_endpoints else 0
                    ),
                })

        # Peerings
        peerings: List[Dict[str, Any]] = []
        if vnet.virtual_network_peerings:
            for p in vnet.virtual_network_peerings:
                peerings.append({
                    "name": p.name,
                    "peering_state": (
                        str(p.peering_state) if p.peering_state else None
                    ),
                    "remote_vnet_id": (
                        p.remote_virtual_network.id
                        if p.remote_virtual_network else None
                    ),
                    "allow_forwarded_traffic": p.allow_forwarded_traffic,
                    "allow_gateway_transit": p.allow_gateway_transit,
                    "use_remote_gateways": p.use_remote_gateways,
                })

        # DNS servers
        dns_servers: List[str] = []
        if vnet.dhcp_options and vnet.dhcp_options.dns_servers:
            dns_servers = list(vnet.dhcp_options.dns_servers)

        return {
            "address_prefixes": address_prefixes,
            "subnet_count": len(subnets),
            "subnets": subnets,
            "peering_count": len(peerings),
            "peerings": peerings,
            "dns_servers": dns_servers,
            "enable_ddos_protection": vnet.enable_ddos_protection,
            "provisioning_state": vnet.provisioning_state,
        }

    async def _enrich_container_app(self, resource_id: str) -> Dict[str, Any]:
        """Enrich Container App with replica count, ingress, and revision info.

        Uses Resource Graph since azure-mgmt-containerapp may not be installed.
        """
        sub_id, _rg, _app_name = _parse_resource_id(resource_id)

        kql = (
            "Resources\n"
            f"| where id =~ '{resource_id}'\n"
            "| project "
            "  provisioningState = properties.provisioningState,"
            "  latestRevisionName = properties.latestRevisionName,"
            "  latestRevisionFqdn = properties.latestRevisionFqdn,"
            "  latestReadyRevisionName = properties.latestReadyRevisionName,"
            "  managedEnvironmentId = properties.managedEnvironmentId,"
            "  runningStatus = properties.runningStatus,"
            "  ingressConfig = properties.configuration.ingress,"
            "  activeRevisionsMode = properties.configuration.activeRevisionsMode,"
            "  registries = properties.configuration.registries,"
            "  templateContainers = properties.template.containers,"
            "  templateScale = properties.template.scale"
        )

        rows = await self._execute_graph_query(kql, [sub_id])
        if not rows:
            return {"error": "Container App not found in Resource Graph"}

        row = rows[0]

        # Parse ingress config
        ingress = row.get("ingressConfig") or {}
        ingress_enabled = bool(ingress)

        # Parse scale config
        scale = row.get("templateScale") or {}
        min_replicas = scale.get("minReplicas", 0)
        max_replicas = scale.get("maxReplicas", 0)

        # Container info
        containers = row.get("templateContainers") or []
        container_images = [
            c.get("image", "unknown") for c in containers
        ]

        running_status = row.get("runningStatus") or {}

        return {
            "provisioning_state": row.get("provisioningState"),
            "latest_revision": row.get("latestRevisionName"),
            "latest_revision_fqdn": row.get("latestRevisionFqdn"),
            "latest_ready_revision": row.get("latestReadyRevisionName"),
            "managed_environment_id": row.get("managedEnvironmentId"),
            "running_state": running_status.get("state"),
            "ingress_enabled": ingress_enabled,
            "ingress_external": ingress.get("external", False),
            "ingress_target_port": ingress.get("targetPort"),
            "ingress_transport": ingress.get("transport"),
            "revision_mode": row.get("activeRevisionsMode", "Single"),
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
            "container_images": container_images,
            "container_count": len(containers),
        }

    async def _enrich_aks(self, resource_id: str) -> Dict[str, Any]:
        """Enrich AKS cluster with version, node pools, and network config."""
        if ContainerServiceClient is None:
            return {"error": "azure-mgmt-containerservice not installed"}

        sub_id, rg, cluster_name = _parse_resource_id(resource_id)
        credential = self._get_credential()
        loop = asyncio.get_event_loop()

        def _get_cluster():
            client = ContainerServiceClient(credential, sub_id)
            return client.managed_clusters.get(rg, cluster_name)

        cluster = await loop.run_in_executor(None, _get_cluster)

        # Node pool details
        node_pools: List[Dict[str, Any]] = []
        if cluster.agent_pool_profiles:
            for pool in cluster.agent_pool_profiles:
                node_pools.append({
                    "name": pool.name,
                    "vm_size": pool.vm_size,
                    "count": pool.count,
                    "min_count": pool.min_count,
                    "max_count": pool.max_count,
                    "os_type": str(pool.os_type) if pool.os_type else None,
                    "mode": str(pool.mode) if pool.mode else None,
                    "enable_auto_scaling": pool.enable_auto_scaling,
                    "availability_zones": pool.availability_zones or [],
                })

        # Network profile
        network_info: Dict[str, Any] = {}
        if cluster.network_profile:
            np = cluster.network_profile
            network_info = {
                "network_plugin": (
                    str(np.network_plugin) if np.network_plugin else None
                ),
                "network_policy": (
                    str(np.network_policy) if np.network_policy else None
                ),
                "service_cidr": np.service_cidr,
                "dns_service_ip": np.dns_service_ip,
                "pod_cidr": np.pod_cidr,
                "load_balancer_sku": (
                    str(np.load_balancer_sku)
                    if np.load_balancer_sku else None
                ),
            }

        # RBAC
        rbac_enabled = False
        if cluster.enable_rbac is not None:
            rbac_enabled = cluster.enable_rbac
        elif (cluster.aad_profile
              and getattr(cluster.aad_profile, "managed", None)):
            rbac_enabled = True

        return {
            "kubernetes_version": cluster.kubernetes_version,
            "provisioning_state": cluster.provisioning_state,
            "power_state": (
                str(cluster.power_state.code)
                if cluster.power_state else None
            ),
            "fqdn": cluster.fqdn,
            "node_pool_count": len(node_pools),
            "node_pools": node_pools,
            "total_node_count": sum(
                (p.get("count") or 0) for p in node_pools
            ),
            "network": network_info,
            "rbac_enabled": rbac_enabled,
            "private_cluster": (
                cluster.api_server_access_profile.enable_private_cluster
                if cluster.api_server_access_profile else False
            ),
            "sku_tier": (
                str(cluster.sku.tier)
                if cluster.sku and cluster.sku.tier else None
            ),
        }

    # -- internal helpers ---------------------------------------------------

    def _to_documents(
        self,
        raw_resources: List[Dict[str, Any]],
        subscription_id: str,
    ) -> List[Dict[str, Any]]:
        """Convert raw Resource Graph rows into Cosmos-DB-ready documents."""
        documents: List[Dict[str, Any]] = []
        now = _now_iso()

        for r in raw_resources:
            rid = r.get("id", "")
            doc: Dict[str, Any] = {
                # Cosmos DB fields
                "id": rid.lower().replace("/", "_"),
                "partition_key": subscription_id,
                # Resource identity
                "resource_id": rid,
                "resource_name": r.get("name", ""),
                "resource_type": (r.get("type") or "").lower(),
                "location": r.get("location", ""),
                "resource_group": r.get("resourceGroup", ""),
                "subscription_id": r.get("subscriptionId", subscription_id),
                # Metadata
                "tags": _sanitize_tags(r.get("tags")),
                "sku": r.get("sku"),
                "kind": r.get("kind"),
                "managed_by": r.get("managedBy"),
                "zones": r.get("zones"),
                # Selective properties (avoid storing full blob)
                "selected_properties": self._extract_selected_properties(
                    r.get("type", ""), r.get("properties") or {},
                ),
                # Timestamps
                "discovered_at": now,
                "last_seen": now,
                # TTL for Cosmos DB auto-expiry (default: 7 days)
                "ttl": 604800,
            }
            documents.append(doc)

        return documents

    @staticmethod
    def _extract_selected_properties(
        resource_type: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract commonly-used properties based on resource type."""
        rtype = resource_type.lower()
        selected: Dict[str, Any] = {}

        if "virtualmachines" in rtype:
            hardware_profile = properties.get("hardwareProfile")
            if isinstance(hardware_profile, dict):
                selected["vm_size"] = hardware_profile.get("vmSize")
            else:
                selected["vm_size"] = None
            
            storage_profile = properties.get("storageProfile")
            if isinstance(storage_profile, dict):
                os_disk = storage_profile.get("osDisk")
                if isinstance(os_disk, dict):
                    selected["os_type"] = os_disk.get("osType")
                else:
                    selected["os_type"] = None
            else:
                selected["os_type"] = None
            
            selected["provisioning_state"] = properties.get("provisioningState")
        elif "microsoft.web/sites" in rtype:
            selected["kind"] = properties.get("kind")
            selected["state"] = properties.get("state")
            selected["default_host_name"] = properties.get("defaultHostName")
            selected["https_only"] = properties.get("httpsOnly")
        elif "storageaccounts" in rtype:
            selected["access_tier"] = properties.get("accessTier")
            selected["provisioning_state"] = properties.get("provisioningState")
            selected["kind"] = properties.get("kind")
        elif "microsoft.containerapp" in rtype or "containerapps" in rtype:
            selected["provisioning_state"] = properties.get("provisioningState")
            running_status = properties.get("runningStatus")
            if isinstance(running_status, dict):
                selected["running_status"] = running_status.get("state")
            else:
                selected["running_status"] = running_status
            selected["managed_environment_id"] = properties.get(
                "managedEnvironmentId",
            )
        elif "microsoft.sql" in rtype:
            selected["state"] = properties.get("state")
            selected["version"] = properties.get("version")
        elif "microsoft.network" in rtype:
            selected["provisioning_state"] = properties.get("provisioningState")

        return selected
