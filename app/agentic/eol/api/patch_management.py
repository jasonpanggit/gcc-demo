"""
Patch Management API Module

Provides endpoints for assessing and installing patches on Arc-enabled servers
using the Azure HybridCompute assessPatches / installPatches REST APIs.

Read endpoints use PatchRepository (PostgreSQL) for data retrieval.
Write endpoints (assess, install, poll) use ARM REST for live Azure operations.

Endpoints:
    GET  /api/patch-management/machines          - List VMs with patch assessment data (PG)
    GET  /api/patch-management/arc-vms          - List Arc VMs from OS inventory (legacy)
    GET  /api/patch-management/arg-patch-data    - Pre-existing assessments + patches from Resource Graph
    POST /api/patch-management/assess            - Trigger patch assessment (fire-and-forget)
    GET  /api/patch-management/last-assessment   - Fetch latest assessment for a single VM from ARG
    GET  /api/patch-management/results/{name}    - Get available patches for a VM (PG)
    POST /api/patch-management/install           - Trigger patch installation (non-blocking)
    GET  /api/patch-management/install-status    - Poll an in-progress install operation
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, Field

from utils.config import config
from utils.normalization import normalize_os_record
from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint, write_endpoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patch-management", tags=["Patch Management"])

# Azure ARM base URL and API versions
_ARM_BASE = "https://management.azure.com"
_ASSESS_API_VERSION     = "2022-12-27"   # HybridCompute (Arc)
_AVM_ASSESS_API_VERSION = "2023-03-01"   # Compute (Azure VM)
_POLL_INTERVAL_SECONDS = 4
_POLL_MAX_SECONDS = 180  # 3 minutes max wait


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

# NOTE: We intentionally do NOT use Pydantic body injection for the mutating
# endpoints below.  The @write_endpoint/@wraps decorator chain combined with
# `from __future__ import annotations` and Pydantic v2 can prevent FastAPI
# from resolving the body parameter type at route-registration time, producing
# a 422 before the function body is even reached.  Reading the raw Request and
# parsing JSON ourselves is fully equivalent and 100% reliable.

class AssessRequest(BaseModel):
    """Used for internal validation only – not injected by FastAPI."""
    machine_name: Optional[str] = Field(None)
    subscription_id: Optional[str] = Field(None)
    resource_group: Optional[str] = Field(None)
    resource_id: Optional[str] = Field(None)
    # 'arc' | 'azure-vm' – inferred from resource_id when omitted
    vm_type: Optional[str] = Field(None)


class InstallRequest(BaseModel):
    """Used for internal validation only – not injected by FastAPI."""
    machine_name: Optional[str] = Field(None)
    subscription_id: Optional[str] = Field(None)
    resource_group: Optional[str] = Field(None)
    resource_id: Optional[str] = Field(None)
    vm_type: Optional[str] = Field(None, description="'arc' | 'azure-vm'")
    classifications: List[str] = Field(
        default=["Critical", "Security"],
        description="Patch classifications to install (Critical, Security, UpdateRollup, "
                    "FeaturePack, ServicePack, Definition, Tools, Updates)",
    )
    kb_numbers_to_include: List[str] = Field(
        default=[],
        description="Specific KB IDs / package names to install",
    )
    kb_numbers_to_exclude: List[str] = Field(
        default=[],
        description="KB IDs / package name masks to exclude",
    )
    reboot_setting: str = Field(
        default="IfRequired",
        description="Reboot behaviour: IfRequired | NeverReboot | AlwaysReboot",
    )
    maximum_duration: str = Field(
        default="PT2H",
        description="ISO 8601 duration for maximum install window (e.g. PT1H, PT2H, PT4H)",
    )
    os_type: Optional[str] = Field(
        None,
        description="Force OS type: Windows | Linux. Auto-detected from inventory when absent.",
    )
    # Linux-specific fields (None for Windows)
    package_names_to_include: Optional[List[str]] = Field(
        None,
        description="Linux package names to install (e.g. ['openssl', 'curl'])",
    )
    package_names_to_exclude: Optional[List[str]] = Field(
        None,
        description="Linux package name masks to exclude",
    )
    os_family: Optional[str] = Field(
        None,
        description="Linux OS family hint: 'ubuntu' | 'rhel' | 'centos'",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_arm_token() -> str:
    """Get an access token for management.azure.com.

    Uses the project-standard SP env vars (AZURE_SP_CLIENT_ID /
    AZURE_SP_CLIENT_SECRET / AZURE_TENANT_ID) when present; falls back to
    DefaultAzureCredential (managed identity / CLI) otherwise.
    """
    try:
        import os
        from azure.identity.aio import DefaultAzureCredential, ClientSecretCredential

        sp_client_id     = os.getenv("AZURE_SP_CLIENT_ID")
        sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id        = os.getenv("AZURE_TENANT_ID") or config.azure.tenant_id

        if sp_client_id and sp_client_secret and tenant_id:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=sp_client_id,
                client_secret=sp_client_secret,
            )
            logger.debug("ARM token: using injected SP %s", sp_client_id)
        else:
            credential = DefaultAzureCredential()
            logger.debug("ARM token: using DefaultAzureCredential")

        token = await credential.get_token("https://management.azure.com/.default")
        await credential.close()
        return token.token
    except Exception as exc:
        logger.error("Failed to acquire ARM token: %s", exc)
        raise HTTPException(status_code=500, detail=f"Azure auth error: {exc}") from exc


def _parse_resource_id(resource_id: str) -> tuple[str, str, str]:
    """Extract (subscription_id, resource_group, machine_name) from a resource ID."""
    parts = resource_id.strip("/").split("/")
    # Expected: subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.HybridCompute/machines/{name}
    try:
        sub = parts[parts.index("subscriptions") + 1]
        rg = parts[parts.index("resourceGroups") + 1]
        name = parts[-1]
        return sub, rg, name
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Cannot parse resource ID: {resource_id}") from exc


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
                logger.debug("Poll %s: empty response body (HTTP %s), retrying", operation_label, resp.status)
                continue
            try:
                import json as _json
                body = _json.loads(raw_text)
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
                raise HTTPException(status_code=502, detail=f"{operation_label} failed: {error}")
            # Still InProgress / empty status – keep polling

    raise HTTPException(
        status_code=504,
        detail=f"{operation_label} timed out after {_POLL_MAX_SECONDS // 60} minutes",
    )


def _extract_install_result(operation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract install outcome from a completed installPatches operation result."""
    props = operation_result.get("properties") or {}
    return {
        "status": operation_result.get("status", "Unknown"),
        "installed_patch_count":    props.get("installedPatchCount", 0) or 0,
        "failed_patch_count":       props.get("failedPatchCount", 0) or 0,
        "pending_patch_count":      props.get("pendingPatchCount", 0) or 0,
        "not_selected_patch_count": props.get("notSelectedPatchCount", 0) or 0,
        "excluded_patch_count":     props.get("excludedPatchCount", 0) or 0,
        "reboot_status":            props.get("rebootStatus"),
        "maintenance_window_exceeded": props.get("maintenanceWindowExceeded", False),
        "start_date_time":          props.get("startDateTime"),
        "last_modified":            props.get("lastModifiedDateTime"),
        "patches":                  props.get("patches", []),
        "error":                    props.get("error"),
    }


