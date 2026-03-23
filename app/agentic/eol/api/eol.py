"""
End-of-Life (EOL) Search and Management API Module

This module provides endpoints for searching, verifying, and managing End-of-Life
data for software and operating systems. It orchestrates multiple specialized agents
to query various EOL data sources and consolidate results.

Key Features:
    - Multi-agent EOL data search across specialized sources
    - Software and OS inventory EOL risk analysis
    - EOL result verification and manual caching
    - Agent response history tracking and management
    - Internet-only search mode for web scraping

Endpoints:
    GET  /api/eol - Get EOL data for software
    POST /api/search/eol - Search EOL data with orchestrator
    POST /api/analyze - Comprehensive EOL risk analysis
    POST /api/verify-eol-result - Verify and cache EOL result
    POST /api/cache-eol-result - Manually cache EOL result
    GET  /api/eol-agent-responses - Get agent response history
    POST /api/eol-agent-responses/clear - Clear response history

Author: GitHub Copilot
Date: October 2025
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import logging

from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    standard_endpoint,
    write_endpoint,
    readonly_endpoint,
    with_timeout_and_stats
)
from utils.eol_inventory import eol_inventory
from utils.eol_data_processor import process_eol_data
from utils.normalization import derive_os_name_version
from utils.os_extraction_rules import os_extraction_rules_store
from utils.vendor_url_inventory import vendor_url_inventory

# Note: DEFAULT_VENDOR_ROUTING removed in pipeline refactor
# This fallback provides basic vendor list for error scenarios

logger = logging.getLogger(__name__)

# Create router for EOL endpoints
router = APIRouter(tags=["EOL Search & Management"])


def _get_eol_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_eol_orchestrator
    return get_eol_orchestrator()


def _get_inventory_asst_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_inventory_asst_orchestrator
    return get_inventory_asst_orchestrator()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SoftwareSearchRequest(BaseModel):
    """Request model for EOL search."""
    software_name: str
    software_version: Optional[str] = None
    search_hints: Optional[str] = None
    search_internet_only: bool = False
    search_include_internet: bool = False
    search_ignore_cache: bool = False
    search_agent_only: bool = False


class VendorParsingRequest(BaseModel):
    """Request model for vendor-driven parsing."""
    vendor: str
    mode: Optional[str] = "agents_plus_internet"
    ignore_cache: bool = False
    limit: Optional[int] = None


class VerifyEOLRequest(BaseModel):
    """Request model for EOL verification."""
    software_name: str
    software_version: Optional[str] = None
    agent_name: Optional[str] = None
    source_url: Optional[str] = None
    verification_status: Optional[str] = "verified"  # "verified" or "failed"


class CacheEOLRequest(BaseModel):
    """Request model for manual EOL caching."""
    software_name: str
    software_version: Optional[str] = None


class BatchEOLRequest(BaseModel):
    """Request model for batch EOL enrichment."""
    items: List[Dict[str, str]]  # List of {"name": "...", "version": "..."}
    max_concurrent: int = 10


class MultiAgentResponse(BaseModel):
    """Response model for multi-agent operations."""
    session_id: str
    analysis_result: dict
    communication_history: list
    timestamp: str


class UpdateEolRecordRequest(BaseModel):
    """Request model for updating a stored EOL record."""
    software_name: Optional[str] = None
    version: Optional[str] = None
    eol_date: Optional[str] = None
    support_end_date: Optional[str] = None
    release_date: Optional[str] = None
    status: Optional[str] = None
    risk_level: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    agent_used: Optional[str] = None
    raw_software_name: Optional[str] = None
    raw_version: Optional[str] = None
    normalized_software_name: Optional[str] = None
    normalized_version: Optional[str] = None
    derivation_strategy: Optional[str] = None
    derivation_rule_id: Optional[str] = None
    derivation_rule_name: Optional[str] = None
    derivation_source_scope: Optional[str] = None
    derivation_pattern: Optional[str] = None
    derivation_notes: Optional[str] = None


class BulkDeleteItem(BaseModel):
    record_id: str
    software_key: str


class BulkDeleteRequest(BaseModel):
    items: List[BulkDeleteItem]


class OSExtractionRuleRequest(BaseModel):
    name: str
    pattern: str
    source_scope: str = "combined"
    derived_name_template: str = "{name}"
    derived_version_template: str = "{version}"
    priority: int = 100
    enabled: bool = True
    notes: Optional[str] = None
    flags: str = "IGNORECASE"


class OSExtractionTestRequest(BaseModel):
    raw_name: str
    raw_version: Optional[str] = None


class OSExtractionReapplyRequest(BaseModel):
    apply_changes: bool = False
    preview_limit: int = 100


@router.get("/api/os-extraction-rules", response_model=StandardResponse)
@readonly_endpoint(agent_name="os_extraction_rules_list", timeout_seconds=15)
async def list_os_extraction_rules(request: Request):
    rules = os_extraction_rules_store.get_rules()
    return StandardResponse(success=True, data=rules, count=len(rules))


@router.post("/api/os-extraction-rules", response_model=StandardResponse)
@write_endpoint(agent_name="os_extraction_rules_add", timeout_seconds=20)
async def add_os_extraction_rule(request: OSExtractionRuleRequest):
    rule = await os_extraction_rules_store.add_rule(request.dict())
    return StandardResponse.success_response(data=[rule], message="OS extraction rule saved").to_dict()


@router.put("/api/os-extraction-rules/{rule_id}", response_model=StandardResponse)
@write_endpoint(agent_name="os_extraction_rules_update", timeout_seconds=20)
async def update_os_extraction_rule(rule_id: str, request: OSExtractionRuleRequest):
    rule = await os_extraction_rules_store.update_rule(rule_id, request.dict())
    if not rule:
        return StandardResponse.error_response("Rule not found").to_dict()
    return StandardResponse.success_response(data=[rule], message="OS extraction rule updated").to_dict()


@router.delete("/api/os-extraction-rules/{rule_id}", response_model=StandardResponse)
@write_endpoint(agent_name="os_extraction_rules_delete", timeout_seconds=20)
async def delete_os_extraction_rule(rule_id: str):
    deleted = await os_extraction_rules_store.delete_rule(rule_id)
    if not deleted:
        return StandardResponse.error_response("Rule not found").to_dict()
    return StandardResponse.success_response(data=[], message="OS extraction rule deleted").to_dict()


@router.post("/api/os-extraction-rules/test", response_model=StandardResponse)
@readonly_endpoint(agent_name="os_extraction_rules_test", timeout_seconds=15)
async def test_os_extraction_rule(request: OSExtractionTestRequest):
    derived = derive_os_name_version(request.raw_name, request.raw_version)
    return StandardResponse.success_response(data=[derived]).to_dict()


@router.post("/api/os-extraction-rules/reapply", response_model=StandardResponse)
@write_endpoint(agent_name="os_extraction_rules_reapply", timeout_seconds=120)
async def reapply_os_extraction_rules(request: OSExtractionReapplyRequest):
    result = await eol_inventory.reapply_os_normalization(
        apply_changes=request.apply_changes,
        preview_limit=request.preview_limit,
    )
    return StandardResponse.success_response(
        data=result.get("items", []),
        metadata={
            "scanned": result.get("scanned", 0),
            "changed": result.get("changed", 0),
            "updated": result.get("updated", 0),
            "errors": result.get("errors", []),
            "apply_changes": request.apply_changes,
        },
        message="Cached OS normalization updated" if request.apply_changes else "Cached OS normalization preview generated",
    ).to_dict()


# ============================================================================
# EOL QUERY ENDPOINTS
# ============================================================================

@router.get("/api/eol", response_model=StandardResponse)
@standard_endpoint(agent_name="eol_search", timeout_seconds=30)
async def get_eol(
    name: Optional[str] = None,
    software: Optional[str] = None,
    version: Optional[str] = None
):
    """
    Get EOL data using multi-agent system with prioritized sources.
    
    Searches for end-of-life information across multiple specialized agents
    (Microsoft, Red Hat, endoflife.date, etc.) and returns consolidated results.
    
    Args:
        name: Software name to search for (required)
        version: Specific version to check (optional)
    
    Returns:
        StandardResponse with EOL data including dates, support status, and sources.
    
    Raises:
        HTTPException: 404 if no EOL data found, 500 for other errors
    
    Example Response:
        {
            "success": true,
            "software_name": "Windows Server 2012 R2",
            "version": null,
            "primary_source": "microsoft_lifecycle",
            "eol_data": {
                "eol_date": "2023-10-10",
                "support_end": "2023-10-10",
                "status": "expired"
            },
            "all_sources": {
                "microsoft_lifecycle": {...},
                "endoflife_date": {...}
            },
            "timestamp": "2025-10-15T10:45:00Z"
        }
    """
    # Support both 'name' and 'software' parameters for backwards compatibility
    software_name = name or software
    if not software_name:
        raise HTTPException(status_code=422, detail="Either 'name' or 'software' parameter is required")

    eol_data = await _get_eol_orchestrator().get_eol_data(software_name, version)

    if not eol_data.get("data"):
        raise HTTPException(status_code=404, detail=f"No EOL data found for {software_name}")

    return {
        "software_name": software_name,
        "version": version,
        "primary_source": eol_data.get("primary_source") or eol_data.get("agent_used") or "unknown",
        "eol_data": eol_data["data"],
        "all_sources": eol_data.get("all_sources", {}),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/search/eol")
@with_timeout_and_stats(
    agent_name="orchestrator",
    timeout_seconds=45,
    track_cache=True,
    auto_wrap_response=False
)
async def search_software_eol(request: SoftwareSearchRequest):
    """
    Search for end-of-life information for specific software using the orchestrator.
    
    Uses intelligent agent routing to search across multiple EOL data sources.
    Supports internet-only search mode for web scraping when structured data unavailable.
    
    Args:
        request: SoftwareSearchRequest containing software_name, software_version,
                search_hints, and search_internet_only flag
    
    Returns:
        Dict with EOL result, session_id, communications, and search metadata.
    
    Example Request:
        {
            "software_name": "Oracle Database",
            "software_version": "19c",
            "search_hints": "Enterprise Edition",
            "search_internet_only": false
        }
    
    Example Response:
        {
            "success": true,
            "result": {
                "eol_date": "2027-04-30",
                "extended_support": "2030-04-30"
            },
            "session_id": "uuid-here",
            "communications": [...],
            "search_mode": "multi_agent",
            "agent_used": "oracle_lifecycle",
            "timestamp": "2025-10-15T10:50:00Z"
        }
    """
    # Log the enhanced search request
    version_display = f" v{request.software_version}" if request.software_version else " (no version)"
    search_mode_label = " [Internet Only]" if request.search_internet_only else (
        " [Agents + Internet]" if request.search_include_internet else (
            " [Agents Only]" if request.search_agent_only else ""
        )
    )
    logger.info(f"EOL search request: {request.software_name}{version_display}{search_mode_label}")
    
    if request.search_hints:
        logger.info(f"Search hints provided: {request.search_hints}")
    
    # Call appropriate search method based on mode
    orchestrator = _get_eol_orchestrator()
    
    if request.search_internet_only:
        # Internet-only search mode
        result = await orchestrator.search_software_eol_internet(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints,
            search_ignore_cache=request.search_ignore_cache,
        )
        search_mode = "internet_only"
    elif request.search_include_internet:
        # Multi-agent search with explicit internet fallback
        result = await orchestrator.search_software_eol(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints,
            search_include_internet=True,
            search_ignore_cache=request.search_ignore_cache,
        )
        search_mode = "agents_plus_internet"
    elif request.search_agent_only:
        # Explicit agent-only search (skip internet fallback)
        result = await orchestrator.search_software_eol(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints,
            search_include_internet=False,
            search_ignore_cache=request.search_ignore_cache,
            search_agent_only=True,
        )
        search_mode = "agents_only"
    else:
        # Standard multi-agent search
        result = await orchestrator.search_software_eol(
            software_name=request.software_name,
            software_version=request.software_version,
            search_hints=request.search_hints,
            search_ignore_cache=request.search_ignore_cache,
        )
        search_mode = "multi_agent"
    
    # Get communication history
    communications = await orchestrator.get_communication_history()
    
    return {
        "result": result,
        "session_id": orchestrator.session_id,
        "communications": communications,
        "search_mode": search_mode,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/api/vendors")
@readonly_endpoint(agent_name="list_vendors", timeout_seconds=20)
async def list_vendors():
    """List vendor identifiers supported by the orchestrator."""
    try:
        orchestrator = _get_eol_orchestrator()
        vendor_map = getattr(orchestrator, "vendor_routing", {}) or {}
        return {
            "success": True,
            "vendors": sorted(vendor_map.keys()),
            "vendor_routing": vendor_map,
            "count": len(vendor_map),
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Vendor list fallback due to orchestrator error: %s", exc)
        # Minimal fallback - pipeline refactor removed DEFAULT_VENDOR_ROUTING
        fallback = {"endoflife": ["endoflife_agent"], "eolstatus": ["eolstatus_agent"]}
        return {
            "success": True,
            "vendors": sorted(fallback.keys()),
            "vendor_routing": fallback,
            "count": len(fallback),
            "warning": "Vendor API fallback; orchestrator unavailable",
        }


@router.post("/api/search/eol/vendor")
@with_timeout_and_stats(
    agent_name="orchestrator",
    timeout_seconds=120,
    track_cache=True,
    auto_wrap_response=False,
)
async def search_vendor_eol(request: VendorParsingRequest):
    """Run vendor-driven EOL parsing across all known products for that vendor."""
    orchestrator = _get_eol_orchestrator()
    vendor_key = (request.vendor or "").strip().lower()
    vendor_map = getattr(orchestrator, "vendor_routing", {}) or {}

    async def _persist_vendor_runs(runs: List[Dict[str, Any]]) -> None:
        if not runs:
            return

        async def _persist_run(run: Dict[str, Any]) -> None:
            logger.info("_persist_run called with run: success=%s, software_name=%s",
                        run.get("success") if run else None,
                        run.get("software_name") if run else None)
            if not run or not run.get("success"):
                logger.info("_persist_run early return: run is None or not successful")
                return

            software_name = run.get("software_name")
            if not software_name:
                logger.info("_persist_run early return: no software_name")
                return

            version = run.get("version")
            eol_date = run.get("eol_date")
            support_end_date = run.get("support_end_date")
            if not eol_date and not support_end_date:
                logger.info("_persist_run early return: no eol_date or support_end_date")
                return

            raw_data = {
                "eol_date": eol_date,
                "support_end_date": support_end_date,
                "source_url": run.get("source_url"),
                "confidence": run.get("confidence"),
                "source": vendor_key,
            }

            # Calculate confidence if not provided by agent
            # Vendor scraping from official sites should have high confidence
            if raw_data["confidence"] is None or raw_data["confidence"] == 0:
                base_confidence = 0.80  # Vendor official site
                completeness_bonus = 0.0
                if eol_date:
                    completeness_bonus += 0.10
                if support_end_date:
                    completeness_bonus += 0.05
                if run.get("release_date"):
                    completeness_bonus += 0.03
                if run.get("source_url"):
                    completeness_bonus += 0.02

                calculated_confidence = min(0.95, base_confidence + completeness_bonus)
                raw_data["confidence"] = calculated_confidence
                logger.info(
                    "Vendor parsing calculated confidence=%.2f for %s %s (base=0.80, bonus=%.2f)",
                    calculated_confidence, software_name, version or "(any)", completeness_bonus
                )

            processed = process_eol_data(raw_data, software_name, version)
            processed["support_end_date"] = support_end_date or processed.get("support_end_date")
            processed["source_url"] = run.get("source_url") or processed.get("source_url")
            processed["agent_used"] = run.get("agent_used") or processed.get("agent_used")

            result = {
                "success": True,
                "data": processed,
                "confidence": processed.get("confidence"),
                "source_url": processed.get("source_url"),
                "agent_used": processed.get("agent_used"),
            }

            logger.info(
                "Vendor parsing persisting: software_name=%s, version=%s, vendor=%s, "
                "eol_date=%s, confidence=%s, agent_used=%s",
                software_name, version, vendor_key,
                run.get("eol_date"), processed.get("confidence"), run.get("agent_used")
            )

            try:
                # Try L1 upsert (may be skipped due to confidence check)
                upsert_success = await eol_inventory.upsert(software_name, version, result)
                if upsert_success:
                    logger.info(
                        "Vendor EOL cache L1 upsert SUCCESS for %s %s (vendor=%s)",
                        software_name, version or "(any)", vendor_key
                    )
                else:
                    logger.warning(
                        "Vendor EOL cache L1 upsert skipped (confidence) for %s %s (vendor=%s)",
                        software_name, version or "(any)", vendor_key
                    )

                # ALWAYS write to L2 PostgreSQL for vendor parsing, regardless of L1 result
                # This ensures vendor parsing results are visible in /eol-inventory page
                logger.info(
                    "Vendor parsing checking L2 write for %s %s: has_pool=%s",
                    software_name, version or "(any)", eol_inventory._has_pool()
                )
                if eol_inventory._has_pool():
                    record = eol_inventory._standardize_data(
                        software_name, version, result,
                        raw_software_name=software_name,
                        raw_version=version
                    )
                    logger.info(
                        "Vendor parsing standardize result for %s %s: record=%s",
                        software_name, version or "(any)", "present" if record else "None"
                    )
                    if record:
                        logger.info(
                            "Vendor parsing forcing L2 PG write for %s %s (vendor=%s)",
                            software_name, version or "(any)", vendor_key
                        )
                        # Change from fire-and-forget to await so we can see errors
                        await eol_inventory._pg_upsert(record)

            except Exception as exc:
                logger.error(
                    "Vendor EOL cache upsert EXCEPTION for %s %s (vendor=%s): %s",
                    software_name, version or "(any)", vendor_key, exc,
                    exc_info=True
                )

        await asyncio.gather(*(_persist_run(run) for run in runs))

    if not vendor_key or vendor_key not in vendor_map:
        raise HTTPException(status_code=404, detail=f"Vendor '{request.vendor}' not found")

    keywords: List[str] = list(vendor_map.get(vendor_key, []) or [])
    if request.limit and request.limit > 0:
        keywords = keywords[: request.limit]

    keywords = [kw for kw in keywords if kw]
    if not keywords:
        raise HTTPException(status_code=400, detail="No products configured for this vendor")

    def _extract_agent_urls(agent) -> List[Dict[str, Any]]:
        urls: List[Dict[str, Any]] = []
        if not agent:
            return urls

        try:
            raw_urls = []
            if hasattr(agent, "get_urls") and callable(getattr(agent, "get_urls")):
                raw_urls = agent.get_urls() or []
            elif hasattr(agent, "urls") and getattr(agent, "urls"):
                raw_urls = agent.urls
            elif hasattr(agent, "eol_urls") and getattr(agent, "eol_urls"):
                raw_urls = list(agent.eol_urls.values())

            for idx, entry in enumerate(raw_urls):
                if isinstance(entry, dict) and entry.get("url"):
                    urls.append({
                        "url": entry.get("url"),
                        "description": entry.get("description") or f"Source {idx + 1}",
                        "priority": entry.get("priority", idx + 1),
                        "active": entry.get("active", True),
                    })
                elif isinstance(entry, str):
                    urls.append({
                        "url": entry,
                        "description": f"Source {idx + 1}",
                        "priority": idx + 1,
                        "active": True,
                    })
        except Exception as exc:
            logger.debug("Unable to extract URLs for vendor %s: %s", vendor_key, exc)

        return urls

    agent = orchestrator.agents.get(vendor_key) if hasattr(orchestrator, "agents") else None
    vendor_urls = _extract_agent_urls(agent)

    # =========================================================================
    # GENERIC VENDOR PARSING PATH
    # =========================================================================
    # Try generic vendor parsing first - works for ANY vendor with fetch methods
    # This replaces vendor-specific branches (microsoft, nodejs, ubuntu, redhat)
    # Falls back to vendor-specific branches only if generic path fails
    # =========================================================================

    if agent and hasattr(agent, "eol_urls"):
        active_urls = [entry for entry in vendor_urls if entry.get("active", True)]

        if active_urls:
            # Try generic vendor parsing helper
            try:
                from utils.vendor_parsing_helper import parse_vendor_urls_generic

                logger.info(f"Attempting generic vendor parsing for {vendor_key} with {len(active_urls)} URLs")
                start_ts = time.time()

                runs = await parse_vendor_urls_generic(
                    agent=agent,
                    vendor_key=vendor_key,
                    active_urls=active_urls,
                )

                if runs:
                    successes = sum(1 for run in runs if run and run.get("success"))
                    timestamp = datetime.utcnow().isoformat()

                    await _persist_vendor_runs(runs)

                    urls_persisted = False
                    if vendor_urls:
                        try:
                            urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                                vendor=vendor_key,
                                urls=vendor_urls,
                                software_found=successes,
                                parsed_at=timestamp,
                            )
                        except Exception as exc:
                            logger.debug("Vendor URL persistence failed: %s", exc)

                    # Return even if successes == 0
                    # Vendor parsing should ONLY use configured URLs, not fall back to tiered pipeline
                    logger.info(
                        f"Generic vendor parsing completed for {vendor_key}: "
                        f"{successes}/{len(runs)} successful in {time.time() - start_ts:.2f}s"
                    )

                    return {
                        "success": True,
                        "vendor": vendor_key,
                        "mode": f"{vendor_key}_generic_urls",
                        "ignore_cache": bool(request.ignore_cache),
                        "runs": runs,
                        "summary": {
                            "requested": len(active_urls),
                            "successes": successes,
                            "failures": max(0, len(runs) - successes),
                        },
                        "vendor_urls": vendor_urls,
                        "url_count": len(vendor_urls),
                        "urls_persisted": urls_persisted,
                        "timestamp": timestamp,
                        "elapsed_seconds": round(time.time() - start_ts, 3),
                    }

            except ImportError:
                logger.warning("vendor_parsing_helper not available, falling back to vendor-specific branches")
            except Exception as exc:
                logger.warning(f"Generic vendor parsing failed for {vendor_key}: {exc}, trying vendor-specific branch")

    # =========================================================================
    # VENDOR-SPECIFIC BRANCHES (LEGACY - kept for backward compatibility)
    # =========================================================================

    if vendor_key == "microsoft":
        if not agent:
            raise HTTPException(status_code=500, detail="Microsoft agent not available")

        active_urls = [entry for entry in vendor_urls if entry.get("active", True)]
        if not active_urls:
            raise HTTPException(status_code=400, detail="No Microsoft URLs configured")

        start_ts = time.time()

        def _infer_microsoft_software(entry: Dict[str, Any]) -> str:
            url_lower = (entry.get("url") or "").lower()
            desc_lower = (entry.get("description") or "").lower()

            if "windows-server" in url_lower or "windows server" in desc_lower:
                return "windows server"
            if "windows11-release-information" in url_lower or "windows 11" in desc_lower:
                return "windows-11"
            if "release-health/release-information" in url_lower or "windows 10" in desc_lower:
                return "windows-10"
            if "sql-server" in url_lower or "sql server" in desc_lower:
                return "sql server"
            if "microsoft-365" in url_lower or "office" in url_lower or "office" in desc_lower:
                return "office"
            if "dotnet" in url_lower or "net" in desc_lower:
                return ".net"
            if "visualstudio" in url_lower or "visual studio" in desc_lower:
                return "visual studio"
            return "microsoft lifecycle"

        async def run_url(entry: Dict[str, Any]) -> Dict[str, Any]:
            software_hint = _infer_microsoft_software(entry)
            try:
                url = entry.get("url")
                records = await agent.fetch_all_from_url(url, software_hint)
                if records:
                    expanded = []
                    for record in records:
                        record_confidence = record.get("confidence")
                        if record_confidence is None:
                            record_confidence = 0.95
                        expanded.append({
                            "software_name": record.get("software_name") or software_hint,
                            "version": record.get("version") or record.get("cycle"),
                            "eol_date": record.get("eol"),
                            "support_end_date": record.get("support"),
                            "agent_used": "microsoft",
                            "confidence": record_confidence,
                            "source_url": url,
                            "success": True,
                            "mode": "microsoft_agent_urls",
                            "raw": record,
                        })
                    return expanded
            except Exception as exc:
                logger.debug("Vendor parsing expansion failed for %s: %s", software_hint, exc)
            try:
                result = await agent.fetch_from_url(entry.get("url"), software_hint)
            except Exception as exc:  # pragma: no cover - defensive
                return {
                    "software_name": software_hint,
                    "version": None,
                    "eol_date": None,
                    "support_end_date": None,
                    "agent_used": "microsoft",
                    "confidence": None,
                    "source_url": entry.get("url"),
                    "success": False,
                    "mode": "microsoft_agent_urls",
                    "error": str(exc),
                    "raw": None,
                }

            data_block = result.get("data") if isinstance(result, dict) else {}
            confidence = None
            if isinstance(data_block, dict):
                confidence = data_block.get("confidence") or result.get("confidence")
            elif isinstance(result, dict):
                confidence = result.get("confidence")

            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = None

            return {
                "software_name": (data_block or {}).get("software_name") or software_hint,
                "version": (data_block or {}).get("version"),
                "eol_date": (data_block or {}).get("eol_date"),
                "support_end_date": (data_block or {}).get("support_end_date"),
                "agent_used": (data_block or {}).get("agent_used") or "microsoft",
                "confidence": confidence,
                "source_url": entry.get("url"),
                "success": bool(result.get("success") if isinstance(result, dict) else False),
                "mode": "microsoft_agent_urls",
                "raw": result,
            }

        raw_runs = await asyncio.gather(*(run_url(entry) for entry in active_urls))
        runs: List[Dict[str, Any]] = []
        for entry in raw_runs:
            if isinstance(entry, list):
                runs.extend(entry)
            elif entry:
                runs.append(entry)
        successes = sum(1 for run in runs if run and run.get("success"))
        timestamp = datetime.utcnow().isoformat()

        await _persist_vendor_runs(runs)

        urls_persisted = False
        if vendor_urls:
            try:
                urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                    vendor=vendor_key,
                    urls=vendor_urls,
                    software_found=successes,
                    parsed_at=timestamp,
                )
            except Exception as exc:
                logger.debug("Vendor URL persistence failed: %s", exc)

        return {
            "success": True,
            "vendor": vendor_key,
            "mode": "microsoft_agent_urls",
            "ignore_cache": bool(request.ignore_cache),
            "runs": runs,
            "summary": {
                "requested": len(active_urls),
                "successes": successes,
                "failures": max(0, len(active_urls) - successes),
            },
            "vendor_urls": vendor_urls,
            "url_count": len(vendor_urls),
            "urls_persisted": urls_persisted,
            "timestamp": timestamp,
            "elapsed_seconds": round(time.time() - start_ts, 3),
        }

    if vendor_key == "nodejs":
        if not agent:
            raise HTTPException(status_code=500, detail="Node.js agent not available")

        active_urls = [entry for entry in vendor_urls if entry.get("active", True)]
        if not active_urls:
            raise HTTPException(status_code=400, detail="No Node.js URLs configured")

        start_ts = time.time()

        def _infer_nodejs_software(entry: Dict[str, Any]) -> str:
            url_lower = (entry.get("url") or "").lower()
            desc_lower = (entry.get("description") or "").lower()
            if "yarn" in url_lower or "yarn" in desc_lower:
                return "yarn"
            if "npm" in url_lower or "npm" in desc_lower:
                return "npm"
            return "nodejs"

        async def run_url(entry: Dict[str, Any]) -> Dict[str, Any]:
            software_hint = _infer_nodejs_software(entry)
            url = entry.get("url")
            try:
                records = await agent.fetch_all_from_url(url, software_hint)
                if records:
                    expanded = []
                    for record in records:
                        record_confidence = record.get("confidence")
                        if record_confidence is None:
                            record_confidence = 0.95
                        expanded.append({
                            "software_name": record.get("software_name") or software_hint,
                            "version": record.get("version") or record.get("cycle"),
                            "eol_date": record.get("eol"),
                            "support_end_date": record.get("support"),
                            "agent_used": "nodejs",
                            "confidence": record_confidence,
                            "source_url": url,
                            "success": True,
                            "mode": "nodejs_agent_urls",
                            "raw": record,
                        })
                    return expanded
            except Exception as exc:
                logger.debug("Node.js vendor parsing expansion failed for %s: %s", software_hint, exc)

            try:
                result = await agent.fetch_from_url(url, software_hint)
            except Exception as exc:  # pragma: no cover - defensive
                return {
                    "software_name": software_hint,
                    "version": None,
                    "eol_date": None,
                    "support_end_date": None,
                    "agent_used": "nodejs",
                    "confidence": None,
                    "source_url": url,
                    "success": False,
                    "mode": "nodejs_agent_urls",
                    "error": str(exc),
                    "raw": None,
                }

            data_block = result.get("data") if isinstance(result, dict) else {}
            confidence = None
            if isinstance(data_block, dict):
                confidence = data_block.get("confidence") or result.get("confidence")
            elif isinstance(result, dict):
                confidence = result.get("confidence")

            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = None

            return {
                "software_name": (data_block or {}).get("software_name") or software_hint,
                "version": (data_block or {}).get("version"),
                "eol_date": (data_block or {}).get("eol_date"),
                "support_end_date": (data_block or {}).get("support_end_date"),
                "agent_used": (data_block or {}).get("agent_used") or "nodejs",
                "confidence": confidence,
                "source_url": url,
                "success": bool(result.get("success") if isinstance(result, dict) else False),
                "mode": "nodejs_agent_urls",
                "raw": result,
            }

        raw_runs = await asyncio.gather(*(run_url(entry) for entry in active_urls))
        runs: List[Dict[str, Any]] = []
        for entry in raw_runs:
            if isinstance(entry, list):
                runs.extend(entry)
            elif entry:
                runs.append(entry)
        successes = sum(1 for run in runs if run and run.get("success"))
        timestamp = datetime.utcnow().isoformat()

        await _persist_vendor_runs(runs)

        urls_persisted = False
        if vendor_urls:
            try:
                urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                    vendor=vendor_key,
                    urls=vendor_urls,
                    software_found=successes,
                    parsed_at=timestamp,
                )
            except Exception as exc:
                logger.debug("Vendor URL persistence failed: %s", exc)

        return {
            "success": True,
            "vendor": vendor_key,
            "mode": "nodejs_agent_urls",
            "ignore_cache": bool(request.ignore_cache),
            "runs": runs,
            "summary": {
                "requested": len(active_urls),
                "successes": successes,
                "failures": max(0, len(active_urls) - successes),
            },
            "vendor_urls": vendor_urls,
            "url_count": len(vendor_urls),
            "urls_persisted": urls_persisted,
            "timestamp": timestamp,
            "elapsed_seconds": round(time.time() - start_ts, 3),
        }

    if vendor_key == "ubuntu":
        if not agent:
            raise HTTPException(status_code=500, detail="Ubuntu agent not available")

        active_urls = [entry for entry in vendor_urls if entry.get("active", True)]
        if not active_urls:
            raise HTTPException(status_code=400, detail="No Ubuntu URLs configured")

        start_ts = time.time()

        def _infer_ubuntu_software(entry: Dict[str, Any]) -> str:
            url_lower = (entry.get("url") or "").lower()
            desc_lower = (entry.get("description") or "").lower()
            if "canonical" in url_lower or "canonical" in desc_lower:
                return "canonical"
            if "snap" in url_lower or "snap" in desc_lower:
                return "snap"
            return "ubuntu"

        async def run_url(entry: Dict[str, Any]) -> Dict[str, Any]:
            software_hint = _infer_ubuntu_software(entry)
            url = entry.get("url")
            try:
                records = await agent.fetch_all_from_url(url, software_hint)
                if records:
                    expanded = []
                    for record in records:
                        record_confidence = record.get("confidence")
                        if record_confidence is None:
                            record_confidence = 0.95
                        expanded.append({
                            "software_name": record.get("software_name") or software_hint,
                            "version": record.get("version") or record.get("cycle"),
                            "eol_date": record.get("eol"),
                            "support_end_date": record.get("support"),
                            "agent_used": "ubuntu",
                            "confidence": record_confidence,
                            "source_url": url,
                            "success": True,
                            "mode": "ubuntu_agent_urls",
                            "raw": record,
                        })
                    return expanded
            except Exception as exc:
                logger.debug("Ubuntu vendor parsing expansion failed for %s: %s", software_hint, exc)

            try:
                result = await agent.get_eol_data(software_hint)
            except Exception as exc:  # pragma: no cover - defensive
                return {
                    "software_name": software_hint,
                    "version": None,
                    "eol_date": None,
                    "support_end_date": None,
                    "agent_used": "ubuntu",
                    "confidence": None,
                    "source_url": url,
                    "success": False,
                    "mode": "ubuntu_agent_urls",
                    "error": str(exc),
                    "raw": None,
                }

            data_block = result.get("data") if isinstance(result, dict) else {}
            confidence = None
            if isinstance(data_block, dict):
                confidence = data_block.get("confidence") or result.get("confidence")
            elif isinstance(result, dict):
                confidence = result.get("confidence")

            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = None

            return {
                "software_name": (data_block or {}).get("software_name") or software_hint,
                "version": (data_block or {}).get("version"),
                "eol_date": (data_block or {}).get("eol_date"),
                "support_end_date": (data_block or {}).get("support_end_date"),
                "agent_used": (data_block or {}).get("agent_used") or "ubuntu",
                "confidence": confidence,
                "source_url": url,
                "success": bool(result.get("success") if isinstance(result, dict) else False),
                "mode": "ubuntu_agent_urls",
                "raw": result,
            }

        raw_runs = await asyncio.gather(*(run_url(entry) for entry in active_urls))
        runs: List[Dict[str, Any]] = []
        for entry in raw_runs:
            if isinstance(entry, list):
                runs.extend(entry)
            elif entry:
                runs.append(entry)
        successes = sum(1 for run in runs if run and run.get("success"))
        timestamp = datetime.utcnow().isoformat()

        await _persist_vendor_runs(runs)

        urls_persisted = False
        if vendor_urls:
            try:
                urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                    vendor=vendor_key,
                    urls=vendor_urls,
                    software_found=successes,
                    parsed_at=timestamp,
                )
            except Exception as exc:
                logger.debug("Vendor URL persistence failed: %s", exc)

        return {
            "success": True,
            "vendor": vendor_key,
            "mode": "ubuntu_agent_urls",
            "ignore_cache": bool(request.ignore_cache),
            "runs": runs,
            "summary": {
                "requested": len(active_urls),
                "successes": successes,
                "failures": max(0, len(active_urls) - successes),
            },
            "vendor_urls": vendor_urls,
            "url_count": len(vendor_urls),
            "urls_persisted": urls_persisted,
            "timestamp": timestamp,
            "elapsed_seconds": round(time.time() - start_ts, 3),
        }

    if vendor_key == "redhat":
        if not agent:
            raise HTTPException(status_code=500, detail="Red Hat agent not available")

        active_urls = [entry for entry in vendor_urls if entry.get("active", True)]
        if not active_urls:
            raise HTTPException(status_code=400, detail="No Red Hat URLs configured")

        start_ts = time.time()

        def _infer_redhat_software(entry: Dict[str, Any]) -> str:
            """Infer software type from URL or description."""
            url_lower = (entry.get("url") or "").lower()
            desc_lower = (entry.get("description") or "").lower()

            if "rhel" in url_lower or "rhel" in desc_lower or "enterprise linux" in desc_lower:
                return "rhel"
            if "centos" in url_lower or "centos" in desc_lower:
                return "centos"
            if "fedora" in url_lower or "fedora" in desc_lower:
                return "fedora"
            return "rhel"  # default

        async def run_url(entry: Dict[str, Any]) -> Dict[str, Any]:
            software_hint = _infer_redhat_software(entry)
            url = entry.get("url")

            try:
                # Try fetch_all_from_url first (returns multiple versions)
                records = await agent.fetch_all_from_url(url, software_hint)
                if records:
                    expanded = []
                    for record in records:
                        record_confidence = record.get("confidence")
                        if record_confidence is None:
                            record_confidence = 0.85
                        expanded.append({
                            "software_name": record.get("software_name") or software_hint,
                            "version": record.get("version") or record.get("cycle"),
                            "eol_date": record.get("eol"),
                            "support_end_date": record.get("support"),
                            "agent_used": "redhat",
                            "confidence": record_confidence,
                            "source_url": url,
                            "success": True,
                            "mode": "redhat_agent_urls",
                            "raw": record,
                        })
                    return expanded
            except Exception as exc:
                logger.debug("Red Hat vendor parsing expansion failed for %s: %s", software_hint, exc)

            # Fallback to single fetch_from_url
            try:
                result = await agent.fetch_from_url(url, software_hint)
            except Exception as exc:  # pragma: no cover
                return {
                    "software_name": software_hint,
                    "version": None,
                    "eol_date": None,
                    "support_end_date": None,
                    "agent_used": "redhat",
                    "confidence": None,
                    "source_url": url,
                    "success": False,
                    "mode": "redhat_agent_urls",
                    "error": str(exc),
                    "raw": None,
                }

            data_block = result.get("data") if isinstance(result, dict) else {}
            confidence = None
            if isinstance(data_block, dict):
                confidence = data_block.get("confidence") or result.get("confidence")
            elif isinstance(result, dict):
                confidence = result.get("confidence")

            if confidence is not None:
                try:
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    confidence = None

            return {
                "software_name": (data_block or {}).get("software_name") or software_hint,
                "version": (data_block or {}).get("version"),
                "eol_date": (data_block or {}).get("eol_date"),
                "support_end_date": (data_block or {}).get("support_end_date"),
                "agent_used": (data_block or {}).get("agent_used") or "redhat",
                "confidence": confidence,
                "source_url": url,
                "success": bool(result.get("success") if isinstance(result, dict) else False),
                "mode": "redhat_agent_urls",
                "raw": result,
            }

        raw_runs = await asyncio.gather(*(run_url(entry) for entry in active_urls))
        runs: List[Dict[str, Any]] = []
        for entry in raw_runs:
            if isinstance(entry, list):
                runs.extend(entry)
            elif entry:
                runs.append(entry)

        successes = sum(1 for run in runs if run and run.get("success"))
        timestamp = datetime.utcnow().isoformat()

        await _persist_vendor_runs(runs)

        urls_persisted = False
        if vendor_urls:
            try:
                urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                    vendor=vendor_key,
                    urls=vendor_urls,
                    software_found=successes,
                    parsed_at=timestamp,
                )
            except Exception as exc:
                logger.debug("Vendor URL persistence failed: %s", exc)

        return {
            "success": True,
            "vendor": vendor_key,
            "mode": "redhat_agent_urls",
            "ignore_cache": bool(request.ignore_cache),
            "runs": runs,
            "summary": {
                "requested": len(active_urls),
                "successes": successes,
                "failures": max(0, len(active_urls) - successes),
            },
            "vendor_urls": vendor_urls,
            "url_count": len(vendor_urls),
            "urls_persisted": urls_persisted,
            "timestamp": timestamp,
            "elapsed_seconds": round(time.time() - start_ts, 3),
        }

    allowed_modes = {"agents_plus_internet", "agents_only", "internet_only"}
    mode = (request.mode or "agents_plus_internet").lower()
    if mode not in allowed_modes:
        mode = "agents_plus_internet"
    ignore_cache = bool(request.ignore_cache)
    start_ts = time.time()

    async def run_keyword(name: str) -> Dict[str, Any]:
        resolved_mode = mode
        try:
            if resolved_mode == "internet_only":
                result = await orchestrator.search_software_eol_internet(
                    software_name=name,
                    software_version=None,
                    search_ignore_cache=ignore_cache,
                )
                resolved_mode = "internet_only"
            elif resolved_mode == "agents_only":
                result = await orchestrator.search_software_eol(
                    software_name=name,
                    software_version=None,
                    search_include_internet=False,
                    search_ignore_cache=ignore_cache,
                    search_agent_only=True,
                )
                resolved_mode = "agents_only"
            else:
                result = await orchestrator.search_software_eol(
                    software_name=name,
                    software_version=None,
                    search_include_internet=True,
                    search_ignore_cache=ignore_cache,
                )
                resolved_mode = "agents_plus_internet"
        except Exception as exc:
            return {
                "software_name": name,
                "success": False,
                "error": str(exc),
                "mode": resolved_mode,
                "raw": None,
            }

        data_block = result.get("data") if isinstance(result, dict) else {}
        version = data_block.get("version") or data_block.get("software_version") if isinstance(data_block, dict) else None
        eol_date = None
        support_end_date = None
        if isinstance(data_block, dict):
            eol_date = data_block.get("eol_date") or data_block.get("support_end_date")
            support_end_date = data_block.get("support_end_date")

        agent_used = None
        if isinstance(result, dict):
            agent_used = result.get("agent_used")
            if not agent_used and isinstance(data_block, dict):
                agent_used = data_block.get("agent_used")

        confidence = None
        if isinstance(data_block, dict):
            confidence = data_block.get("confidence") or result.get("confidence")
        elif isinstance(result, dict):
            confidence = result.get("confidence")

        source_url = None
        if isinstance(data_block, dict):
            source_url = data_block.get("source_url") or result.get("source_url")
        elif isinstance(result, dict):
            source_url = result.get("source_url")

        success = bool(result.get("success") if isinstance(result, dict) else False)
        success = success or (isinstance(data_block, dict) and bool(data_block))

        return {
            "software_name": name,
            "version": version,
            "eol_date": eol_date,
            "support_end_date": support_end_date,
            "agent_used": agent_used,
            "confidence": confidence,
            "source_url": source_url,
            "success": success,
            "mode": resolved_mode,
            "raw": result,
        }

    runs = await asyncio.gather(*(run_keyword(keyword) for keyword in keywords))
    successes = sum(1 for run in runs if run and run.get("success"))
    timestamp = datetime.utcnow().isoformat()

    await _persist_vendor_runs(runs)

    urls_persisted = False
    if vendor_urls:
        try:
            urls_persisted = await vendor_url_inventory.upsert_vendor_urls(
                vendor=vendor_key,
                urls=vendor_urls,
                software_found=successes,
                parsed_at=timestamp,
            )
        except Exception as exc:
            logger.debug("Vendor URL persistence failed: %s", exc)

    return {
        "success": True,
        "vendor": vendor_key,
        "mode": mode,
        "ignore_cache": ignore_cache,
        "runs": runs,
        "summary": {
            "requested": len(keywords),
            "successes": successes,
            "failures": max(0, len(keywords) - successes),
        },
        "vendor_urls": vendor_urls,
        "url_count": len(vendor_urls),
        "urls_persisted": urls_persisted,
        "timestamp": timestamp,
        "elapsed_seconds": round(time.time() - start_ts, 3),
    }


@router.post("/api/analyze")
@write_endpoint(agent_name="analyze_inventory", timeout_seconds=60)
async def analyze_inventory_eol():
    """
    Comprehensive EOL risk analysis using multi-agent orchestration.
    
    Analyzes the entire software and OS inventory to identify EOL risks,
    prioritize updates, and provide actionable recommendations.
    
    Returns:
        MultiAgentResponse with risk analysis, affected systems, and
        communication history from all agents involved.
    
    Example Response:
        {
            "session_id": "uuid-here",
            "analysis_result": {
                "high_risk": 15,
                "medium_risk": 45,
                "low_risk": 200,
                "recommendations": [...]
            },
            "communication_history": [...],
            "timestamp": "2025-10-15T11:00:00Z"
        }
    """
    analysis = await _get_eol_orchestrator().analyze_inventory_eol_risks()
    communications = await _get_eol_orchestrator().get_communication_history()
    
    return MultiAgentResponse(
        session_id=_get_eol_orchestrator().session_id,
        analysis_result=analysis,
        communication_history=communications,
        timestamp=datetime.utcnow().isoformat()
    )


# ============================================================================
# EOL VERIFICATION & CACHING ENDPOINTS
# ============================================================================

@router.post("/api/verify-eol-result", response_model=StandardResponse)
@write_endpoint(agent_name="verify_eol", timeout_seconds=45)
async def verify_eol_result(request: VerifyEOLRequest):
    """
    Mark EOL result as verified or failed and cache with appropriate priority.
    
    Performs EOL lookup and caches the result with verification status.
    Failed verifications are removed from cache, while verified results
    are cached with high priority.
    
    Args:
        request: VerifyEOLRequest with software name, version, and verification status
    
    Returns:
        StandardResponse with verification details and cache status.
    
    Example Request:
        {
            "software_name": "Adobe Acrobat Reader",
            "software_version": "2020.012.20041",
            "agent_name": "adobe_lifecycle",
            "verification_status": "verified",
            "source_url": "https://adobe.com/lifecycle"
        }
    
    Example Response:
        {
            "success": true,
            "message": "EOL result verified and cached",
            "verification_status": "verified",
            "software_name": "Adobe Acrobat Reader",
            "agent_used": "adobe_lifecycle",
            "cache_updated": true
        }
    """
    verification_status = request.verification_status or "verified"
    is_verified = verification_status == "verified"
    is_failed = verification_status == "failed"
    
    # Get the orchestrator to perform the search 
    result = await _get_eol_orchestrator().get_autonomous_eol_data(
        software_name=request.software_name,
        version=request.software_version
    )
    
    # If we have a result, cache it with appropriate verification status
    if result.get('success') and result.get('data'):
        # Use eol_cache to handle verification status
        from utils.eol_cache import eol_cache
        if is_failed:
            # For failed verifications, delete the cache entry to clear it completely
            await eol_cache.delete_failed_cache_entry(
                software_name=request.software_name,
                version=request.software_version,
                agent_name=request.agent_name
            )
            return {
                "success": True,
                "message": f"Failed verification - cache entry removed for {request.software_name}",
                "verification_status": verification_status,
                "software_name": request.software_name,
                "software_version": request.software_version,
                "cache_cleared": True
            }
        else:
            # For verified results, update the cache with verification status
            await eol_cache.cache_response(
                software_name=request.software_name,
                version=request.software_version,
                agent_name=request.agent_name,
                response_data=result,
                verified=is_verified,
                source_url=request.source_url,
                priority=2  # High priority for verified results
            )
            return {
                "success": True,
                "message": f"EOL result verified and cached for {request.software_name}",
                "verification_status": verification_status,
                "software_name": request.software_name,
                "software_version": request.software_version,
                "agent_used": result.get('agent_used'),
                "cache_updated": True
            }
    else:
        return {
            "success": False,
            "message": f"Failed to find EOL data for {request.software_name}",
            "error": "No EOL data found to verify"
        }


@router.post("/api/cache-eol-result", response_model=StandardResponse)
@write_endpoint(agent_name="cache_eol", timeout_seconds=45)
async def cache_eol_result(request: CacheEOLRequest):
    """
    Manually cache EOL result for user validation.
    
    Performs EOL lookup and stores the result in cache for future queries.
    Useful for pre-caching known EOL data or validating cache behavior.
    
    Args:
        request: CacheEOLRequest with software name and version
    
    Returns:
        StandardResponse with cache operation status and agent information.
    
    Example Request:
        {
            "software_name": "MySQL",
            "software_version": "5.7"
        }
    
    Example Response:
        {
            "success": true,
            "message": "EOL result cached for MySQL",
            "software_name": "MySQL",
            "software_version": "5.7",
            "agent_used": "mysql_lifecycle",
            "timestamp": "2025-10-15T11:10:00Z"
        }
    """
    # Get the orchestrator to perform the search and cache it
    result = await _get_eol_orchestrator().get_autonomous_eol_data(
        software_name=request.software_name,
        version=request.software_version
    )
    
    # If we have a result, the caching should have been handled by the agent
    if result.get('success') and result.get('data'):
        return {
            "success": True,
            "message": f"EOL result cached for {request.software_name}",
            "software_name": request.software_name,
            "software_version": request.software_version,
            "agent_used": result.get('agent_used'),
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        return {
            "success": False,
            "message": f"Failed to find EOL data for {request.software_name}",
            "error": "No EOL data found to cache"
        }


# ============================================================================
# EOL TABLE ENDPOINTS
# ============================================================================


@router.get("/api/eol-inventory", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_inventory_list", timeout_seconds=20)
async def list_eol_inventory_records(
    request: Request,
    search: Optional[str] = None,
    software_name: Optional[str] = None,
    version: Optional[str] = None,
    sort_column: str = "updated_at",
    sort_direction: str = "DESC",
    limit: int = 25,
    offset: int = 0,
    page: int = 1,
    page_size: int = 25,
):
    """Return EOL inventory records for UI browsing with server-side pagination."""
    try:
        eol_repo = request.app.state.eol_repo

        # Support both offset/limit style and page/page_size style.
        # page/page_size takes precedence when page > 0.
        if page > 1 or page_size != 25:
            effective_limit = page_size
            effective_offset = (page - 1) * page_size
        else:
            effective_limit = limit
            effective_offset = offset

        # Accept software_name or search as the filter term.
        filter_term = software_name or search or None

        total_count = await eol_repo.count_records(search=filter_term)
        records = await eol_repo.list_records(
            search=filter_term, sort_column=sort_column,
            sort_direction=sort_direction, limit=effective_limit, offset=effective_offset,
        )
        total_pages = max(1, (total_count + effective_limit - 1) // effective_limit)
        return StandardResponse(
            success=True,
            data=records,
            count=len(records),
            message=f"Retrieved {len(records)} of {total_count} EOL records",
            metadata={
                "total_count": total_count,
                "total_pages": total_pages,
                "page": page,
                "page_size": effective_limit,
                "offset": effective_offset,
            },
        )
    except Exception as exc:
        logger.debug("EOL inventory list failed: %s", exc)
        response = StandardResponse.error_response(error=str(exc))
        return response.to_dict()


@router.get("/api/eol-inventory/vendor/{vendor}", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_inventory_vendor", timeout_seconds=20)
async def list_eol_by_vendor(vendor: str, limit: int = 100, offset: int = 0):
    """Return EOL records filtered by vendor name from PostgreSQL."""
    records, total = await eol_inventory.list_by_vendor(vendor, limit=limit, offset=offset)
    return StandardResponse.success_response(
        data={"items": records, "total": total, "vendor": vendor},
        message=f"Retrieved {len(records)} of {total} EOL records for vendor '{vendor}'",
    ).to_dict()


@router.get("/api/eol-inventory/{software_key}", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_inventory_get", timeout_seconds=15)
async def get_eol_record(request: Request, software_key: str):
    """Retrieve a single EOL record by software_key."""
    eol_repo = request.app.state.eol_repo
    record = await eol_repo.get_by_key(software_key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"EOL record not found: {software_key}")
    return StandardResponse(success=True, data=record, message="EOL record retrieved")


@router.put("/api/eol-inventory/{record_id}", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_update", timeout_seconds=20)
async def update_eol_inventory_record(
    record_id: str,
    software_key: str,
    request: Request,
    body: UpdateEolRecordRequest = None,
):
    """Update a stored EOL record via eol_repo upsert."""
    eol_repo = request.app.state.eol_repo
    record_data = body.dict(exclude_unset=True) if body else {}
    if not record_data:
        response = StandardResponse.error_response("No update fields provided")
        return response.to_dict()

    try:
        await eol_repo.upsert_eol_record(
            software_key=software_key,
            software_name=record_data.get("software_name", ""),
            version_key=record_data.get("version"),
            status=record_data.get("status"),
            risk_level=record_data.get("risk_level"),
            eol_date=record_data.get("eol_date"),
            extended_end_date=record_data.get("support_end_date"),
            is_eol=record_data.get("status") in ("expired", "eol") if record_data.get("status") else False,
            item_type=None,
            lifecycle_url=record_data.get("source_url"),
        )
        return StandardResponse(success=True, data=record_data, message="EOL record saved")
    except Exception as e:
        logger.error("Failed to upsert EOL record: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"EOL record save failed: {str(e)}")


@router.delete("/api/eol-inventory/{record_id}", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_delete", timeout_seconds=20)
async def delete_eol_inventory_record(record_id: str, software_key: str):
    """Delete a stored EOL record."""
    deleted = await eol_inventory.delete_record(record_id, software_key)
    if not deleted:
        response = StandardResponse.error_response("Record not found or delete failed")
        return response.to_dict()

    response = StandardResponse.success_response(
        data=[],
        metadata={"operation": "delete", "id": record_id},
        message="Record deleted",
    )
    return response.to_dict()


@router.post("/api/eol-inventory/bulk-delete", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_bulk_delete", timeout_seconds=30)
async def bulk_delete_eol_inventory_records(request: BulkDeleteRequest):
    """Delete multiple EOL records in one call."""
    items = request.items or []
    if not items:
        response = StandardResponse.error_response("No items provided for deletion")
        return response.to_dict()

    results = await eol_inventory.delete_records([item.dict() for item in items])
    deleted = results.get("deleted", 0)
    failed = results.get("failed", [])

    if deleted == 0 and failed:
        response = StandardResponse.error_response("Bulk delete failed", error_details=failed)
        return response.to_dict()

    response = StandardResponse.success_response(
        data=[],
        metadata={"requested": len(items), **results},
        message=f"Deleted {deleted} record(s)" if deleted else "No records deleted",
    )
    return response.to_dict()


@router.post("/api/eol-inventory/purge-all", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_purge_all", timeout_seconds=60)
async def purge_all_eol_inventory_records():
    """Delete ALL records from the eol_table.

    Also clears the orchestrator in-memory cache so stale data is not served
    from memory after the purge.
    """
    from main import get_eol_orchestrator
    # Clear orchestrator in-memory cache first
    try:
        orchestrator = get_eol_orchestrator()
        memory_cleared = len(orchestrator.eol_cache)
        orchestrator.eol_cache.clear()
    except Exception:
        memory_cleared = 0

    deleted = await eol_inventory.purge_all()

    response = StandardResponse.success_response(
        data=[],
        metadata={"deleted": deleted, "memory_cleared": memory_cleared},
        message=f"Purged {deleted} record(s) from EOL inventory",
    )
    return response.to_dict()


# ============================================================================
# EOL AGENT RESPONSE TRACKING ENDPOINTS
# ============================================================================

@router.get("/api/eol-agent-responses", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_agent_responses", timeout_seconds=15)
async def get_eol_agent_responses(request: Request, limit: int = 1000, offset: int = 0):
    """
    Get tracked EOL agent responses from the database.

    Retrieves historical EOL search results stored in eol_agent_responses table.

    Returns:
        StandardResponse with list of agent responses, sorted by timestamp (newest first).
    """
    eol_repo = getattr(request.app.state, 'eol_repo', None)
    if eol_repo is None:
        logger.error("❌ eol_repo not found on app.state - startup may not have completed")
        return StandardResponse(
            success=False,
            data=[],
            count=0,
            message="Repository not initialized - please try again in a moment",
        )

    responses = await eol_repo.list_recent_responses(limit=limit, offset=offset)
    return StandardResponse(
        success=True,
        data=responses,
        count=len(responses),
        message=f"Retrieved {len(responses)} agent responses",
    )


@router.get("/api/eol-agent-responses/session/{session_id}", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_session_responses", timeout_seconds=15)
async def get_session_responses(request: Request, session_id: str):
    """Return all agent responses for a given session, ordered ASC."""
    eol_repo = request.app.state.eol_repo
    responses = await eol_repo.get_responses_by_session(session_id)
    return StandardResponse(
        success=True,
        data=responses,
        count=len(responses),
    )


@router.post("/api/eol-agent-responses/clear", response_model=StandardResponse)
@write_endpoint(agent_name="clear_eol_responses", timeout_seconds=30)
async def clear_eol_agent_responses():
    """
    Clear all tracked EOL agent responses from both orchestrators.
    
    Removes all historical EOL search responses from memory, resetting
    the response tracking for both inventory assistant and EOL orchestrators.
    
    Returns:
        StandardResponse indicating success and counts cleared from each source.
    
    Example Response:
        {
            "success": true,
            "message": "EOL agent responses cleared",
            "cleared_counts": {
                "inventory_asst_orchestrator": 20,
                "eol_orchestrator": 25
            },
            "total_cleared": 45
        }
    """
    cleared_counts = {
        "inventory_asst_orchestrator": 0,
        "eol_orchestrator": 0
    }
    
    # Clear inventory assistant orchestrator responses
    inventory_orchestrator = _get_inventory_asst_orchestrator()
    if inventory_orchestrator and hasattr(inventory_orchestrator, 'clear_eol_agent_responses'):
        count = inventory_orchestrator.clear_eol_agent_responses()
        cleared_counts["inventory_asst_orchestrator"] = count
        logger.info(f"🧹 [API] Cleared {count} EOL responses from inventory assistant orchestrator")
    
    # Clear EOL orchestrator responses
    eol_orchestrator = _get_eol_orchestrator()
    if eol_orchestrator and hasattr(eol_orchestrator, 'clear_eol_agent_responses'):
        count = eol_orchestrator.clear_eol_agent_responses()
        cleared_counts["eol_orchestrator"] = count
        logger.info(f"🧹 [API] Cleared {count} EOL responses from EOL orchestrator")
    
    total_cleared = sum(cleared_counts.values())
    
    return {
        "success": True,
        "message": f"Cleared {total_cleared} EOL agent responses",
        "cleared_counts": cleared_counts,
        "total_cleared": total_cleared,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/eol/batch-enrich", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_batch_enrich", timeout_seconds=60)
async def batch_enrich_eol(request: BatchEOLRequest):
    """
    Fetch EOL data for multiple software items in parallel.
    
    This endpoint is designed for UI-driven async enrichment after fast initial load.
    Returns EOL data from cache first, then fetches missing items from agents.
    
    Args:
        request: BatchEOLRequest with list of items and concurrency limit
    
    Returns:
        StandardResponse with EOL data for each item
        
    Example Request:
        {
            "items": [
                {"name": "Python", "version": "3.8"},
                {"name": "Node.js", "version": "14.0"}
            ],
            "max_concurrent": 5
        }
    
    Example Response:
        {
            "success": true,
            "data": [
                {
                    "software_name": "Python",
                    "version": "3.8",
                    "eol_date": "2024-10-01",
                    "source": "cache"
                },
                ...
            ]
        }
    """
    if not request.items:
        return {"success": True, "data": [], "message": "No items to enrich"}
    
    if len(request.items) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 items per batch request"
        )
    
    orchestrator = _get_eol_orchestrator()
    results = []
    semaphore = asyncio.Semaphore(min(request.max_concurrent, 10))
    
    async def fetch_one(item: Dict[str, str]) -> Dict[str, Any]:
        name = item.get("name") or item.get("software_name")
        version = item.get("version") or item.get("software_version")
        
        if not name:
            return {"error": "Missing software name"}
        
        async with semaphore:
            # Try cache first
            try:
                cached = await eol_inventory.get(name, version)
                if cached:
                    return {
                        "software_name": name,
                        "version": version,
                        "eol_date": cached.get("eol_date"),
                        "support_end_date": cached.get("support_end_date"),
                        "status": cached.get("status"),
                        "risk_level": cached.get("risk_level"),
                        "confidence": cached.get("confidence"),
                        "source": "cache"
                    }
            except Exception as e:
                logger.debug(f"Cache lookup failed for {name} {version}: {e}")
            
            # Fetch from agents
            try:
                result = await orchestrator.get_autonomous_eol_data(name, version, item_type="os")
                if result and result.get("success"):
                    data = result.get("data", {})
                    return {
                        "software_name": name,
                        "version": version,
                        "eol_date": data.get("eol_date"),
                        "support_end_date": data.get("support_end_date"),
                        "status": data.get("status"),
                        "risk_level": data.get("risk_level"),
                        "confidence": data.get("confidence"),
                        "source": result.get("agent_used") or "agent"
                    }
            except Exception as e:
                logger.warning(f"EOL lookup failed for {name} {version}: {e}")
            
            return {
                "software_name": name,
                "version": version,
                "error": "EOL data not available"
            }
    
    # Fetch all in parallel with semaphore limiting concurrency
    tasks = [fetch_one(item) for item in request.items]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error dicts
    clean_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            clean_results.append({
                "software_name": request.items[i].get("name", "unknown"),
                "error": str(result)
            })
        else:
            clean_results.append(result)
    
    return {
        "success": True,
        "data": clean_results,
        "total_items": len(clean_results),
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# EOL MANAGEMENT VIEW ENDPOINT
# ============================================================================

@router.get("/api/eol-management", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_management", timeout_seconds=20)
async def get_eol_management(
    request: Request,
    subscription_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return VMs with their EOL status for the management view."""
    eol_repo = request.app.state.eol_repo
    vms = await eol_repo.get_vm_eol_management(
        subscription_id=subscription_id, limit=limit, offset=offset,
    )
    return StandardResponse(
        success=True,
        data={"items": vms, "total": len(vms), "offset": offset, "limit": limit},
        count=len(vms),
        message=f"Retrieved {len(vms)} VMs with EOL status" if vms else "No VM EOL management data available",
    )
