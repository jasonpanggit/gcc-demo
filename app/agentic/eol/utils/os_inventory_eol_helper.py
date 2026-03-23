"""OS inventory EOL enrichment helpers.

Extracted from EOLOrchestratorAgent to keep the orchestrator file lean.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

from utils.eol_data_processor import process_eol_data

logger = logging.getLogger(__name__)

MAX_CONCURRENT_EOL_ANALYSIS = 10


async def enrich_os_inventory_with_eol(
    os_items: List[Dict[str, Any]],
    eol_cache: Dict[str, Any],
    cache_ttl: int,
    session_id: str,
    fetch_eol: Callable[..., Coroutine],
) -> Dict[str, Any]:
    """Enrich a list of OS inventory items with EOL data.

    Args:
        os_items: Raw OS inventory items from os_inventory agent.
        eol_cache: In-memory EOL cache (mutated in place for cache hits).
        cache_ttl: Cache TTL in seconds.
        session_id: Current session ID for result metadata.
        fetch_eol: Async callable matching get_autonomous_eol_data signature.

    Returns:
        Enriched inventory response dict.
    """
    start_time = time.time()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EOL_ANALYSIS)

    async def _analyze(os_item: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            return await _analyze_os_item(os_item, eol_cache, cache_ttl, fetch_eol)

    results = await asyncio.gather(*[_analyze(i) for i in os_items], return_exceptions=True)

    enriched = []
    for os_item, res in zip(os_items, results):
        item = {**os_item}
        if isinstance(res, dict) and res.get("success"):
            eol = res.get("eol_data", {})
            item.update({
                "eol_date": eol.get("eol_date"),
                "eol_status": eol.get("status", "Unknown"),
                "support_status": eol.get("support_status"),
                "risk_level": eol.get("risk_level", "unknown"),
                "days_until_eol": eol.get("days_until_eol"),
                "eol_source": eol.get("source"),
                "eol_confidence": eol.get("confidence", 0.5),
            })
        else:
            item.update({"eol_date": None, "eol_status": "Unknown", "support_status": "Unknown", "risk_level": "unknown", "days_until_eol": None, "eol_source": None, "eol_confidence": 0.0})
        enriched.append(item)

    return {
        "success": True,
        "data": enriched,
        "summary": {
            "total_items": len(enriched),
            "items_with_eol": sum(1 for i in enriched if i.get("eol_date")),
            "critical_items": sum(1 for i in enriched if i.get("risk_level") == "critical"),
            "high_risk_items": sum(1 for i in enriched if i.get("risk_level") == "high"),
            "analysis_time": time.time() - start_time,
            "cache_hits": sum(1 for r in results if isinstance(r, dict) and r.get("cache_hit")),
        },
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _analyze_os_item(
    os_item: Dict[str, Any],
    eol_cache: Dict[str, Any],
    cache_ttl: int,
    fetch_eol: Callable[..., Coroutine],
) -> Dict[str, Any]:
    os_name = os_item.get("os_name") or os_item.get("name", "")
    os_version = os_item.get("os_version") or os_item.get("version", "")
    if not os_name:
        return {"success": False, "error": "No OS name provided"}

    cache_key = f"os_eol_{os_name}_{os_version}".lower().replace(" ", "_")
    if cache_key in eol_cache:
        entry = eol_cache[cache_key]
        if datetime.now(timezone.utc) - entry["timestamp"] < timedelta(seconds=cache_ttl):
            return {"success": True, "eol_data": entry["data"], "cache_hit": True}

    eol_result = await fetch_eol(os_name, os_version, item_type="os")
    if eol_result.get("success") and eol_result.get("data"):
        eol_data = process_eol_data(eol_result["data"], os_name, os_version)
        eol_cache[cache_key] = {"data": eol_data, "timestamp": datetime.now(timezone.utc)}
        return {"success": True, "eol_data": eol_data, "cache_hit": False}

    return {"success": False, "error": "No EOL data found"}