async def _query_arg(query: str, subscription_ids: List[str]) -> List[Dict[str, Any]]:
    """Execute a Resource Graph query via executor (SDK is synchronous)."""
    try:
        from azure.mgmt.resourcegraph import ResourceGraphClient as SyncARGClient
        from azure.mgmt.resourcegraph.models import (
            QueryRequest as ARGQueryRequest,
            QueryRequestOptions as ARGQueryRequestOptions,
        )
        from azure.identity import DefaultAzureCredential as SyncDefaultCred
        from azure.identity import ClientSecretCredential as SyncSPCred
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"azure-mgmt-resourcegraph / azure-identity not installed: {exc}",
        ) from exc

    import os

    sp_client_id     = os.getenv("AZURE_SP_CLIENT_ID")
    sp_client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
    tenant_id        = os.getenv("AZURE_TENANT_ID") or config.azure.tenant_id

    if sp_client_id and sp_client_secret and tenant_id:
        cred = SyncSPCred(tenant_id=tenant_id, client_id=sp_client_id, client_secret=sp_client_secret)
    else:
        cred = SyncDefaultCred()

    graph_client = SyncARGClient(cred)
    all_rows: List[Dict[str, Any]] = []
    skip_token: Optional[str] = None
    loop = asyncio.get_event_loop()

    while True:
        def _run(st=skip_token):
            opts = ARGQueryRequestOptions(result_format="objectArray", top=1000)
            if st:
                opts.skip_token = st
            req = ARGQueryRequest(subscriptions=subscription_ids, query=query, options=opts)
            return graph_client.resources(req)

        response = await loop.run_in_executor(None, _run)
        data = response.data if hasattr(response, "data") else []
        all_rows.extend(data if isinstance(data, list) else [])
        skip_token = getattr(response, "skip_token", None)
        if not skip_token:
            break

    return all_rows


def _resolve_vm_type(resource_id: Optional[str], vm_type: Optional[str]) -> str:
    """Return 'arc' or 'azure-vm' based on resource_id or explicit hint."""
    if vm_type and vm_type.lower() in ("arc", "azure-vm"):
        return vm_type.lower()
    rid = (resource_id or "").lower()
    if "/microsoft.compute/virtualmachines/" in rid:
        return "azure-vm"
    return "arc"


# ---------------------------------------------------------------------------
# Helpers for machine listing
# ---------------------------------------------------------------------------

