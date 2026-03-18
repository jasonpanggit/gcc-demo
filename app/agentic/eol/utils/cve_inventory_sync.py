"""Inventory-driven CVE cache warming.

Discovers normalized OS identities from cached inventory sources and prefetches
CVEs for newly observed operating systems so the CVE cache stays aligned with
the environments actually present in the estate.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from models.cve_models import VMScanTarget
    from utils.normalization import normalize_os_name_version
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_models import VMScanTarget
    from app.agentic.eol.utils.normalization import normalize_os_name_version


logger = logging.getLogger(__name__)

OS_SYNC_CONTAINER_ID = "cve_inventory_sync_state"
OS_SYNC_DOCUMENT_ID = "default"
OS_SYNC_PARTITION_KEY = "inventory_os_sync"


class CVEInventorySyncStateStore:
    """In-memory store for the set of normalized inventory OS identities already synced."""

    def __init__(self, container_id: str = OS_SYNC_CONTAINER_ID):
        self.container_id = container_id
        self._fallback_state: Dict[str, Any] = {
            "id": OS_SYNC_DOCUMENT_ID,
            "sync_type": OS_SYNC_PARTITION_KEY,
            "synced_os_keys": [],
            "os_entries": [],
            "last_synced_at": None,
        }

    async def load(self) -> Dict[str, Any]:
        return deepcopy(self._fallback_state)

    async def save(self, state: Dict[str, Any]) -> None:
        normalized = {
            "id": OS_SYNC_DOCUMENT_ID,
            "sync_type": OS_SYNC_PARTITION_KEY,
            "synced_os_keys": sorted(set(state.get("synced_os_keys") or [])),
            "os_entries": list(state.get("os_entries") or []),
            "last_synced_at": state.get("last_synced_at") or datetime.now(timezone.utc).isoformat(),
        }
        self._fallback_state = deepcopy(normalized)


def _vendor_for_os(normalized_name: str) -> Optional[str]:
    vendor_map = {
        "ubuntu": "ubuntu",
        "windows server": "microsoft",
        "windows": "microsoft",
        "rhel": "redhat",
        "centos": "centos",
        "debian": "debian",
    }
    return vendor_map.get(normalized_name)


def _normalize_inventory_os(os_name: Optional[str], os_version: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not os_name:
        return None, None

    if str(os_name).strip().lower() == "windowsserver":
        os_name = "Windows Server"
        release_year = re.search(r"(20\d{2}|19\d{2})", str(os_version or ""))
        if release_year:
            os_version = release_year.group(1)

    normalized_name, normalized_version = normalize_os_name_version(os_name, os_version)
    if not normalized_name:
        return None, None

    return normalized_name.strip().lower(), (normalized_version or None)


def _os_key(normalized_name: str, normalized_version: Optional[str]) -> str:
    return f"{normalized_name}::{(normalized_version or '').strip().lower()}"


def _major_version(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    match = re.search(r"\d+", str(value))
    return match.group(0) if match else None


def _build_inventory_cpe_names(normalized_name: str, normalized_version: Optional[str]) -> List[str]:
    version = (normalized_version or "").strip().lower()
    if not version:
        return []

    if normalized_name == "windows server" and version.isdigit():
        return [f"cpe:2.3:o:microsoft:windows_server_{version}:-:*:*:*:*:*:*:*"]

    if normalized_name == "ubuntu":
        return [f"cpe:2.3:o:canonical:ubuntu_linux:{version}:*:*:*:*:*:*:*"]

    major_version = _major_version(version)
    if normalized_name == "rhel" and major_version:
        return [f"cpe:2.3:o:redhat:enterprise_linux:{major_version}:*:*:*:*:*:*:*"]

    if normalized_name == "debian" and major_version:
        return [f"cpe:2.3:o:debian:debian_linux:{major_version}:*:*:*:*:*:*:*"]

    return []


def _build_inventory_live_queries(identity: Dict[str, Any], limit_per_os: Optional[int]) -> List[Dict[str, Any]]:
    vendor = _vendor_for_os(identity["normalized_name"])
    keyword_parts = [identity["normalized_name"]]
    if identity.get("normalized_version"):
        keyword_parts.append(str(identity["normalized_version"]))
    keyword = " ".join(keyword_parts)

    cpe_names = _build_inventory_cpe_names(
        identity["normalized_name"],
        identity.get("normalized_version"),
    )
    if cpe_names:
        return [
            {
                "mode": "cpe",
                "query": None,
                "source": "nvd",
                "limit": limit_per_os,
                "filters": {
                    "vendor": vendor,
                    "keyword": keyword,
                },
                "nvd_filters": {"cpeName": cpe_name},
            }
            for cpe_name in cpe_names
        ]

    return [
        {
            "mode": "keyword",
            "query": keyword,
            "source": None,
            "limit": limit_per_os,
            "filters": {
                "vendor": vendor,
                "keyword": keyword,
            },
            "nvd_filters": {},
        }
    ]


def _merge_identity(
    bucket: Dict[str, Dict[str, Any]],
    normalized_name: Optional[str],
    normalized_version: Optional[str],
    raw_name: Optional[str],
    raw_version: Optional[str],
    source: str,
) -> None:
    if not normalized_name:
        return

    key = _os_key(normalized_name, normalized_version)
    existing = bucket.get(key)
    if existing is None:
        bucket[key] = {
            "key": key,
            "normalized_name": normalized_name,
            "normalized_version": normalized_version,
            "display_name": normalized_name.title() if normalized_name != "rhel" else "RHEL",
            "raw_examples": [],
            "sources": [],
        }
        existing = bucket[key]

    raw_entry = {
        "os_name": raw_name,
        "os_version": raw_version,
        "source": source,
    }
    if raw_entry not in existing["raw_examples"]:
        existing["raw_examples"].append(raw_entry)
    if source not in existing["sources"]:
        existing["sources"].append(source)


async def discover_inventory_os_identities(
    *,
    eol_orchestrator: Any,
    cve_scanner: Any,
) -> List[Dict[str, Any]]:
    """Collect normalized OS identities from the inventory sources used by the app."""
    bucket: Dict[str, Dict[str, Any]] = {}

    try:
        os_agent = getattr(eol_orchestrator, "agents", {}).get("os_inventory") if eol_orchestrator else None
        if os_agent:
            result = await os_agent.get_os_inventory(days=90, limit=None, use_cache=True)
            for item in result.get("data") or []:
                normalized_name, normalized_version = _normalize_inventory_os(
                    item.get("os_name") or item.get("name"),
                    item.get("os_version") or item.get("version"),
                )
                _merge_identity(
                    bucket,
                    normalized_name,
                    normalized_version,
                    item.get("os_name") or item.get("name"),
                    item.get("os_version") or item.get("version"),
                    "os_inventory",
                )
    except Exception as exc:
        logger.warning("Failed to discover OS identities from OS inventory: %s", exc)

    try:
        if cve_scanner:
            vm_targets = await cve_scanner.get_vm_targets(include_arc=True)
            for vm in vm_targets or []:
                normalized_name, normalized_version = _normalize_inventory_os(vm.os_name or vm.os_type, vm.os_version)
                _merge_identity(
                    bucket,
                    normalized_name,
                    normalized_version,
                    vm.os_name or vm.os_type,
                    vm.os_version,
                    "vm_inventory",
                )
    except Exception as exc:
        logger.warning("Failed to discover OS identities from VM inventory: %s", exc)

    discovered = list(bucket.values())
    discovered.sort(key=lambda item: (item["normalized_name"], item.get("normalized_version") or ""))
    return discovered


async def sync_inventory_os_cves(
    *,
    cve_service: Any,
    cve_scanner: Any,
    eol_orchestrator: Any,
    state_store: Optional[CVEInventorySyncStateStore] = None,
    limit_per_os: Optional[int] = None,
    force_resync: bool = False,
    os_summary_repo: Optional[Any] = None,
) -> Dict[str, Any]:
    """Warm the CVE cache for newly observed OS identities from inventory.

    Args:
        os_summary_repo: Optional CVESyncOSSummaryRepository for persisting results
    """
    state_store = state_store or CVEInventorySyncStateStore()
    discovered = await discover_inventory_os_identities(
        eol_orchestrator=eol_orchestrator,
        cve_scanner=cve_scanner,
    )
    state = await state_store.load()
    synced_keys = set(state.get("synced_os_keys") or [])

    targets = discovered if force_resync else [item for item in discovered if item["key"] not in synced_keys]
    processed: List[Dict[str, Any]] = []

    # Parallel processing with concurrency limit
    # Without NVD API key: strict limit to avoid rate limiting (0.6 req/s = 1 req per 6s)
    # With NVD API key: can handle more concurrent requests (5 req/s)
    max_concurrent = 3  # Conservative default without API key
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_os_identity(identity: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single OS identity with concurrency control and jitter."""
        async with semaphore:
            # Add random jitter (1.0-4.0 seconds) to spread out requests and avoid rate limiting
            # Higher jitter without API key to respect 0.6 req/s limit (1 req per 6 seconds)
            jitter = random.uniform(1.0, 4.0)
            await asyncio.sleep(jitter)

            live_queries = _build_inventory_live_queries(identity, limit_per_os)

            try:
                deduped_matches: Dict[str, Any] = {}
                for live_query in live_queries:
                    matches = await cve_service.sync_live_cves(
                        query=live_query["query"],
                        limit=live_query["limit"],
                        source=live_query["source"],
                        nvd_filters=live_query["nvd_filters"],
                    )
                    for match in matches:
                        deduped_matches[match.cve_id] = match

                match_count = len(deduped_matches)
                return {
                    **identity,
                    "query_mode": live_queries[0]["mode"] if live_queries else "keyword",
                    "filters": live_queries[0]["filters"] if live_queries else {},
                    "live_queries": [
                        {
                            "mode": query_spec["mode"],
                            "query": query_spec["query"],
                            "source": query_spec["source"],
                            "nvd_filters": query_spec["nvd_filters"],
                        }
                        for query_spec in live_queries
                    ],
                    "match_count": match_count,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                logger.warning("Inventory OS CVE sync failed for %s: %s", identity["key"], exc)
                return {
                    **identity,
                    "query_mode": live_queries[0]["mode"] if live_queries else "keyword",
                    "filters": live_queries[0]["filters"] if live_queries else {},
                    "live_queries": [
                        {
                            "mode": query_spec["mode"],
                            "query": query_spec["query"],
                            "source": query_spec["source"],
                            "nvd_filters": query_spec["nvd_filters"],
                        }
                        for query_spec in live_queries
                    ],
                    "match_count": 0,
                    "error": str(exc),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                }

    # Execute all OS identity syncs in parallel with concurrency limit
    if targets:
        logger.info(f"Starting parallel CVE sync for {len(targets)} OS identities (max {max_concurrent} concurrent, jitter 1.0-4.0s)")
        processed = await asyncio.gather(*[process_os_identity(identity) for identity in targets])

    total_cves = sum(entry.get("match_count", 0) for entry in processed)

    updated_entries: Dict[str, Dict[str, Any]] = {
        entry.get("key"): entry for entry in state.get("os_entries") or [] if entry.get("key")
    }
    for identity in discovered:
        updated_entries.setdefault(identity["key"], identity)
    for entry in processed:
        updated_entries[entry["key"]] = entry

    if processed:
        synced_keys.update(item["key"] for item in processed)
        await state_store.save({
            "synced_os_keys": sorted(synced_keys),
            "os_entries": sorted(updated_entries.values(), key=lambda item: item.get("key", "")),
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        })

        # Persist OS sync summaries to PostgreSQL for dashboard display
        if os_summary_repo:
            try:
                await os_summary_repo.upsert_batch(list(updated_entries.values()))
                logger.info(f"Persisted {len(updated_entries)} OS sync summaries to PostgreSQL")
            except Exception as e:
                logger.warning(f"Failed to persist OS sync summaries: {e}")

    return {
        "discovered_os_count": len(discovered),
        "new_os_count": 0 if force_resync else len(targets),
        "processed_os_count": len(processed),
        "synced_cve_count": total_cves,
        "force_resync": force_resync,
        "os_entries": processed,
        "known_os_count": len(synced_keys),
    }