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
from fastapi import APIRouter, HTTPException
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
from utils.vendor_url_inventory import vendor_url_inventory
from agents.eol_orchestrator import DEFAULT_VENDOR_ROUTING

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


class BulkDeleteItem(BaseModel):
    record_id: str
    software_key: str


class BulkDeleteRequest(BaseModel):
    items: List[BulkDeleteItem]


# ============================================================================
# EOL QUERY ENDPOINTS
# ============================================================================

@router.get("/api/eol", response_model=StandardResponse)
@standard_endpoint(agent_name="eol_search", timeout_seconds=30)
async def get_eol(name: str, version: Optional[str] = None):
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
    eol_data = await _get_eol_orchestrator().get_eol_data(name, version)
    
    if not eol_data.get("data"):
        raise HTTPException(status_code=404, detail=f"No EOL data found for {name}")
    
    return {
        "software_name": name,
        "version": version,
        "primary_source": eol_data["primary_source"],
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
        fallback = {key: list(val) for key, val in DEFAULT_VENDOR_ROUTING.items()}
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
            if not run or not run.get("success"):
                return

            software_name = run.get("software_name")
            if not software_name:
                return

            version = run.get("version")
            eol_date = run.get("eol_date")
            support_end_date = run.get("support_end_date")
            if not eol_date and not support_end_date:
                return

            raw_data = {
                "eol_date": eol_date,
                "support_end_date": support_end_date,
                "source_url": run.get("source_url"),
                "confidence": run.get("confidence"),
                "source": vendor_key,
            }

            processed = orchestrator._process_eol_data(raw_data, software_name, version)
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

            try:
                await eol_inventory.upsert(software_name, version, result)
            except Exception as exc:
                logger.debug("Vendor EOL cache upsert failed for %s %s: %s", software_name, version or "(any)", exc)

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
        from utils.cosmos_cache import base_cosmos
        from utils.eol_cache import eol_cache
        if getattr(base_cosmos, 'initialized', False):
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
                "success": True,
                "message": "Verification recorded (Cosmos DB not initialized)",
                "verification_status": verification_status,
                "cache_updated": False
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
    limit: int = 100,
    software_name: Optional[str] = None,
    version: Optional[str] = None,
):
    """Return recent Cosmos EOL table entries for UI browsing."""
    try:
        items = await eol_inventory.list_recent(
            limit=limit,
            software_name=software_name,
            version=version,
        )

        response = StandardResponse.success_response(
            data=items,
            metadata={
                "limit": limit,
                "software_name": software_name,
                "version": version,
            },
        )
        return response.to_dict()
    except Exception as exc:
        logger.debug("EOL inventory list failed: %s", exc)
        response = StandardResponse.error_response(error=str(exc))
        return response.to_dict()


@router.put("/api/eol-inventory/{record_id}", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_update", timeout_seconds=20)
async def update_eol_inventory_record(
    record_id: str,
    software_key: str,
    request: UpdateEolRecordRequest,
):
    """Update a stored EOL record in Cosmos."""
    updates: Dict[str, Any] = {k: v for k, v in request.dict(exclude_unset=True).items()}
    if not updates:
        response = StandardResponse.error_response("No update fields provided")
        return response.to_dict()

    updated = await eol_inventory.update_record(record_id, software_key, updates)
    if not updated:
        response = StandardResponse.error_response("Record not found or update failed")
        return response.to_dict()

    response = StandardResponse.success_response(
        data=[updated],
        metadata={"operation": "update", "id": record_id},
    )
    return response.to_dict()


@router.delete("/api/eol-inventory/{record_id}", response_model=StandardResponse)
@write_endpoint(agent_name="eol_inventory_delete", timeout_seconds=20)
async def delete_eol_inventory_record(record_id: str, software_key: str):
    """Delete a stored EOL record in Cosmos."""
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
    """Delete multiple EOL records in Cosmos in one call."""
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


# ============================================================================
# EOL AGENT RESPONSE TRACKING ENDPOINTS
# ============================================================================

@router.get("/api/eol-agent-responses", response_model=StandardResponse)
@readonly_endpoint(agent_name="eol_agent_responses", timeout_seconds=15)
async def get_eol_agent_responses():
    """
    Get all tracked EOL agent responses from both Inventory Assistant and EOL orchestrators.
    
    Retrieves historical EOL search results from all orchestrators, including
    which agents were used, confidence scores, and timestamps.
    
    Returns:
        StandardResponse with list of EOL responses from all sources,
        sorted by timestamp (newest first).
    
    Example Response:
        {
            "success": true,
            "responses": [
                {
                    "software_name": "Windows Server 2012 R2",
                    "agent_used": "microsoft_lifecycle",
                    "confidence": 0.95,
                    "timestamp": "2025-10-15T11:15:00Z",
                    "orchestrator_type": "eol_orchestrator"
                }
            ],
            "count": 45,
            "sources": {
                "inventory_asst_orchestrator": 20,
                "eol_orchestrator": 25
            }
        }
    """
    all_responses = []
    
    # Get responses from Inventory Assistant orchestrator
    inventory_orchestrator = _get_inventory_asst_orchestrator()
    if inventory_orchestrator and hasattr(inventory_orchestrator, 'get_eol_agent_responses'):
        inventory_responses = inventory_orchestrator.get_eol_agent_responses()
        # Mark these as from the inventory assistant orchestrator
        for response in inventory_responses:
            response['orchestrator_type'] = 'inventory_asst_orchestrator'
        all_responses.extend(inventory_responses)
        logger.info(f"🔍 [API] Inventory assistant orchestrator returned {len(inventory_responses)} EOL responses")
    else:
        logger.warning("🔍 [API] Inventory assistant orchestrator not available or missing get_eol_agent_responses method")
    
    # Get responses from EOL orchestrator
    eol_orchestrator = _get_eol_orchestrator()
    if eol_orchestrator and hasattr(eol_orchestrator, 'get_eol_agent_responses'):
        eol_responses = eol_orchestrator.get_eol_agent_responses()
        # Mark these as from eol orchestrator
        for response in eol_responses:
            response['orchestrator_type'] = 'eol_orchestrator'
        all_responses.extend(eol_responses)
        logger.info(f"🔍 [API] EOL orchestrator returned {len(eol_responses)} EOL responses")
    else:
        logger.warning("🔍 [API] EOL orchestrator not available or missing get_eol_agent_responses method")
    
    # Sort by timestamp (newest first)
    all_responses.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    logger.info(f"🔍 [API] Total EOL responses returned: {len(all_responses)}")
    
    # Return in StandardResponse format - data field contains the responses
    return {
        "success": True,
        "data": all_responses,  # Changed from "responses" to "data" for StandardResponse compatibility
        "count": len(all_responses),
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {
            "sources": {
                "inventory_asst_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'inventory_asst_orchestrator']),
                "eol_orchestrator": len([r for r in all_responses if r.get('orchestrator_type') == 'eol_orchestrator'])
            }
        }
    }


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