def _normalize_machine_os_fields(machine: Dict[str, Any]) -> Dict[str, Any]:
    """Apply centralized OS normalization to a machine inventory row."""
    if not isinstance(machine, dict):
        return machine
    normalized = normalize_os_record(
        machine.get("os_name"),
        machine.get("os_version"),
        machine.get("os_type"),
    )
    machine.setdefault("raw_os_name", normalized.get("raw_os_name"))
    machine.setdefault("raw_os_version", normalized.get("raw_os_version"))
    machine["os_name"] = normalized["os_name"]
    machine["os_version"] = normalized.get("os_version")
    machine["normalized_os_name"] = normalized.get("normalized_os_name")
    machine["normalized_os_version"] = normalized.get("normalized_os_version")
    machine["os_type"] = normalized.get("os_type") or machine.get("os_type")
    return machine


async def _list_machines_inventory(days: int) -> Dict[str, Any]:
    """
    Return a unified list of both Azure VMs (from Resource Inventory) and
    Arc-enabled servers (from OS Inventory), each tagged with vm_type.
    EOL enrichment is intentionally omitted — the client fetches it per-card.
    """
    machines: List[Dict[str, Any]] = []

    # ── Arc-enabled servers from OS inventory ──────────────────────────────
    try:
        from main import get_eol_orchestrator
        orchestrator = get_eol_orchestrator()
        os_result = await orchestrator.agents["os_inventory"].get_os_inventory(days=days)
        all_os: List[Dict[str, Any]] = (
            os_result.get("data", []) if isinstance(os_result, dict) else []
        )
        for item in all_os:
            if (
                str(item.get("computer_type", "")).lower() == "arc-enabled server"
                or "/microsoft.hybridcompute/machines/" in str(item.get("resource_id", "")).lower()
            ):
                machines.append(_normalize_machine_os_fields({**item, "vm_type": "arc"}))
    except Exception as exc:
        logger.warning("Failed to fetch OS inventory for Arc VMs: %s", exc)

    # ── Azure VMs from Resource Inventory ─────────────────────────────────
    try:
        from utils.resource_inventory_client import get_resource_inventory_client
        inv_client = get_resource_inventory_client()
        azure_vms = await inv_client.get_resources(
            "Microsoft.Compute/virtualMachines",
            subscription_id=config.azure.subscription_id,
        )
        arc_rid_set = {
            str(m.get("resource_id", "")).lower()
            for m in machines
        }
        for vm in azure_vms:
            sp  = vm.get("selected_properties") or {}
            rid = str(vm.get("resource_id") or vm.get("id") or "").lower()
            if not rid or rid in arc_rid_set:
                continue
            vm_name = vm.get("resource_name") or vm.get("name")
            normalized_os = normalize_os_record(
                sp.get("os_image") or sp.get("os_type") or vm.get("os_name") or "",
                vm.get("os_version"),
                sp.get("os_type") or vm.get("os_type"),
            )
            vm_record = {
                "computer":               vm_name,
                "name":                   vm_name,
                "os_name":                normalized_os["os_name"],
                "os_version":             normalized_os.get("os_version"),
                "os_type":                normalized_os.get("os_type"),
                "raw_os_name":            normalized_os.get("raw_os_name"),
                "raw_os_version":         normalized_os.get("raw_os_version"),
                "normalized_os_name":     normalized_os.get("normalized_os_name"),
                "normalized_os_version":  normalized_os.get("normalized_os_version"),
                "resource_id":            vm.get("resource_id") or vm.get("id"),
                "subscription_id":        vm.get("subscription_id") or vm.get("subscriptionId") or config.azure.subscription_id,
                "resource_group":         vm.get("resource_group") or vm.get("resourceGroup"),
                "location":               vm.get("location"),
                "vm_size":                sp.get("vm_size") or vm.get("vm_size"),
                "vm_type":                "azure-vm",
            }
            machines.append(_normalize_machine_os_fields(vm_record))

    except Exception as exc:
        logger.warning("Failed to fetch Azure VMs from resource inventory: %s", exc)

    arc_count = sum(1 for m in machines if m.get("vm_type") == "arc")
    avm_count  = sum(1 for m in machines if m.get("vm_type") == "azure-vm")
    logger.info("Machines list: %d Arc, %d Azure VM", arc_count, avm_count)

    return {
        "success":       True,
        "data":          machines,
        "count":         len(machines),
        "arc_count":     arc_count,
        "azure_vm_count": avm_count,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/machines", response_model=StandardResponse)
@readonly_endpoint(agent_name="patch_mgmt_machines", timeout_seconds=60)
async def list_machines(
    days: int = Query(90, description="OS-inventory look-back window for Arc VMs"),
):
    """
    List Azure VMs and Arc-enabled servers for patch management.

    Fetches Arc servers from OS inventory (Log Analytics) and Azure VMs
    from Resource Inventory. EOL enrichment is performed client-side.
    """
    return await _list_machines_inventory(days=days)


@router.get("/arc-vms", response_model=StandardResponse)
@readonly_endpoint(agent_name="patch_mgmt_arc_vms", timeout_seconds=30)
async def list_arc_vms(days: int = Query(90, description="Look-back window for OS inventory")):
    """
    Return Arc-enabled servers from the OS inventory.

    Filters the OS heartbeat inventory to machines whose computer_type is
    'Arc-enabled Server' or whose resource_id contains
    '/microsoft.hybridcompute/machines/'.
    """
    try:
        from main import get_eol_orchestrator
        orchestrator = get_eol_orchestrator()
        os_result = await orchestrator.agents["os_inventory"].get_os_inventory(days=days)
    except Exception as exc:
        logger.error("Failed to fetch OS inventory: %s", exc)
        return {"success": False, "error": str(exc), "data": [], "count": 0}

    all_items: List[Dict[str, Any]] = os_result.get("data", []) if isinstance(os_result, dict) else []

    arc_vms = [
        item for item in all_items
        if (
            str(item.get("computer_type", "")).lower() == "arc-enabled server"
            or "/microsoft.hybridcompute/machines/" in str(item.get("resource_id", "")).lower()
        )
    ]

    return {
        "success": True,
        "data": arc_vms,
        "count": len(arc_vms),
        "total_os_inventory": len(all_items),
    }


@router.post("/assess")
@write_endpoint(agent_name="patch_mgmt_assess", timeout_seconds=30)
async def assess_patches(request: Request):
    """
    Fire-and-forget: trigger an Azure assessPatches call and return immediately.

    Returns { triggered: true, message } as soon as Azure accepts the request
    (HTTP 202). Does NOT poll for results. Use GET /last-assessment to fetch
    the completed assessment from Azure Resource Graph once it is ready
    (typically 1–3 minutes).

    Body (JSON):
        machine_name    – machine name (required unless resource_id provided)
        subscription_id – override subscription (optional)
        resource_group  – override resource group (optional)
        resource_id     – full ARM resource ID (overrides the above)
        vm_type         – 'arc' | 'azure-vm' (inferred from resource_id when omitted)
    """
    # Parse body manually to avoid decorator/@wraps/Pydantic v2 registration issues
    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    body = AssessRequest.model_validate(raw)

    if not body.machine_name and not body.resource_id:
        raise HTTPException(
            status_code=400,
            detail="machine_name (or resource_id) is required",
        )

    # Resolve subscription / resource-group / machine name
    if body.resource_id:
        try:
            sub_id, rg, machine_name = _parse_resource_id(body.resource_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        sub_id = body.subscription_id or config.azure.subscription_id
        rg = body.resource_group or config.azure.resource_group_name
        machine_name = body.machine_name  # type: ignore[assignment]  # guarded above

    if not sub_id or not rg or not machine_name:
        raise HTTPException(
            status_code=400,
            detail="subscription_id, resource_group, and machine_name are required",
        )

    # Route to the correct ARM provider based on vm_type
    vm_type = _resolve_vm_type(body.resource_id, body.vm_type)
    if vm_type == "azure-vm":
        assess_url = (
            f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
            f"/providers/Microsoft.Compute/virtualMachines/{machine_name}"
            f"/assessPatches?api-version={_AVM_ASSESS_API_VERSION}"
        )
        log_label = "Azure VM"
    else:
        assess_url = (
            f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
            f"/providers/Microsoft.HybridCompute/machines/{machine_name}"
            f"/assessPatches?api-version={_ASSESS_API_VERSION}"
        )
        log_label = "Arc VM"

    token = await _get_arm_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    logger.info("Triggering assessPatches for %s: %s / %s / %s", log_label, sub_id, rg, machine_name)

    async with aiohttp.ClientSession() as session:
        async with session.post(assess_url, headers=headers, json={}) as resp:
            if resp.status == 200:
                # Rare synchronous completion – return triggered status (no polling)
                logger.info("assessPatches returned 200 synchronously for %s", machine_name)
                return {
                    "success":  True,
                    "triggered": True,
                    "machine":  machine_name,
                    "subscription_id": sub_id,
                    "resource_group":  rg,
                    "vm_type":  vm_type,
                    "message":  f"Assessment accepted for {log_label} '{machine_name}'. Use 'View Last Assessment' to see results.",
                }

            if resp.status != 202:
                error_text = await resp.text()
                logger.error(
                    "assessPatches POST failed %s for %s: %s",
                    resp.status, machine_name, error_text,
                )
                raise HTTPException(
                    status_code=resp.status,
                    detail=f"assessPatches failed ({resp.status}): {error_text[:500]}",
                )

            # 202 – accepted; capture the operation URL for reference but return immediately
            operation_url = (
                resp.headers.get("Azure-AsyncOperation")
                or resp.headers.get("Location")
                or ""
            )

    logger.info(
        "assessPatches triggered (fire-and-forget) for %s %s/%s/%s – operation: %s",
        log_label, sub_id, rg, machine_name, operation_url,
    )

    return {
        "success":       True,
        "triggered":     True,
        "machine":       machine_name,
        "subscription_id": sub_id,
        "resource_group":  rg,
        "vm_type":       vm_type,
        "operation_url": operation_url,
        "message": (
            f"Assessment triggered for {log_label} '{machine_name}'. "
            "Azure is now scanning this machine — it typically completes in 1–3 minutes. "
            "Use 'View Last Assessment' to load the results once ready."
        ),
    }


# ---------------------------------------------------------------------------
# Last-assessment endpoint (ARG query for a single machine)
# ---------------------------------------------------------------------------

@router.get("/last-assessment")  # no response_model — returns custom shape with 'found', 'patches', etc.
@readonly_endpoint(agent_name="patch_mgmt_last_assessment", timeout_seconds=30)
async def get_last_assessment(
    machine_name: str = Query(..., description="Machine name to look up"),
    subscription_id: Optional[str] = Query(None),
    vm_type: str = Query("arc", description="'arc' | 'azure-vm'"),
):
    """
    Fetch the latest assessment for a single machine from Azure Resource Graph.

    Runs targeted KQL queries against patchassessmentresources, filtered by
    machine name and vm_type, and returns the summary + patch list.
    """
    sub_id = subscription_id or config.azure.subscription_id
    if not sub_id:
        raise HTTPException(status_code=400, detail="subscription_id is required")
    if not machine_name:
        raise HTTPException(status_code=400, detail="machine_name is required")

    resolved_vm_type = _resolve_vm_type(None, vm_type)
    if resolved_vm_type == "azure-vm":
        summary_type = "microsoft.compute/virtualmachines/patchassessmentresults"
        patches_type = "microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches"
        provider     = "Microsoft.Compute/virtualMachines"
    else:
        summary_type = "microsoft.hybridcompute/machines/patchassessmentresults"
        patches_type = "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches"
        provider     = "Microsoft.HybridCompute/machines"

    safe_name = machine_name.replace("'", "''")

    summary_kql = f"""
patchassessmentresources
| where type =~ '{summary_type}'
| extend machineName = tostring(split(id, '/')[8])
| where machineName =~ '{safe_name}'
| extend props = properties
| project machineName, resourceGroup, subscriptionId,
    status        = tostring(props.status),
    lastModified  = tostring(coalesce(props.lastModifiedDateTimeUTC, props.lastModifiedDateTime)),
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount    = toint(props.otherPatchCount),
    osType        = tostring(props.osType),
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
    patchName = tostring(props.patchName), kbId = tostring(props.kbId),
    classifications = tostring(props.classifications),
    rebootBehavior  = tostring(props.rebootBehavior),
    assessmentState = tostring(props.assessmentState),
    publishedDate   = tostring(props.publishedDate)
"""

    try:
        summary_rows, patches_rows = await asyncio.gather(
            _query_arg(summary_kql, [sub_id]),
            _query_arg(patches_kql, [sub_id]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("last-assessment ARG query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Resource Graph query failed: {exc}") from exc

    if not summary_rows:
        return {
            "success": True,
            "found": False,
            "machine_name": machine_name,
            "vm_type": resolved_vm_type,
            "message": (
                f"No assessment found in Resource Graph for '{machine_name}'. "
                "The assessment may still be in progress (wait 1–3 minutes) or has not been run yet."
            ),
        }

    row = summary_rows[0]
    patches = [
        {
            "patchName":       r.get("patchName"),
            "kbId":            r.get("kbId"),
            "classifications": _parse_arg_list(r.get("classifications")),
            "rebootBehavior":  r.get("rebootBehavior"),
            "assessmentState": r.get("assessmentState"),
            "publishedDate":   r.get("publishedDate"),
        }
        for r in patches_rows
    ]

    crit  = row.get("criticalCount") or 0
    other = row.get("otherCount") or 0
    if (crit == 0 and other == 0) and patches:
        for p in patches:
            cls = [c.lower() for c in (p.get("classifications") or [])]
            if "critical" in cls or "security" in cls:
                crit += 1
            else:
                other += 1

    rg = row.get("resourceGroup") or ""
    resource_id = (
        f"/subscriptions/{sub_id}/resourceGroups/{rg}"
        f"/providers/{provider}/{machine_name}"
    )

    return {
        "success":      True,
        "found":        True,
        "machine_name": machine_name,
        "resource_id":  resource_id,
        "resource_group": rg,
        "subscription_id": row.get("subscriptionId") or sub_id,
        "os_type":      row.get("osType"),
        "reboot_pending": row.get("rebootPending"),
        "vm_type":      resolved_vm_type,
        "patches": {
            "available_patches":           patches,
            "critical_and_security_count": crit,
            "other_count":                 other,
            "total_count":                 len(patches) or (crit + other),
            "last_assessed":               row.get("lastModified"),
            "status":                      row.get("status"),
            "source":                      "resource_graph",
        },
    }


# ---------------------------------------------------------------------------
# Install endpoints
# ---------------------------------------------------------------------------

@router.post("/install")
@write_endpoint(agent_name="patch_mgmt_install", timeout_seconds=60)
async def install_patches(request: Request):
    """
    Trigger an Azure installPatches call for the given Arc-enabled machine.

    Returns immediately with an ``operation_url`` that the caller should poll
    via GET /api/patch-management/install-status.

    Body (JSON):
        machine_name          – Arc machine name
        resource_id           – full ARM resource ID (overrides machine_name coords)
        subscription_id       – override subscription
        resource_group        – override resource group
        classifications       – list of patch classifications (default: Critical, Security)
        kb_numbers_to_include – KB numbers / package masks to include
        kb_numbers_to_exclude – KB numbers / package masks to exclude
        reboot_setting        – IfRequired | NeverReboot | AlwaysReboot
        maximum_duration      – ISO 8601 duration (default PT2H)
        os_type               – Windows | Linux (auto-detected when omitted)
    """
    try:
        raw = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    body = InstallRequest.model_validate(raw)

    if not body.machine_name and not body.resource_id:
        raise HTTPException(
            status_code=400,
            detail="machine_name (or resource_id) is required",
        )

    # Resolve coordinates
    if body.resource_id:
        try:
            sub_id, rg, machine_name = _parse_resource_id(body.resource_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        sub_id       = body.subscription_id or config.azure.subscription_id
        rg           = body.resource_group  or config.azure.resource_group_name
        machine_name = body.machine_name  # type: ignore[assignment]  # guarded above

    if not sub_id or not rg or not machine_name:
        raise HTTPException(
            status_code=400,
            detail="subscription_id, resource_group, and machine_name are required",
        )

    # Detect OS type – use param when supplied, otherwise default to Windows
    os_type = body.os_type or "Windows"  # sensible default for Arc-enrolled Windows servers

    # Validate Linux requirements before hitting the ARM API
    if os_type.lower() == "linux":
        if not body.package_names_to_include and not body.kb_numbers_to_include:
            raise HTTPException(
                status_code=400,
                detail="package_names_to_include required for Linux VMs",
            )

    # Route to the correct ARM provider based on vm_type
    vm_type = _resolve_vm_type(body.resource_id, body.vm_type)
    if vm_type == "azure-vm":
        install_url = (
            f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
            f"/providers/Microsoft.Compute/virtualMachines/{machine_name}"
            f"/installPatches?api-version={_AVM_ASSESS_API_VERSION}"
        )
        log_label = "Azure VM"
    else:
        install_url = (
            f"{_ARM_BASE}/subscriptions/{sub_id}/resourceGroups/{rg}"
            f"/providers/Microsoft.HybridCompute/machines/{machine_name}"
            f"/installPatches?api-version={_ASSESS_API_VERSION}"
        )
        log_label = "Arc VM"

    # Build OS-specific parameters
    classifications = body.classifications or ["Critical", "Security"]
    if os_type.lower() == "linux":
        # Prefer package_names_to_include (Linux-native); fall back to kb_numbers_to_include
        pkg_include = body.package_names_to_include or body.kb_numbers_to_include or []
        pkg_exclude = body.package_names_to_exclude or body.kb_numbers_to_exclude or []
        os_params = {
            "linuxParameters": {
                "classificationsToInclude": classifications,
                "packageNameMasksToInclude": pkg_include,
                "packageNameMasksToExclude": pkg_exclude,
            }
        }
    else:
        windows_params: Dict[str, Any] = {
            "classificationsToInclude": classifications,
            "kbNumbersToInclude":       body.kb_numbers_to_include or [],
            "kbNumbersToExclude":       body.kb_numbers_to_exclude or [],
            "excludeKbsRequiringReboot": False,
        }
        os_params = {"windowsParameters": windows_params}

    request_body = {
        "maximumDuration": body.maximum_duration,
        "rebootSetting":   body.reboot_setting,
        **os_params,
    }

    token = await _get_arm_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    logger.info(
        "Triggering installPatches for %s: %s / %s / %s (os_type=%s, classes=%s)",
        log_label, sub_id, rg, machine_name, os_type, classifications,
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(install_url, headers=headers, json=request_body) as resp:
            if resp.status == 200:
                # Synchronous / immediate completion (rare)
                result_body = await resp.json(content_type=None)
                patch_repo = request.app.state.patch_repo
                sync_result = _extract_install_result(result_body)
                pending_record = await patch_repo.record_install({
                    "operation_url": install_url,
                    "machine_name": machine_name,
                    "subscription_id": sub_id,
                    "resource_group": rg,
                    "vm_type": vm_type,
                    "os_type": os_type,
                    "classifications": classifications,
                    "requested_patch_ids": (body.kb_numbers_to_include or []) + (body.kb_numbers_to_exclude or []),
                    "status": "Completed",
                    "start_date_time": sync_result.get("start_date_time"),
                })
                # Mark install complete inline since it was a synchronous return
                return {
                    "success": True,
                    "machine": machine_name,
                    "status": "Completed",
                    "data": sync_result,
                }

            if resp.status != 202:
                err_text = await resp.text()
                logger.error(
                    "installPatches POST failed %s for %s: %s",
                    resp.status, machine_name, err_text,
                )
                raise HTTPException(
                    status_code=resp.status,
                    detail=f"installPatches failed ({resp.status}): {err_text[:500]}",
                )

            operation_url = (
                resp.headers.get("Azure-AsyncOperation")
                or resp.headers.get("Location")
            )
            if not operation_url:
                raise HTTPException(
                    status_code=502,
                    detail="No Azure-AsyncOperation or Location header in 202 response",
                )

    logger.info("Install operation started for %s: %s", machine_name, operation_url)

    patch_repo = request.app.state.patch_repo
    await patch_repo.record_install({
        "operation_url": operation_url,
        "machine_name": machine_name,
        "subscription_id": sub_id,
        "resource_group": rg,
        "vm_type": vm_type,
        "os_type": os_type,
        "classifications": classifications,
        "requested_patch_ids": (body.kb_numbers_to_include or []) + (body.kb_numbers_to_exclude or []),
        "status": "InProgress",
    })

    return {
        "success":       True,
        "machine":       machine_name,
        "subscription_id": sub_id,
        "resource_group": rg,
        "status":        "InProgress",
        "operation_url": operation_url,
        "message":       (
            f"Patch installation started. Poll /api/patch-management/install-status "
            f"with the operation_url to track progress."
        ),
    }


@router.get("/install-status")  # no response_model — returns custom shape: is_done, status, data
@readonly_endpoint(agent_name="patch_mgmt_install_status", timeout_seconds=20)
async def get_install_status(request: Request, operation_url: str = Query(..., description="Azure-AsyncOperation URL from /install")):
    """
    Check the status of an in-progress or completed installPatches operation.

    Pass the ``operation_url`` returned by POST /install.  Returns the raw
    Azure operation status plus a parsed install result when completed.
    """
    token = await _get_arm_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(operation_url, headers=headers) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                raise HTTPException(
                    status_code=resp.status,
                    detail=f"Failed to poll install status ({resp.status}): {err_text[:500]}",
                )
            body = await resp.json(content_type=None)

    raw_status = (body.get("status") or "Unknown")
    is_done = raw_status.lower() in ("succeeded", "failed", "canceled", "cancelled")

    result: Dict[str, Any] = {
        "success":    True,
        "status":     raw_status,
        "is_done":    is_done,
        "data":       _extract_install_result(body) if is_done else None,
        "error":      body.get("error"),
    }

    if is_done and result["data"]:
        patch_repo = request.app.state.patch_repo
        await patch_repo.record_install({"operation_url": operation_url, "status": "Completed", **result["data"]})

    return result


@router.get("/arg-patch-data", response_model=StandardResponse)
@readonly_endpoint(agent_name="patch_mgmt_arg", timeout_seconds=60)
async def get_arg_patch_data(
    subscription_id: Optional[str] = Query(None),
):
    """
    Query Azure Resource Graph for stored patch-assessment data for all
    Arc-enabled machines in the subscription.

    Returns both per-machine summary counters (criticalAndSecurity, other,
    last-assessed timestamp) and the full list of available patches – all
    sourced from the ``patchassessmentresources`` ARG table without triggering
    a new live assessment.
    """
    sub_id = subscription_id or config.azure.subscription_id
    if not sub_id:
        raise HTTPException(status_code=400, detail="subscription_id is required")

    # Run all 4 ARG queries in parallel: summaries + patches for Arc AND Azure VMs
    arc_summary_kql = """
patchassessmentresources
| where type =~ 'microsoft.hybridcompute/machines/patchassessmentresults'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, resourceGroup, subscriptionId,
    vmType        = 'arc',
    status        = tostring(props.status),
    lastModified  = tostring(coalesce(props.lastModifiedDateTimeUTC, props.lastModifiedDateTime)),
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount    = toint(props.otherPatchCount),
    osType        = tostring(props.osType),
    rebootPending = tobool(props.rebootPending)
"""
    avm_summary_kql = """
patchassessmentresources
| where type =~ 'microsoft.compute/virtualmachines/patchassessmentresults'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, resourceGroup, subscriptionId,
    vmType        = 'azure-vm',
    status        = tostring(props.status),
    lastModified  = tostring(coalesce(props.lastModifiedDateTimeUTC, props.lastModifiedDateTime)),
    criticalCount = toint(props.criticalAndSecurityPatchCount),
    otherCount    = toint(props.otherPatchCount),
    osType        = tostring(props.osType),
    rebootPending = tobool(props.rebootPending)
"""
    arc_patches_kql = """
patchassessmentresources
| where type =~ 'microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, vmType = 'arc',
    patchName = tostring(props.patchName), kbId = tostring(props.kbId),
    classifications = tostring(props.classifications),
    rebootBehavior = tostring(props.rebootBehavior),
    assessmentState = tostring(props.assessmentState),
    publishedDate = tostring(props.publishedDate)
"""
    avm_patches_kql = """
patchassessmentresources
| where type =~ 'microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches'
| extend props = properties
| extend machineName = tostring(split(id, '/')[8])
| project machineName, vmType = 'azure-vm',
    patchName = tostring(props.patchName), kbId = tostring(props.kbId),
    classifications = tostring(props.classifications),
    rebootBehavior = tostring(props.rebootBehavior),
    assessmentState = tostring(props.assessmentState),
    publishedDate = tostring(props.publishedDate)
"""

    try:
        arc_sum, avm_sum, arc_pat, avm_pat = await asyncio.gather(
            _query_arg(arc_summary_kql, [sub_id]),
            _query_arg(avm_summary_kql,  [sub_id]),
            _query_arg(arc_patches_kql,  [sub_id]),
            _query_arg(avm_patches_kql,  [sub_id]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ARG patch-data query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Resource Graph query failed: {exc}") from exc

    summaries_raw = arc_sum + avm_sum
    patches_raw   = arc_pat + avm_pat

    # ── Group patches by (machineName, vmType) ─────────────────────────────
    patches_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for row in patches_raw:
        key = f"{(row.get('machineName') or '').lower()}|{(row.get('vmType') or 'arc')}"
        patches_by_key.setdefault(key, []).append({
            "patchName":       row.get("patchName"),
            "kbId":            row.get("kbId"),
            "classifications": _parse_arg_list(row.get("classifications")),
            "rebootBehavior":  row.get("rebootBehavior"),
            "assessmentState": row.get("assessmentState"),
            "publishedDate":   row.get("publishedDate"),
        })

    # ── Build per-machine result ───────────────────────────────────────────
    machines: List[Dict[str, Any]] = []
    for row in summaries_raw:
        vm_type = row.get("vmType") or "arc"
        name    = row.get("machineName") or ""
        key     = f"{name.lower()}|{vm_type}"
        patches = patches_by_key.get(key, [])
        crit    = row.get("criticalCount") or 0
        other   = row.get("otherCount") or 0

        if (crit == 0 and other == 0) and patches:
            for p in patches:
                cls = [c.lower() for c in (p.get("classifications") or [])]
                if "critical" in cls or "security" in cls:
                    crit += 1
                else:
                    other += 1

        rg = row.get("resourceGroup") or ""
        provider = (
            "Microsoft.Compute/virtualMachines"
            if vm_type == "azure-vm"
            else "Microsoft.HybridCompute/machines"
        )
        resource_id = (
            f"/subscriptions/{sub_id}/resourceGroups/{rg}"
            f"/providers/{provider}/{name}"
        )

        machines.append({
            "machine_name":    name,
            "resource_id":     resource_id,
            "resource_group":  rg,
            "subscription_id": row.get("subscriptionId") or sub_id,
            "os_type":         row.get("osType"),
            "reboot_pending":  row.get("rebootPending"),
            "vm_type":         vm_type,
            "patches": {
                "available_patches":           patches,
                "critical_and_security_count": crit,
                "other_count":                 other,
                "total_count":                 len(patches) or (crit + other),
                "last_assessed":               row.get("lastModified"),
                "status":                      row.get("status"),
                "source":                      "resource_graph",
            },
        })

    total_patches = sum(len(v) for v in patches_by_key.values())
    arc_count  = sum(1 for m in machines if m.get("vm_type") == "arc")
    avm_count  = sum(1 for m in machines if m.get("vm_type") == "azure-vm")
    logger.info("ARG patch-data: %d Arc, %d Azure VM, %d total patches", arc_count, avm_count, total_patches)

    return {
        "success":        True,
        "data":           machines,
        "count":          len(machines),
        "arc_count":      arc_count,
        "azure_vm_count": avm_count,
        "total_patches":  total_patches,
    }


def _parse_arg_list(val: Any) -> List[str]:
    """ARG returns JSON arrays as strings like '[\"Critical\",\"Security\"]' – parse them."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        import json as _json
        try:
            parsed = _json.loads(val)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return [val] if val else []
    return []


@router.get("/results/{machine_name}", response_model=StandardResponse)
@readonly_endpoint(agent_name="patch_mgmt_results", timeout_seconds=30)
async def get_patch_results(
    request: Request,
    machine_name: str,
    resource_id: Optional[str] = Query(None, description="Full ARM resource ID for the VM"),
):
    """
    Retrieve available patches for a machine from PostgreSQL.

    Uses PatchRepository.get_patches_for_vm() instead of the previous ARM REST
    patchAssessmentResults/latest call. The data comes directly from the
    available_patches table without triggering a new assessment.
    """
    if not resource_id:
        return StandardResponse(
            success=True,
            data=[],
            count=0,
            message=f"No patches available for '{machine_name}' (resource_id required)",
        )

    patch_repo = request.app.state.patch_repo
    patches = await patch_repo.get_patches_for_vm(resource_id)

    return StandardResponse(
        success=True,
        data=patches,
        count=len(patches),
        message=f"Retrieved {len(patches)} patches for {machine_name}" if patches else "No patches available for this machine",
    )
