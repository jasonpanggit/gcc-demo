"""Patch Management MCP Server

Provides MCP-compliant tools for Azure patch management operations:
- VM and Arc server patch assessment
- Patch installation with classification filtering
- Patch compliance queries via Azure Resource Graph
- Real-time status monitoring for patch operations
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

try:
    from utils.normalization import normalize_os_record
except ImportError:
    from app.agentic.eol.utils.normalization import normalize_os_record

try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
    import aiohttp
except ImportError:
    ClientSecretCredential = None
    ResourceGraphClient = None
    QueryRequest = None
    QueryRequestOptions = None
    aiohttp = None

_LOG_LEVEL_NAME = os.getenv("PATCH_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO

try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Suppress verbose Azure SDK HTTP logging
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

mcp = FastMCP(name="azure-patch")

# Azure ARM constants
_ARM_BASE = "https://management.azure.com"
_ASSESS_API_VERSION = "2022-12-27"  # HybridCompute (Arc)
_AVM_ASSESS_API_VERSION = "2023-03-01"  # Compute (Azure VM)
_POLL_INTERVAL_SECONDS = 4
_POLL_MAX_SECONDS = 180  # 3 minutes max wait

_credential: Optional[Any] = None
_subscription_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

async def _get_arm_token() -> str:
    """Get an access token for management.azure.com using injected SPN credentials."""
    global _credential

    try:
        sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
        sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if not (sp_client_id and sp_client_secret and tenant_id):
            raise RuntimeError(
                "Injected SPN credentials are required. "
                "Set AZURE_SP_CLIENT_ID, AZURE_SP_CLIENT_SECRET, and AZURE_TENANT_ID."
            )

        if not isinstance(_credential, ClientSecretCredential):
            _credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=sp_client_id,
                client_secret=sp_client_secret
            )
        logger.info("Patch MCP auth: using injected SPN credential (%s...)", sp_client_id[:8])

        token = await _credential.get_token("https://management.azure.com/.default")
        return token.token
    except Exception as exc:
        logger.error("Failed to acquire ARM token: %s", exc)
        raise RuntimeError(f"Azure auth error: {exc}") from exc


def _parse_resource_id(resource_id: str) -> tuple[str, str, str]:
    """Extract (subscription_id, resource_group, machine_name) from a resource ID."""
    parts = resource_id.strip("/").split("/")
    try:
        sub = parts[parts.index("subscriptions") + 1]
        rg = parts[parts.index("resourceGroups") + 1]
        name = parts[-1]
        return sub, rg, name
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Cannot parse resource ID: {resource_id}") from exc


def _resolve_vm_type(resource_id: Optional[str], vm_type: Optional[str]) -> str:
    """Return 'arc' or 'azure-vm' based on resource_id or explicit hint."""
    if vm_type and vm_type.lower() in ("arc", "azure-vm"):
        return vm_type.lower()
    rid = (resource_id or "").lower()
    if "/microsoft.compute/virtualmachines/" in rid:
        return "azure-vm"
    return "arc"


_ARG_MAX_RETRIES = 3
_ARG_BACKOFF_BASE = 5  # seconds, doubled each retry


async def _query_arg(query: str, subscription_ids: List[str]) -> List[Dict[str, Any]]:
    """Execute a Resource Graph query with exponential-backoff retry on throttling."""
    if not ResourceGraphClient or not QueryRequest:
        raise RuntimeError("azure-mgmt-resourcegraph not installed")

    sp_client_id = os.getenv("AZURE_SP_CLIENT_ID")
    sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    if not (sp_client_id and sp_client_secret and tenant_id):
        raise RuntimeError(
            "Injected SPN credentials are required for ARG queries. "
            "Set AZURE_SP_CLIENT_ID, AZURE_SP_CLIENT_SECRET, and AZURE_TENANT_ID."
        )

    from azure.identity import ClientSecretCredential as SyncSPCred
    from azure.core.exceptions import HttpResponseError
    cred = SyncSPCred(tenant_id=tenant_id, client_id=sp_client_id, client_secret=sp_client_secret)

    graph_client = ResourceGraphClient(cred)
    all_rows: List[Dict[str, Any]] = []
    skip_token: Optional[str] = None
    loop = asyncio.get_event_loop()

    while True:
        last_exc: Optional[Exception] = None
        for attempt in range(_ARG_MAX_RETRIES):
            try:
                def _run(st=skip_token):
                    opts = QueryRequestOptions(result_format="objectArray", top=1000)
                    if st:
                        opts.skip_token = st
                    req = QueryRequest(subscriptions=subscription_ids, query=query, options=opts)
                    return graph_client.resources(req)

                response = await loop.run_in_executor(None, _run)
                last_exc = None
                break  # success — exit retry loop
            except HttpResponseError as exc:
                last_exc = exc
                if getattr(getattr(exc, "error", None), "code", None) == "RateLimiting":
                    retry_after = _ARG_BACKOFF_BASE * (2 ** attempt)
                    try:
                        header_val = exc.response.headers.get("Retry-After") if exc.response else None
                        if header_val:
                            retry_after = int(header_val)
                    except Exception:
                        pass
                    logger.warning(
                        "ARG throttled (attempt %d/%d) — sleeping %ds before retry",
                        attempt + 1, _ARG_MAX_RETRIES, retry_after,
                    )
                    await asyncio.sleep(retry_after)
                else:
                    raise  # non-throttle error, propagate immediately

        if last_exc is not None:
            raise last_exc  # exhausted retries

        data = response.data if hasattr(response, "data") else []
        all_rows.extend(data if isinstance(data, list) else [])
        skip_token = getattr(response, "skip_token", None)
        if not skip_token:
            break

    return all_rows


def _parse_arg_list(val: Any) -> List[str]:
    """ARG returns JSON arrays as strings like '["Critical","Security"]' – parse them."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return [val] if val else []
    return []


