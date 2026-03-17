"""CVE Management MCP Server.

Provides MCP tools for cache-aware CVE search, live NVD-backed search,
sync operations, vulnerability scan workflows, KB-to-CVE lookups, and
patch remediation.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

_LOG_LEVEL_NAME = os.getenv("CVE_MCP_LOG_LEVEL", "INFO")
_resolved_log_level = logging.INFO

try:
    _resolved_log_level = getattr(logging, _LOG_LEVEL_NAME.upper())
except AttributeError:
    _resolved_log_level = logging.INFO

logging.basicConfig(level=_resolved_log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(name="azure-cve")


def _json_response(payload: Dict[str, Any]) -> TextContent:
    return TextContent(type="text", text=json.dumps(payload, indent=2, default=str))


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _normalize_cve_id(cve_id: Optional[str]) -> Optional[str]:
    if not cve_id:
        return None
    return cve_id.strip().upper()


def _normalize_filters(
    *,
    keyword: Optional[str] = None,
    severity: Optional[str] = None,
    cvss_min: Optional[float] = None,
    cvss_max: Optional[float] = None,
    published_after: Optional[str] = None,
    published_before: Optional[str] = None,
    source: Optional[str] = None,
    vendor: Optional[str] = None,
    product: Optional[str] = None,
    cpe_name: Optional[str] = None,
) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if keyword:
        filters["keyword"] = keyword.strip()
    if severity:
        filters["severity"] = severity.strip().upper()
    if cvss_min is not None:
        filters["min_score"] = float(cvss_min)
    if cvss_max is not None:
        filters["max_score"] = float(cvss_max)
    if published_after:
        filters["published_after"] = published_after
    if published_before:
        filters["published_before"] = published_before
    if source:
        filters["source"] = source.strip().lower()
    if vendor:
        filters["vendor"] = vendor.strip()
    if product:
        filters["product"] = product.strip()
    if cpe_name:
        filters["cpe_name"] = cpe_name.strip()
    return filters


def _severity_for(cve: Any) -> Optional[str]:
    cvss_v3 = getattr(cve, "cvss_v3", None)
    if cvss_v3 and getattr(cvss_v3, "base_severity", None):
        return str(cvss_v3.base_severity).upper()
    cvss_v2 = getattr(cve, "cvss_v2", None)
    if cvss_v2 and getattr(cvss_v2, "base_severity", None):
        return str(cvss_v2.base_severity).upper()
    return None


def _score_for(cve: Any) -> Optional[float]:
    cvss_v3 = getattr(cve, "cvss_v3", None)
    if cvss_v3 and getattr(cvss_v3, "base_score", None) is not None:
        return float(cvss_v3.base_score)
    cvss_v2 = getattr(cve, "cvss_v2", None)
    if cvss_v2 and getattr(cvss_v2, "base_score", None) is not None:
        return float(cvss_v2.base_score)
    return None


def _published_for(cve: Any) -> Optional[datetime]:
    value = getattr(cve, "published_date", None)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _matches_filters(cve: Any, filters: Dict[str, Any]) -> bool:
    severity = filters.get("severity")
    if severity and _severity_for(cve) != str(severity).upper():
        return False

    min_score = filters.get("min_score")
    score = _score_for(cve)
    if min_score is not None and (score is None or score < float(min_score)):
        return False

    max_score = filters.get("max_score")
    if max_score is not None and (score is None or score > float(max_score)):
        return False

    published_after = filters.get("published_after")
    if published_after:
        try:
            after_dt = datetime.fromisoformat(str(published_after).replace("Z", "+00:00"))
            if after_dt.tzinfo is None:
                after_dt = after_dt.replace(tzinfo=timezone.utc)
            published_dt = _published_for(cve)
            if published_dt is None or published_dt < after_dt:
                return False
        except ValueError:
            pass

    published_before = filters.get("published_before")
    if published_before:
        try:
            before_dt = datetime.fromisoformat(str(published_before).replace("Z", "+00:00"))
            if before_dt.tzinfo is None:
                before_dt = before_dt.replace(tzinfo=timezone.utc)
            published_dt = _published_for(cve)
            if published_dt is None or published_dt > before_dt:
                return False
        except ValueError:
            pass

    keyword = (filters.get("keyword") or "").strip().lower()
    if keyword:
        haystack_parts: List[str] = [str(getattr(cve, "cve_id", "")), str(getattr(cve, "description", ""))]
        for product in getattr(cve, "affected_products", []) or []:
            haystack_parts.extend([
                str(getattr(product, "vendor", "")),
                str(getattr(product, "product", "")),
                str(getattr(product, "version", "")),
                str(getattr(product, "cpe_uri", "")),
            ])
        haystack = " ".join(haystack_parts).lower()
        if keyword not in haystack:
            return False

    source = (filters.get("source") or "").strip().lower()
    if source:
        sources = [str(item).lower() for item in getattr(cve, "sources", []) or []]
        if source not in sources:
            return False

    vendor = (filters.get("vendor") or "").strip().lower()
    if vendor:
        if not any(vendor in str(getattr(product, "vendor", "")).lower() for product in getattr(cve, "affected_products", []) or []):
            return False

    product_name = (filters.get("product") or "").strip().lower()
    if product_name:
        if not any(product_name in str(getattr(product, "product", "")).lower() for product in getattr(cve, "affected_products", []) or []):
            return False

    cpe_name = (filters.get("cpe_name") or "").strip().lower()
    if cpe_name:
        if not any(cpe_name in str(getattr(product, "cpe_uri", "")).lower() for product in getattr(cve, "affected_products", []) or []):
            return False

    return True


def _sort_cves(cves: List[Any], sort_by: str = "published_date", sort_order: str = "desc") -> List[Any]:
    reverse = str(sort_order).lower() != "asc"
    field = (sort_by or "published_date").lower()
    severity_rank = {
        "UNKNOWN": 0,
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }

    if field == "cve_id":
        key_fn = lambda cve: str(getattr(cve, "cve_id", ""))
    elif field == "severity":
        key_fn = lambda cve: (severity_rank.get(_severity_for(cve) or "UNKNOWN", 0), _score_for(cve) or -1.0, str(getattr(cve, "cve_id", "")))
    elif field == "cvss_score":
        key_fn = lambda cve: (_score_for(cve) or -1.0, str(getattr(cve, "cve_id", "")))
    elif field == "last_modified_date":
        key_fn = lambda cve: (str(getattr(cve, "last_modified_date", "")), str(getattr(cve, "cve_id", "")))
    else:
        key_fn = lambda cve: (_published_for(cve) or datetime.min.replace(tzinfo=timezone.utc), str(getattr(cve, "cve_id", "")))

    return sorted(cves, key=key_fn, reverse=reverse)


async def _get_cve_service():
    from main import get_cve_service
    return await get_cve_service()


async def _get_cve_scanner():
    from main import get_cve_scanner
    return await get_cve_scanner()


async def _get_cve_patch_mapper():
    from main import get_cve_patch_mapper
    return await get_cve_patch_mapper()


async def _get_cve_vm_service():
    from main import get_cve_vm_service
    return await get_cve_vm_service()


async def _get_kb_cve_edge_repository():
    """Get KB-CVE edge repository. Phase 8: prefer CVERepository via pg_client."""
    try:
        from utils.pg_client import postgres_client
        if postgres_client.is_initialized:
            from utils.repositories.cve_repository import CVERepository
            return CVERepository(postgres_client.pool)
    except Exception:
        pass
    from main import get_kb_cve_edge_repository
    return await get_kb_cve_edge_repository()


async def _search_cache(*, cve_id: Optional[str], filters: Dict[str, Any], limit: int, offset: int, sort_by: str, sort_order: str) -> Dict[str, Any]:
    cve_service = await _get_cve_service()
    if cve_id:
        cve = await cve_service.get_cve(cve_id)
        filtered = [cve] if cve and _matches_filters(cve, filters) else []
        total_count = len(filtered)
    else:
        filtered = await cve_service.search_cves(filters, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order, allow_live_fallback=False)
        total_count = await cve_service.count_cves(filters)
    return {"results": filtered, "total_count": total_count, "cache_strategy": "cache_only"}


async def _search_live(*, cve_id: Optional[str], filters: Dict[str, Any], limit: int, offset: int, sort_by: str, sort_order: str) -> Dict[str, Any]:
    cve_service = await _get_cve_service()
    if cve_id:
        cve = await cve_service.get_cve(cve_id, force_refresh=True)
        filtered = [cve] if cve and _matches_filters(cve, filters) else []
        return {"results": filtered, "total_count": len(filtered), "cache_strategy": "live_refresh"}

    live_results = await cve_service.sync_live_cves(
        query=filters.get("keyword"),
        limit=max(limit + offset, limit),
        source=filters.get("source"),
        nvd_filters={"cpeName": filters["cpe_name"]} if filters.get("cpe_name") else None,
        populate_l1=True,
    )
    filtered_live = [cve for cve in live_results if _matches_filters(cve, filters)]
    filtered_live = _sort_cves(filtered_live, sort_by=sort_by, sort_order=sort_order)
    return {"results": filtered_live[offset:offset + limit], "total_count": len(filtered_live), "cache_strategy": "live_nvd"}


async def _search_auto(*, cve_id: Optional[str], filters: Dict[str, Any], limit: int, offset: int, sort_by: str, sort_order: str) -> Dict[str, Any]:
    cve_service = await _get_cve_service()
    if cve_id:
        cve = await cve_service.get_cve(cve_id)
        filtered = [cve] if cve and _matches_filters(cve, filters) else []
        return {"results": filtered, "total_count": len(filtered), "cache_strategy": "cache_first"}

    results = await cve_service.search_cves(filters, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order, allow_live_fallback=True)
    total_count = await cve_service.count_cves(filters)
    return {"results": results, "total_count": max(total_count, len(results)), "cache_strategy": "cache_with_live_fallback"}


async def _run_search(*, tool_name: str, cve_id: Optional[str] = None, keyword: Optional[str] = None, severity: Optional[str] = None, cvss_min: Optional[float] = None, cvss_max: Optional[float] = None, published_after: Optional[str] = None, published_before: Optional[str] = None, source: Optional[str] = None, vendor: Optional[str] = None, product: Optional[str] = None, cpe_name: Optional[str] = None, limit: int = 20, offset: int = 0, sort_by: str = "published_date", sort_order: str = "desc", search_mode: str = "auto") -> TextContent:
    try:
        normalized_cve_id = _normalize_cve_id(cve_id)
        filters = _normalize_filters(keyword=keyword, severity=severity, cvss_min=cvss_min, cvss_max=cvss_max, published_after=published_after, published_before=published_before, source=source, vendor=vendor, product=product, cpe_name=cpe_name)
        mode = (search_mode or "auto").strip().lower()
        if mode == "cache":
            search_result = await _search_cache(cve_id=normalized_cve_id, filters=filters, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order)
        elif mode == "live":
            search_result = await _search_live(cve_id=normalized_cve_id, filters=filters, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order)
        else:
            search_result = await _search_auto(cve_id=normalized_cve_id, filters=filters, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order)
        results = [_serialize(cve) for cve in search_result["results"]]
        return _json_response({"success": True, "count": len(results), "total_count": search_result["total_count"], "offset": offset, "limit": limit, "mode": mode, "cves": results, "filters": filters, "tool_name": tool_name, "cache_strategy": search_result["cache_strategy"]})
    except Exception as exc:
        logger.exception("%s failed", tool_name)
        return _json_response({"success": False, "error": str(exc), "tool_name": tool_name})


@mcp.tool()
async def search_cve(
    cve_id: Annotated[Optional[str], "CVE identifier (e.g., CVE-2024-1234)"] = None,
    keyword: Annotated[Optional[str], "Keyword to search in description or affected products"] = None,
    severity: Annotated[Optional[str], "Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"] = None,
    cvss_min: Annotated[Optional[float], "Minimum CVSS score (0.0-10.0)"] = None,
    cvss_max: Annotated[Optional[float], "Maximum CVSS score (0.0-10.0)"] = None,
    published_after: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    published_before: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    source: Annotated[Optional[str], "Preferred source filter such as nvd, cve_org, microsoft, github"] = None,
    vendor: Annotated[Optional[str], "Filter by affected product vendor"] = None,
    product: Annotated[Optional[str], "Filter by affected product name"] = None,
    cpe_name: Annotated[Optional[str], "Optional CPE name for live NVD search"] = None,
    limit: Annotated[int, "Maximum results to return"] = 20,
    offset: Annotated[int, "Pagination offset"] = 0,
    sort_by: Annotated[str, "Sort field: published_date, last_modified_date, cvss_score, severity, cve_id"] = "published_date",
    sort_order: Annotated[str, "Sort order: asc or desc"] = "desc",
    search_mode: Annotated[str, "Search mode: auto, cache, or live"] = "auto",
) -> TextContent:
    """Search CVEs using cached data by default with optional live NVD fallback."""
    return await _run_search(tool_name="search_cve", cve_id=cve_id, keyword=keyword, severity=severity, cvss_min=cvss_min, cvss_max=cvss_max, published_after=published_after, published_before=published_before, source=source, vendor=vendor, product=product, cpe_name=cpe_name, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order, search_mode=search_mode)


@mcp.tool()
async def search_cve_cache(
    cve_id: Annotated[Optional[str], "CVE identifier (e.g., CVE-2024-1234)"] = None,
    keyword: Annotated[Optional[str], "Keyword to search in cached CVEs"] = None,
    severity: Annotated[Optional[str], "Filter by severity"] = None,
    cvss_min: Annotated[Optional[float], "Minimum CVSS score"] = None,
    cvss_max: Annotated[Optional[float], "Maximum CVSS score"] = None,
    published_after: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    published_before: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    source: Annotated[Optional[str], "Filter by cached source"] = None,
    vendor: Annotated[Optional[str], "Filter by affected vendor"] = None,
    product: Annotated[Optional[str], "Filter by affected product"] = None,
    cpe_name: Annotated[Optional[str], "Optional CPE filter applied to cached affected products"] = None,
    limit: Annotated[int, "Maximum results to return"] = 20,
    offset: Annotated[int, "Pagination offset"] = 0,
    sort_by: Annotated[str, "Sort field"] = "published_date",
    sort_order: Annotated[str, "Sort order"] = "desc",
) -> TextContent:
    """Search only the local cache and persisted repository for CVEs."""
    return await _run_search(tool_name="search_cve_cache", cve_id=cve_id, keyword=keyword, severity=severity, cvss_min=cvss_min, cvss_max=cvss_max, published_after=published_after, published_before=published_before, source=source, vendor=vendor, product=product, cpe_name=cpe_name, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order, search_mode="cache")


@mcp.tool()
async def search_cve_live(
    cve_id: Annotated[Optional[str], "CVE identifier (e.g., CVE-2024-1234)"] = None,
    keyword: Annotated[Optional[str], "Keyword to search live from NVD"] = None,
    severity: Annotated[Optional[str], "Filter by severity"] = None,
    cvss_min: Annotated[Optional[float], "Minimum CVSS score"] = None,
    cvss_max: Annotated[Optional[float], "Maximum CVSS score"] = None,
    published_after: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    published_before: Annotated[Optional[str], "Filter by publish date (ISO 8601 format)"] = None,
    source: Annotated[Optional[str], "Preferred upstream source, typically nvd"] = None,
    vendor: Annotated[Optional[str], "Filter by affected vendor"] = None,
    product: Annotated[Optional[str], "Filter by affected product"] = None,
    cpe_name: Annotated[Optional[str], "Optional NVD CPE name for real-time lookup"] = None,
    limit: Annotated[int, "Maximum results to return"] = 20,
    offset: Annotated[int, "Pagination offset"] = 0,
    sort_by: Annotated[str, "Sort field"] = "published_date",
    sort_order: Annotated[str, "Sort order"] = "desc",
) -> TextContent:
    """Search CVEs live and persist the returned records into cache and repository."""
    return await _run_search(tool_name="search_cve_live", cve_id=cve_id, keyword=keyword, severity=severity, cvss_min=cvss_min, cvss_max=cvss_max, published_after=published_after, published_before=published_before, source=source, vendor=vendor, product=product, cpe_name=cpe_name, limit=limit, offset=offset, sort_by=sort_by, sort_order=sort_order, search_mode="live")


@mcp.tool()
async def sync_cve(cve_id: Annotated[str, "CVE identifier to refresh from live sources"]) -> TextContent:
    """Force-refresh a single CVE from live sources and update cache/repository."""
    try:
        cve_service = await _get_cve_service()
        cve = await cve_service.sync_cve(_normalize_cve_id(cve_id) or cve_id)
        if not cve:
            return _json_response({"success": False, "error": f"CVE {_normalize_cve_id(cve_id) or cve_id} not found in live sources", "tool_name": "sync_cve"})
        return _json_response({"success": True, "cve": _serialize(cve), "tool_name": "sync_cve", "message": "CVE refreshed from live sources and persisted"})
    except Exception as exc:
        logger.exception("sync_cve failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "sync_cve"})


@mcp.tool()
async def sync_recent_cves(hours: Annotated[int, "Sync CVEs modified within the last N hours"] = 24, limit: Annotated[Optional[int], "Optional max CVEs to sync"] = 100) -> TextContent:
    """Sync recently modified CVEs from upstream sources into the repository."""
    try:
        cve_service = await _get_cve_service()
        since_date = datetime.now(timezone.utc) - timedelta(hours=max(hours, 1))
        synced_count = await cve_service.sync_recent_cves(since_date=since_date, limit=limit)
        return _json_response({"success": True, "since_date": since_date.isoformat(), "synced_count": synced_count, "limit": limit, "tool_name": "sync_recent_cves"})
    except Exception as exc:
        logger.exception("sync_recent_cves failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "sync_recent_cves"})


@mcp.tool()
async def get_cve_cache_stats() -> TextContent:
    """Return L1 CVE cache statistics for troubleshooting and tuning."""
    try:
        cve_service = await _get_cve_service()
        return _json_response({"success": True, "stats": cve_service.get_cache_stats(), "tool_name": "get_cve_cache_stats"})
    except Exception as exc:
        logger.exception("get_cve_cache_stats failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "get_cve_cache_stats"})


@mcp.tool()
async def scan_inventory(subscription_id: Annotated[str, "Azure subscription ID"], resource_group: Annotated[Optional[str], "Optional resource group filter"] = None, vm_name: Annotated[Optional[str], "Optional VM name filter"] = None) -> TextContent:
    """Trigger a CVE scan across Azure/Arc VM inventory."""
    try:
        from models.cve_models import CVEScanRequest

        scanner = await _get_cve_scanner()
        resource_groups = [resource_group] if resource_group else None
        cve_filters = {"vm_name": vm_name} if vm_name else None
        scan_request = CVEScanRequest(subscription_ids=[subscription_id], resource_groups=resource_groups, include_arc=True, cve_filters=cve_filters)

        scan_id = await scanner.start_scan(scan_request)
        scan_result = await scanner.get_scan_status_summary(scan_id)

        response_data = {"success": True, "scan_id": scan_id, "status": scan_result.get("status", "pending") if scan_result else "pending", "message": "Scan started. Check status with get_cve_scan_status.", "tool_name": "scan_inventory"}
        if scan_result:
            response_data.update({"vm_count": scan_result.get("total_vms", 0), "scanned_vms": scan_result.get("scanned_vms", 0), "cve_count": scan_result.get("total_matches", 0), "started_at": scan_result.get("started_at")})

        return _json_response(response_data)
    except Exception as exc:
        logger.exception("scan_inventory failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "scan_inventory"})


@mcp.tool()
async def get_cve_scan_status(scan_id: Annotated[str, "Scan identifier returned from scan_inventory"]) -> TextContent:
    """Get the status and summary for a previously started CVE inventory scan."""
    try:
        scanner = await _get_cve_scanner()
        scan_result = await scanner.get_scan_status_summary(scan_id)
        if not scan_result:
            return _json_response({"success": False, "error": f"Scan {scan_id} not found", "tool_name": "get_cve_scan_status"})
        return _json_response({"success": True, "scan": _serialize(scan_result), "tool_name": "get_cve_scan_status"})
    except Exception as exc:
        logger.exception("get_cve_scan_status failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "get_cve_scan_status"})


@mcp.tool()
async def list_cve_scans(limit: Annotated[int, "Maximum number of recent scans to return"] = 10) -> TextContent:
    """List recent CVE inventory scans for follow-up and debugging."""
    try:
        scanner = await _get_cve_scanner()
        scans = await scanner.list_recent_scans(limit=limit)
        return _json_response({"success": True, "count": len(scans), "scans": _serialize(scans), "tool_name": "list_cve_scans"})
    except Exception as exc:
        logger.exception("list_cve_scans failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "list_cve_scans"})


@mcp.tool()
async def get_cve_affected_vms(cve_id: Annotated[str, "CVE identifier to inspect across scanned VM inventory"]) -> TextContent:
    """Return VMs currently affected by a given CVE using the latest scan/inventory data."""
    try:
        vm_service = await _get_cve_vm_service()
        response = await vm_service.get_cve_affected_vms(_normalize_cve_id(cve_id) or cve_id)
        if response is None:
            return _json_response({"success": False, "error": f"No affected VM data found for {_normalize_cve_id(cve_id) or cve_id}", "tool_name": "get_cve_affected_vms"})
        return _json_response({"success": True, "result": _serialize(response), "tool_name": "get_cve_affected_vms"})
    except Exception as exc:
        logger.exception("get_cve_affected_vms failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "get_cve_affected_vms"})


@mcp.tool()
async def resolve_kb_to_cves(kb_number: Annotated[str, "KB article number such as KB5075999"]) -> TextContent:
    """Resolve a Microsoft KB article to its known CVE IDs using reverse edge mappings."""
    try:
        patch_mapper = await _get_cve_patch_mapper()
        cve_ids = await patch_mapper.get_cve_ids_for_kb(kb_number)
        kb_repo = await _get_kb_cve_edge_repository()
        edges = await kb_repo.get_edges_for_kb(kb_number)
        return _json_response({"success": True, "kb_number": kb_number, "cve_ids": cve_ids, "edges": _serialize(edges), "tool_name": "resolve_kb_to_cves"})
    except Exception as exc:
        logger.exception("resolve_kb_to_cves failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "resolve_kb_to_cves"})


@mcp.tool()
async def get_patches(cve_id: Annotated[str, "CVE identifier (e.g., CVE-2024-1234)"], subscription_ids: Annotated[Optional[List[str]], "Optional subscription IDs to filter affected VMs"] = None) -> TextContent:
    """Get patches that remediate a CVE."""
    try:
        patch_mapper = await _get_cve_patch_mapper()
        mapping = await patch_mapper.get_patches_for_cve(_normalize_cve_id(cve_id) or cve_id, subscription_ids)
        patches = [{"kb_number": getattr(patch, "kb_number", None), "package_name": getattr(patch, "package_name", None), "title": getattr(patch, "title", None), "priority": getattr(patch, "priority", None), "affected_vm_count": getattr(patch, "affected_vm_count", None), "vendor": getattr(patch, "vendor", None)} for patch in getattr(mapping, "patches", [])]
        return _json_response({"success": True, "cve_id": _normalize_cve_id(cve_id) or cve_id, "patches": patches, "total_patches": len(patches), "priority_score": getattr(mapping, "priority_score", None), "total_affected_vms": getattr(mapping, "total_affected_vms", None), "recommendation": getattr(mapping, "recommendation", None), "tool_name": "get_patches"})
    except Exception as exc:
        logger.exception("get_patches failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "get_patches"})


@mcp.tool()
async def trigger_remediation(cve_id: Annotated[str, "CVE identifier to remediate"], vm_name: Annotated[str, "VM name to apply patches"], subscription_id: Annotated[str, "Azure subscription ID"], resource_group: Annotated[str, "Resource group containing VM"], dry_run: Annotated[bool, "If True, show plan without executing"] = True, confirmed: Annotated[bool, "Must be True to execute real patch installation"] = False) -> TextContent:
    """Trigger patch installation to remediate a CVE with a dry-run safety workflow."""
    try:
        from utils.patch_mcp_client import get_patch_mcp_client

        normalized_cve_id = _normalize_cve_id(cve_id) or cve_id
        patch_mapper = await _get_cve_patch_mapper()
        mapping = await patch_mapper.get_patches_for_cve(normalized_cve_id, [subscription_id])
        if not getattr(mapping, "patches", []):
            return _json_response({"success": False, "error": f"No patches found for {normalized_cve_id}", "tool_name": "trigger_remediation"})

        if dry_run or not confirmed:
            patches = [{"kb_number": getattr(patch, "kb_number", None), "package_name": getattr(patch, "package_name", None), "title": getattr(patch, "title", None), "priority": getattr(patch, "priority", None)} for patch in mapping.patches]
            return _json_response({"success": True, "mode": "dry_run", "cve_id": normalized_cve_id, "vm_name": vm_name, "patches": patches, "message": "Installation plan ready. Call with confirmed=True to execute.", "warning": "Patch installation may require VM reboot.", "tool_name": "trigger_remediation"})

        patch_client = await get_patch_mcp_client()
        kb_numbers = [getattr(patch, "kb_number", None) for patch in mapping.patches if getattr(patch, "kb_number", None)]
        result = await patch_client.install_vm_patches(machine_name=vm_name, subscription_id=subscription_id, resource_group=resource_group, classifications=["Critical", "Security"], kb_numbers_to_include=kb_numbers, reboot_setting="IfRequired")
        return _json_response({"success": True, "mode": "confirmed", "cve_id": normalized_cve_id, "vm_name": vm_name, "operation_url": result.get("operation_url") if isinstance(result, dict) else None, "status": result.get("status", "started") if isinstance(result, dict) else "started", "message": "Patch installation started. Monitor with the patch MCP status tools.", "tool_name": "trigger_remediation"})
    except Exception as exc:
        logger.exception("trigger_remediation failed")
        return _json_response({"success": False, "error": str(exc), "tool_name": "trigger_remediation"})


if __name__ == "__main__":
    logger.info("Starting CVE MCP server")
    mcp.run()