async def _poll_operation(
    session: aiohttp.ClientSession,
    operation_url: str,
    token: str,
    operation_label: str = "operation",
) -> Dict[str, Any]:
    """Poll an Azure async operation URL until it completes or times out."""
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + _POLL_MAX_SECONDS

    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        async with session.get(operation_url, headers=headers) as resp:
            raw_text = await resp.text()
            if not raw_text or not raw_text.strip():
                logger.debug("Poll %s: empty response (HTTP %s), retrying", operation_label, resp.status)
                continue
            try:
                body = json.loads(raw_text)
            except Exception:
                logger.debug("Poll %s: non-JSON response (HTTP %s), retrying", operation_label, resp.status)
                continue

            if not isinstance(body, dict):
                logger.debug("Poll %s: unexpected body type %s, retrying", operation_label, type(body))
                continue

            status = (body.get("status") or "").lower()
            logger.debug("Poll %s status: %s", operation_label, status)

            if status == "succeeded":
                return body
            if status in ("failed", "canceled", "cancelled"):
                error = body.get("error") or body
                raise RuntimeError(f"{operation_label} failed: {error}")

    raise TimeoutError(f"{operation_label} timed out after {_POLL_MAX_SECONDS // 60} minutes")


def _extract_install_result(operation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract install outcome from a completed installPatches operation result."""
    props = operation_result.get("properties") or {}
    return {
        "status": operation_result.get("status", "Unknown"),
        "installed_patch_count": props.get("installedPatchCount", 0) or 0,
        "failed_patch_count": props.get("failedPatchCount", 0) or 0,
        "pending_patch_count": props.get("pendingPatchCount", 0) or 0,
        "not_selected_patch_count": props.get("notSelectedPatchCount", 0) or 0,
        "excluded_patch_count": props.get("excludedPatchCount", 0) or 0,
        "reboot_status": props.get("rebootStatus"),
        "maintenance_window_exceeded": props.get("maintenanceWindowExceeded", False),
        "start_date_time": props.get("startDateTime"),
        "last_modified": props.get("lastModifiedDateTime"),
        "patches": props.get("patches", []),
        "error": props.get("error"),
    }


def _extract_patches(operation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the patch list from a completed assessPatches operation result."""
    props = operation_result.get("properties") or {}
    details = (
        props.get("patchAssessmentDetails")
        or props.get("assessmentDetails")
        or props
    )

    available_patches: List[Dict[str, Any]] = details.get("availablePatches", [])

    critical_count = details.get("criticalAndSecurityPatchCount", 0) or 0
    other_count = details.get("otherPatchCount", 0) or 0

    if available_patches and critical_count == 0:
        for p in available_patches:
            classifications = [c.lower() for c in (p.get("classifications") or [])]
            if "critical" in classifications or "security" in classifications:
                critical_count += 1
            else:
                other_count += 1

    return {
        "available_patches": available_patches,
        "critical_and_security_count": critical_count,
        "other_count": other_count,
        "total_count": len(available_patches) if available_patches else (critical_count + other_count),
        "last_assessed": operation_result.get("endTime") or datetime.now(timezone.utc).isoformat(),
        "status": operation_result.get("status", "Succeeded"),
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_azure_vms(
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[Optional[str], "Filter by resource group (optional)"] = None,
) -> Dict[str, Any]:
    """
    List all Azure VMs and Arc-enabled servers in a subscription.

    Returns unified list tagged with vm_type ('arc' or 'azure-vm').
    Use this to discover patch targets before assessment or installation.
    """
    try:
        from utils.resource_inventory_client import get_resource_inventory_client
        from main import get_eol_orchestrator

        machines: List[Dict[str, Any]] = []

        # Arc-enabled servers from OS inventory
        try:
            orchestrator = get_eol_orchestrator()
            os_result = await orchestrator.agents["os_inventory"].get_os_inventory(days=90)
            all_os: List[Dict[str, Any]] = (
                os_result.get("data", []) if isinstance(os_result, dict) else []
            )
            for item in all_os:
                if (
                    str(item.get("computer_type", "")).lower() == "arc-enabled server"
                    or "/microsoft.hybridcompute/machines/" in str(item.get("resource_id", "")).lower()
                ):
                    if resource_group and item.get("resource_group") != resource_group:
                        continue
                    machines.append({**item, "vm_type": "arc"})
        except Exception as exc:
            logger.warning("Failed to fetch Arc VMs from OS inventory: %s", exc)

        # Azure VMs from Resource Inventory
        try:
            inv_client = get_resource_inventory_client()
            azure_vms = await inv_client.get_resources(
                "Microsoft.Compute/virtualMachines",
                subscription_id=subscription_id,
            )
            arc_rid_set = {str(m.get("resource_id", "")).lower() for m in machines}
            for vm in azure_vms:
                sp = vm.get("selected_properties") or {}
                rid = str(vm.get("resource_id") or vm.get("id") or "").lower()
                rg = vm.get("resource_group") or vm.get("resourceGroup")

                if not rid or rid in arc_rid_set:
                    continue
                if resource_group and rg != resource_group:
                    continue

                vm_name = vm.get("resource_name") or vm.get("name")
                normalized_os = normalize_os_record(
                    sp.get("os_image") or sp.get("os_type") or vm.get("os_name"),
                    vm.get("os_version"),
                    sp.get("os_type") or vm.get("os_type"),
                )
                machines.append({
                    "computer": vm_name,
                    "name": vm_name,
                    "os_name": normalized_os["os_name"],
                    "os_version": normalized_os.get("os_version"),
                    "os_type": normalized_os.get("os_type"),
                    "raw_os_name": normalized_os.get("raw_os_name"),
                    "raw_os_version": normalized_os.get("raw_os_version"),
                    "normalized_os_name": normalized_os.get("normalized_os_name"),
                    "normalized_os_version": normalized_os.get("normalized_os_version"),
                    "resource_id": vm.get("resource_id") or vm.get("id"),
                    "subscription_id": vm.get("subscription_id") or vm.get("subscriptionId") or subscription_id,
                    "resource_group": rg,
                    "location": vm.get("location"),
                    "vm_size": sp.get("vm_size") or vm.get("vm_size"),
                    "vm_type": "azure-vm",
                })
        except Exception as exc:
            logger.warning("Failed to fetch Azure VMs from resource inventory: %s", exc)

        arc_count = sum(1 for m in machines if m.get("vm_type") == "arc")
        avm_count = sum(1 for m in machines if m.get("vm_type") == "azure-vm")

        return {
            "success": True,
            "data": machines,
            "count": len(machines),
            "arc_count": arc_count,
            "azure_vm_count": avm_count,
        }
    except Exception as exc:
        logger.error("list_azure_vms failed: %s", exc)
        return {"success": False, "error": str(exc), "data": []}


@mcp.tool()
async def query_patch_assessments(
    subscription_id: Annotated[str, "Azure subscription ID"],
    machine_name: Annotated[Optional[str], "Filter by specific machine name (optional)"] = None,
    vm_type: Annotated[str, "'arc' or 'azure-vm'"] = "arc",
) -> Dict[str, Any]:
    """
    Query Azure Resource Graph for historical patch assessment data with Cosmos DB caching.

    Returns stored assessment summaries and patch lists without triggering new assessments.
    Use this to check last-known patch status before deciding to trigger a live assessment.

    PERFORMANCE: Caches results in Cosmos DB with 1-hour TTL to prevent ARG throttling.
    """
    try:
        # Try Cosmos cache first if machine_name is specified
        if machine_name:
            try:
                from utils.patch_assessment_repository import get_patch_assessment_repository
                repo = await get_patch_assessment_repository()
                cached = await repo.get_assessment(subscription_id, machine_name, vm_type)
                if cached:
                    logger.info(f"Returning cached patch assessment for {machine_name}")
                    return cached
            except Exception as cache_err:
                logger.debug(f"Cache lookup failed, falling back to ARG: {cache_err}")

        resolved_vm_type = _resolve_vm_type(None, vm_type)

        if resolved_vm_type == "azure-vm":
            summary_type = "microsoft.compute/virtualmachines/patchassessmentresults"
            patches_type = "microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches"
        else:
            summary_type = "microsoft.hybridcompute/machines/patchassessmentresults"
            patches_type = "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches"

        name_filter = ""
        if machine_name:
            safe_name = machine_name.replace("'", "''")
            name_filter = f"| where machineName =~ '{safe_name}'"

        summary_kql = f"""
patchassessmentresources
| where type =~ '{summary_type}'
| extend machineName = tostring(split(id, '/')[8])
{name_filter}
| extend props = properties
| project machineName, resourceGroup, subscriptionId,
    status = tostring(props.status),
    lastModified = tostring(coalesce(props.lastModifiedDateTimeUTC, props.lastModifiedDateTime)),
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount = toint(props.otherPatchCount),
    osType = tostring(props.osType),
    rebootPending = tobool(props.rebootPending)
"""

        patches_kql = f"""
patchassessmentresources
| where type =~ '{patches_type}'
| extend machineName = tostring(split(id, '/')[8])
{name_filter}
| extend props = properties
| project machineName,
    patchName = tostring(props.patchName),
    kbId = tostring(props.kbId),
    classifications = tostring(props.classifications),
    rebootBehavior = tostring(props.rebootBehavior),
    assessmentState = tostring(props.assessmentState),
    publishedDate = tostring(props.publishedDate)
"""

        summary_rows, patches_rows = await asyncio.gather(
            _query_arg(summary_kql, [subscription_id]),
            _query_arg(patches_kql, [subscription_id]),
        )

        # Group patches by machine
        patches_by_machine: Dict[str, List[Dict[str, Any]]] = {}
        for row in patches_rows:
            mname = (row.get("machineName") or "").lower()
            patches_by_machine.setdefault(mname, []).append({
                "patchName": row.get("patchName"),
                "kbId": row.get("kbId"),
                "classifications": _parse_arg_list(row.get("classifications")),
                "rebootBehavior": row.get("rebootBehavior"),
                "assessmentState": row.get("assessmentState"),
                "publishedDate": row.get("publishedDate"),
            })

        # Build results
        machines = []
        for row in summary_rows:
            mname = row.get("machineName") or ""
            patches = patches_by_machine.get(mname.lower(), [])
            crit = row.get("criticalCount") or 0
            other = row.get("otherCount") or 0

            if (crit == 0 and other == 0) and patches:
                for p in patches:
                    cls = [c.lower() for c in (p.get("classifications") or [])]
                    if "critical" in cls or "security" in cls:
                        crit += 1
                    else:
                        other += 1

            machines.append({
                "machine_name": mname,
                "resource_group": row.get("resourceGroup"),
                "subscription_id": row.get("subscriptionId") or subscription_id,
                "os_type": row.get("osType"),
                "reboot_pending": row.get("rebootPending"),
                "vm_type": resolved_vm_type,
                "patches": {
                    "available_patches": patches,
                    "critical_and_security_count": crit,
                    "other_count": other,
                    "total_count": len(patches) or (crit + other),
                    "last_assessed": row.get("lastModified"),
                    "status": row.get("status"),
                    "source": "resource_graph",
                },
            })

        result = {
            "success": True,
            "data": machines,
            "count": len(machines),
            "total_patches": sum(len(m["patches"]["available_patches"]) for m in machines),
        }

        # Cache the result if machine_name was specified
        if machine_name and machines:
            try:
                from utils.patch_assessment_repository import get_patch_assessment_repository
                repo = await get_patch_assessment_repository()
                await repo.store_assessment(subscription_id, machine_name, vm_type, result)
                logger.info(f"Cached patch assessment for {machine_name}")
            except Exception as cache_err:
                logger.debug(f"Failed to cache assessment: {cache_err}")

        return result
    except Exception as exc:
        logger.error("query_patch_assessments failed: %s", exc)
        return {"success": False, "error": str(exc), "data": []}


@mcp.tool()
async def assess_vm_patches(
    machine_name: Annotated[str, "Machine name to assess"],
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[str, "Resource group name"],
    vm_type: Annotated[str, "'arc' or 'azure-vm'"] = "arc",
    resource_id: Annotated[Optional[str], "Full ARM resource ID (overrides other params)"] = None,
) -> Dict[str, Any]:
    """
    Trigger a live patch assessment on an Azure VM or Arc server.

    Returns immediately with operation_url (fire-and-forget).
    Assessment typically completes in 1-3 minutes.
    Use get_assessment_result or query_patch_assessments to retrieve results once ready.
    """
    try:
        # Resolve coordinates
        if resource_id:
            sub_id, rg, mname = _parse_resource_id(resource_id)
        else:
            sub_id, rg, mname = subscription_id, resource_group, machine_name

        resolved_vm_type = _resolve_vm_type(resource_id, vm_type)

        if resolved_vm_type == "azure-vm":
            assess_url = (
                f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.Compute/virtualMachines/{mname}"
                f"/assessPatches?api-version={_AVM_ASSESS_API_VERSION}"
            )
            log_label = "Azure VM"
        else:
            assess_url = (
                f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.HybridCompute/machines/{mname}"
                f"/assessPatches?api-version={_ASSESS_API_VERSION}"
            )
            log_label = "Arc VM"

        token = await _get_arm_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        logger.info("Triggering assessPatches for %s: %s / %s / %s", log_label, sub_id, rg, mname)

        async with aiohttp.ClientSession() as session:
            async with session.post(assess_url, headers=headers, json={}) as resp:
                if resp.status == 200:
                    logger.info("assessPatches returned 200 synchronously for %s", mname)
                    return {
                        "success": True,
                        "triggered": True,
                        "machine": mname,
                        "subscription_id": sub_id,
                        "resource_group": rg,
                        "vm_type": resolved_vm_type,
                        "message": f"Assessment completed synchronously for {log_label} '{mname}'",
                    }

                if resp.status != 202:
                    error_text = await resp.text()
                    logger.error("assessPatches failed %s for %s: %s", resp.status, mname, error_text)
                    return {
                        "success": False,
                        "error": f"assessPatches failed ({resp.status}): {error_text[:500]}",
                    }

                operation_url = (
                    resp.headers.get("Azure-AsyncOperation")
                    or resp.headers.get("Location")
                    or ""
                )

        logger.info("assessPatches triggered for %s %s/%s/%s", log_label, sub_id, rg, mname)

        return {
            "success": True,
            "triggered": True,
            "machine": mname,
            "subscription_id": sub_id,
            "resource_group": rg,
            "vm_type": resolved_vm_type,
            "operation_url": operation_url,
            "message": f"Assessment triggered for {log_label} '{mname}' (completes in 1-3 min)",
        }
    except Exception as exc:
        logger.error("assess_vm_patches failed: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def get_assessment_result(
    machine_name: Annotated[str, "Machine name"],
    subscription_id: Annotated[str, "Azure subscription ID"],
    vm_type: Annotated[str, "'arc' or 'azure-vm'"] = "arc",
) -> Dict[str, Any]:
    """
    Fetch the latest assessment result for a single machine from Azure Resource Graph.

    Use this after triggering assess_vm_patches to retrieve completed assessment data.
    Returns patch summary with classifications and reboot requirements.
    """
    try:
        resolved_vm_type = _resolve_vm_type(None, vm_type)

        if resolved_vm_type == "azure-vm":
            summary_type = "microsoft.compute/virtualmachines/patchassessmentresults"
            patches_type = "microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches"
            provider = "Microsoft.Compute/virtualMachines"
        else:
            summary_type = "microsoft.hybridcompute/machines/patchassessmentresults"
            patches_type = "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches"
            provider = "Microsoft.HybridCompute/machines"

        safe_name = machine_name.replace("'", "''")

        summary_kql = f"""
patchassessmentresources
| where type =~ '{summary_type}'
| extend machineName = tostring(split(id, '/')[8])
| where machineName =~ '{safe_name}'
| extend props = properties
| project machineName, resourceGroup, subscriptionId,
    status = tostring(props.status),
    lastModified = tostring(coalesce(props.lastModifiedDateTimeUTC, props.lastModifiedDateTime)),
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount = toint(props.otherPatchCount),
    osType = tostring(props.osType),
    rebootPending = tobool(props.rebootPending)
| order by lastModified desc
| take 1
"""

        patches_kql = f"""
patchassessmentresources
| where type =~ '{patches_type}'
| extend machineName = tostring(split(id, '/')[8])
| where machineName =~ '{safe_name}'
| extend props = properties
| project machineName,
    patchName = tostring(props.patchName),
    kbId = tostring(props.kbId),
    classifications = tostring(props.classifications),
    rebootBehavior = tostring(props.rebootBehavior),
    assessmentState = tostring(props.assessmentState),
    publishedDate = tostring(props.publishedDate)
"""

        summary_rows, patches_rows = await asyncio.gather(
            _query_arg(summary_kql, [subscription_id]),
            _query_arg(patches_kql, [subscription_id]),
        )

        if not summary_rows:
            return {
                "success": True,
                "found": False,
                "machine_name": machine_name,
                "vm_type": resolved_vm_type,
                "message": f"No assessment found for '{machine_name}' (wait 1-3 min after triggering)",
            }

        row = summary_rows[0]
        patches = [
            {
                "patchName": r.get("patchName"),
                "kbId": r.get("kbId"),
                "classifications": _parse_arg_list(r.get("classifications")),
                "rebootBehavior": r.get("rebootBehavior"),
                "assessmentState": r.get("assessmentState"),
                "publishedDate": r.get("publishedDate"),
            }
            for r in patches_rows
        ]

        crit = row.get("criticalCount") or 0
        other = row.get("otherCount") or 0
        if (crit == 0 and other == 0) and patches:
            for p in patches:
                cls = [c.lower() for c in (p.get("classifications") or [])]
                if "critical" in cls or "security" in cls:
                    crit += 1
                else:
                    other += 1

        rg = row.get("resourceGroup") or ""
        resource_id = f"/subscriptions/{subscription_id}/resourceGroups/{rg}/providers/{provider}/{machine_name}"

        return {
            "success": True,
            "found": True,
            "machine_name": machine_name,
            "resource_id": resource_id,
            "resource_group": rg,
            "subscription_id": row.get("subscriptionId") or subscription_id,
            "os_type": row.get("osType"),
            "reboot_pending": row.get("rebootPending"),
            "vm_type": resolved_vm_type,
            "patches": {
                "available_patches": patches,
                "critical_and_security_count": crit,
                "other_count": other,
                "total_count": len(patches) or (crit + other),
                "last_assessed": row.get("lastModified"),
                "status": row.get("status"),
                "source": "resource_graph",
            },
        }
    except Exception as exc:
        logger.error("get_assessment_result failed: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def install_vm_patches(
    machine_name: Annotated[str, "Machine name"],
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[str, "Resource group name"],
    classifications: Annotated[List[str], "Patch classifications to install"] = ["Critical", "Security"],
    vm_type: Annotated[str, "'arc' or 'azure-vm'"] = "arc",
    resource_id: Annotated[Optional[str], "Full ARM resource ID (overrides other params)"] = None,
    kb_numbers_to_include: Annotated[List[str], "Specific KB IDs to include (Windows)"] = [],
    kb_numbers_to_exclude: Annotated[List[str], "KB IDs to exclude (Windows)"] = [],
    reboot_setting: Annotated[str, "Reboot behavior: IfRequired | NeverReboot | AlwaysReboot"] = "IfRequired",
    maximum_duration: Annotated[str, "ISO 8601 duration (e.g., PT2H)"] = "PT2H",
    os_type: Annotated[Optional[str], "Force OS type: Windows | Linux"] = None,
    package_names: Annotated[Optional[List[str]], "Linux package name masks to install (e.g. ['openssl', 'curl*'])"] = None,
    os_family: Annotated[Optional[str], "Linux OS family hint: 'ubuntu' | 'rhel' | 'centos'"] = None,
) -> Dict[str, Any]:
    """
    Trigger patch installation on an Azure VM or Arc server.

    For Windows VMs, pass os_type='Windows' and use kb_numbers_to_include/kb_numbers_to_exclude.
    For Linux VMs, pass os_type='Linux' and package_names instead of kb_numbers.
    os_family ('ubuntu', 'rhel', 'centos') is an optional hint for Linux targets.

    Returns immediately with operation_url for status polling.
    Installation can take 10-30+ minutes depending on patch count and reboot requirements.
    Use get_install_status to monitor progress.
    """
    try:
        # Resolve coordinates
        if resource_id:
            sub_id, rg, mname = _parse_resource_id(resource_id)
        else:
            sub_id, rg, mname = subscription_id, resource_group, machine_name

        resolved_vm_type = _resolve_vm_type(resource_id, vm_type)
        resolved_os_type = os_type or "Windows"  # default

        if resolved_vm_type == "azure-vm":
            install_url = (
                f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.Compute/virtualMachines/{mname}"
                f"/installPatches?api-version={_AVM_ASSESS_API_VERSION}"
            )
            log_label = "Azure VM"
        else:
            install_url = (
                f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
                f"/providers/Microsoft.HybridCompute/machines/{mname}"
                f"/installPatches?api-version={_ASSESS_API_VERSION}"
            )
            log_label = "Arc VM"

        # Build OS-specific parameters
        if resolved_os_type.lower() == "linux":
            # Prefer package_names (Linux-native); fall back to kb_numbers_to_include
            pkg_include = package_names or kb_numbers_to_include or []
            pkg_exclude = kb_numbers_to_exclude
            os_params = {
                "linuxParameters": {
                    "classificationsToInclude": classifications,
                    "packageNameMasksToInclude": pkg_include,
                    "packageNameMasksToExclude": pkg_exclude,
                }
            }
        else:
            os_params = {
                "windowsParameters": {
                    "classificationsToInclude": classifications,
                    "kbNumbersToInclude": kb_numbers_to_include,
                    "kbNumbersToExclude": kb_numbers_to_exclude,
                    "excludeKbsRequiringReboot": False,
                }
            }

        request_body = {
            "maximumDuration": maximum_duration,
            "rebootSetting": reboot_setting,
            **os_params,
        }

        token = await _get_arm_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        logger.info(
            "Triggering installPatches for %s: %s / %s / %s (os_type=%s, classes=%s)",
            log_label, sub_id, rg, mname, resolved_os_type, classifications,
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(install_url, headers=headers, json=request_body) as resp:
                if resp.status == 200:
                    result_body = await resp.json(content_type=None)
                    return {
                        "success": True,
                        "machine": mname,
                        "status": "Completed",
                        "data": _extract_install_result(result_body),
                    }

                if resp.status != 202:
                    err_text = await resp.text()
                    logger.error("installPatches failed %s for %s: %s", resp.status, mname, err_text)
                    return {
                        "success": False,
                        "error": f"installPatches failed ({resp.status}): {err_text[:500]}",
                    }

                operation_url = (
                    resp.headers.get("Azure-AsyncOperation")
                    or resp.headers.get("Location")
                )
                if not operation_url:
                    return {
                        "success": False,
                        "error": "No Azure-AsyncOperation or Location header in 202 response",
                    }

        logger.info("Install operation started for %s: %s", mname, operation_url)

        return {
            "success": True,
            "machine": mname,
            "subscription_id": sub_id,
            "resource_group": rg,
            "status": "InProgress",
            "operation_url": operation_url,
            "message": "Patch installation started. Poll with get_install_status.",
        }
    except Exception as exc:
        logger.error("install_vm_patches failed: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def get_install_status(
    operation_url: Annotated[str, "Azure-AsyncOperation URL from install_vm_patches"],
) -> Dict[str, Any]:
    """
    Check the status of an in-progress or completed patch installation.

    Pass the operation_url returned by install_vm_patches.
    Returns current status and detailed results when completed.
    """
    try:
        token = await _get_arm_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(operation_url, headers=headers) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    return {
                        "success": False,
                        "error": f"Failed to poll install status ({resp.status}): {err_text[:500]}",
                    }
                body = await resp.json(content_type=None)

        raw_status = (body.get("status") or "Unknown")
        is_done = raw_status.lower() in ("succeeded", "failed", "canceled", "cancelled")

        result = {
            "success": True,
            "status": raw_status,
            "is_done": is_done,
            "data": _extract_install_result(body) if is_done else None,
            "error": body.get("error"),
        }
        return result
    except Exception as exc:
        logger.error("get_install_status failed: %s", exc)
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def get_vm_patch_summary(
    subscription_id: Annotated[str, "Azure subscription ID"],
    resource_group: Annotated[Optional[str], "Filter by resource group (optional)"] = None,
) -> Dict[str, Any]:
    """
    Get a consolidated patch status summary for all VMs/Arc servers in the subscription.

    Returns compliance stats: total VMs, compliant (no critical patches), non-compliant, unassessed.
    Use this for reporting and dashboard views.
    """
    try:
        # Query assessments for both Arc and Azure VMs
        arc_kql = """
patchassessmentresources
| where type =~ 'microsoft.hybridcompute/machines/patchassessmentresults'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, resourceGroup,
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount = toint(props.otherPatchCount),
    vmType = 'arc'
"""

        avm_kql = """
patchassessmentresources
| where type =~ 'microsoft.compute/virtualmachines/patchassessmentresults'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, resourceGroup,
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount = toint(props.otherPatchCount),
    vmType = 'azure-vm'
"""

        arc_rows, avm_rows = await asyncio.gather(
            _query_arg(arc_kql, [subscription_id]),
            _query_arg(avm_kql, [subscription_id]),
        )

        all_rows = arc_rows + avm_rows

        if resource_group:
            all_rows = [r for r in all_rows if r.get("resourceGroup") == resource_group]

        total_vms = len(all_rows)
        compliant = sum(1 for r in all_rows if (r.get("criticalCount") or 0) == 0)
        non_compliant = total_vms - compliant

        total_critical_patches = sum(r.get("criticalCount") or 0 for r in all_rows)
        total_other_patches = sum(r.get("otherCount") or 0 for r in all_rows)

        return {
            "success": True,
            "data": {
                "total_vms": total_vms,
                "compliant_vms": compliant,
                "non_compliant_vms": non_compliant,
                "compliance_percentage": round((compliant / total_vms * 100) if total_vms > 0 else 0, 1),
                "total_critical_patches": total_critical_patches,
                "total_other_patches": total_other_patches,
                "subscription_id": subscription_id,
                "resource_group": resource_group,
            },
        }
    except Exception as exc:
        logger.error("get_vm_patch_summary failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Server Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Azure Patch Management MCP Server")
    _subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    mcp.run()
