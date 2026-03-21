"""Software Inventory Agent - Retrieves software inventory from Azure Log Analytics."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import math

try:  # Optional dependencies for local/mock testing
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus
except ImportError:  # pragma: no cover - only triggered when Azure SDK is absent
    LogsQueryClient = None  # type: ignore[assignment]

    class _FallbackLogsQueryStatus:
        SUCCESS = "success"

    LogsQueryStatus = _FallbackLogsQueryStatus()  # type: ignore[assignment]

try:
    from azure.identity import DefaultAzureCredential
except ImportError:  # pragma: no cover - support running tests without Azure SDK
    DefaultAzureCredential = None  # type: ignore[assignment]

# Import utilities
try:
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    from utils.cache_stats_manager import cache_stats_manager
    from utils.normalization import normalize_software_name_version
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    from utils.normalization import normalize_software_name_version
    try:
        from utils.cache_stats_manager import cache_stats_manager
    except ImportError:
        # Create dummy stats manager if import fails
        class DummyCacheStatsManager:
            def record_agent_request(self, *args, **kwargs): pass
        cache_stats_manager = DummyCacheStatsManager()

try:
    from utils.pg_client import postgres_client
except ImportError:
    postgres_client = None  # type: ignore[assignment]

# Initialize logger
logger = get_logger(__name__)

# Suppress Azure SDK verbose logging
azure_loggers = [
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.core",
    "azure.monitor",
    "urllib3.connectionpool"
]
for azure_logger_name in azure_loggers:
    azure_logger = logging.getLogger(azure_logger_name)
    azure_logger.setLevel(logging.WARNING)


def _escape_kql_literal(value: str) -> str:
    """Escape characters that can break KQL string literals."""
    return value.replace("\\", "\\\\").replace('"', r'\"')


def _to_string_list(value: Any) -> List[str]:
    """Normalize dynamic arrays returned by Log Analytics."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:  # pragma: no cover - lenient parsing for dynamic types
            return [value]
        return [value]
    return [str(value)]

class SoftwareInventoryAgent:
    """Agent responsible for retrieving software inventory from ConfigurationData table"""
    
    def __init__(self):
        # Agent identification
        self.agent_name = "software_inventory"
        
        self.workspace_id = getattr(config.azure, 'log_analytics_workspace_id', None)

        if DefaultAzureCredential is None:
            self.credential = None
            logger.warning("Azure SDK not available – Software inventory agent will operate in mock mode")
        else:
            from utils.azure_client_manager import get_azure_sdk_manager
            self.credential = get_azure_sdk_manager().get_credential()
        self._logs_client: Optional[LogsQueryClient] = None
        self._full_cache_scopes: Dict[str, bool] = {}
        
        logger.info(f"✅ SoftwareInventoryAgent initialized with workspace: {self.workspace_id}")

    async def _persist_software_inventory_to_postgres(self, results: list) -> None:
        """Persist full software inventory to inventory_software_cache table.

        Uses double-encode pattern: stores json.dumps(results) as JSONB string,
        matching the (data#>>'{}')::jsonb reader pattern used elsewhere.
        Only called on full (non-computer-filtered) fetches.
        """
        if postgres_client is None or not getattr(postgres_client, "pool", None):
            logger.debug("Postgres pool not ready — skipping software inventory persist")
            return
        try:
            data_str = json.dumps(results)
            async with postgres_client.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO inventory_software_cache (cache_key, data, cached_at, ttl_seconds)
                    VALUES ($1, $2::jsonb, NOW(), 3600)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        data      = EXCLUDED.data,
                        cached_at = NOW()
                    """,
                    "software_inventory",
                    data_str,
                )
            logger.debug("Persisted %d software inventory rows to postgres", len(results))
        except Exception as exc:
            logger.warning("Failed to persist software inventory to postgres: %s", exc)

    async def _fetch_eol(self, software_name: str, version: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve EOL data using database cache first, then agent orchestrator with confidence logic."""
        if not software_name:
            return None

        # Use centralized normalization for consistent cache keys
        normalized_name, normalized_version = normalize_software_name_version(software_name, version)
        
        logger.debug(
            f"Software inventory normalized: '{software_name}' v'{version}' -> '{normalized_name}' v'{normalized_version}'"
        )

        try:
            from utils.eol_inventory import eol_inventory
            cached = await eol_inventory.get(normalized_name, normalized_version)
            if cached:
                logger.info(f"✅ Software EOL cache hit for {normalized_name} {normalized_version}")
                return cached
        except Exception as exc:
            logger.debug("EOL cache lookup failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)

        logger.debug("Software EOL cache miss for %s %s, querying orchestrator...", normalized_name, normalized_version)

        try:
            # Lazy import to avoid circular dependencies during app startup
            from main import get_eol_orchestrator

            orchestrator = get_eol_orchestrator()
            eol_result = await orchestrator.get_autonomous_eol_data(
                software_name, version, item_type="software"  # Pass original names; orchestrator handles normalization
            )
            if eol_result and eol_result.get("success"):
                # Orchestrator already saves to cache with normalized keys, no need to duplicate
                return eol_result
        except Exception as exc:
            logger.debug("EOL agent lookup failed for %s %s: %s", software_name, version or "(any)", exc)

        return None

    async def _enrich_with_eol(self, items: List[Dict[str, Any]], skip_enrichment: bool = False) -> None:
        """Populate EOL fields on inventory items using cache-first then agent lookup.
        
        Args:
            items: List of inventory items to enrich
            skip_enrichment: If True, skip EOL enrichment entirely (for fast initial load)
        """
        if not items or skip_enrichment:
            return

        semaphore = asyncio.Semaphore(6)

        def _key(name: Optional[str], version: Optional[str]) -> Optional[str]:
            if not name:
                return None
            return f"{name.strip().lower()}::{(version or '').strip().lower()}"

        unique_pairs: Dict[str, Dict[str, Optional[str]]] = {}
        for item in items:
            name = item.get("name") or item.get("software")
            version = item.get("version")
            key = _key(name, version)
            if key and key not in unique_pairs:
                unique_pairs[key] = {"name": name, "version": version}

        async def _fetch_pair(name: Optional[str], version: Optional[str]):
            async with semaphore:
                return await self._fetch_eol(name, version)

        tasks = {
            key: asyncio.create_task(_fetch_pair(pair["name"], pair["version"]))
            for key, pair in unique_pairs.items()
        }

        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for key, task in tasks.items():
            try:
                results[key] = await task
            except Exception:
                results[key] = None

        for item in items:
            name = item.get("name") or item.get("software")
            version = item.get("version")
            key = _key(name, version)
            eol_data = results.get(key) if key else None
            if not eol_data:
                continue

            payload = eol_data.get("data") if isinstance(eol_data, dict) else None
            payload = payload if isinstance(payload, dict) else {}

            item["eol_date"] = payload.get("eol_date")
            item["support_end_date"] = payload.get("support_end_date") or payload.get("support")
            item["eol_status"] = payload.get("status") or payload.get("support_status")
            item["risk_level"] = payload.get("risk_level")
            item["eol_confidence"] = payload.get("confidence") or eol_data.get("confidence")
            item["eol_source"] = payload.get("source") or payload.get("agent_used") or eol_data.get("agent_used")

            if item.get("eol_date"):
                try:
                    days = math.floor((datetime.fromisoformat(item["eol_date"]) - datetime.utcnow()).total_seconds() / 86400)
                    item["days_until_eol"] = days
                except Exception:
                    item["days_until_eol"] = None

    async def clear_cache(self) -> Dict[str, Any]:
        """Clear cached software inventory data"""
        logger.info(f"🗑️ Attempting to clear cached software inventory data from database")
        # logger.debug(f"Clear cache parameters - type: 'software', agent: '{self.agent_name}'")
        
        try:
            clear_start_time = datetime.utcnow()
            result = inventory_cache.clear_cache(
                cache_key=self.agent_name,
                cache_type="software"
            )
            clear_end_time = datetime.utcnow()
            clear_duration = (clear_end_time - clear_start_time).total_seconds()
            
            logger.info(f"✅ Successfully cleared cached software inventory data from database in {clear_duration:.2f}s")
            # logger.debug(f"Clear cache result: {result}")
            return result
            
        except Exception as clear_err:
            logger.error(f"❌ Failed to clear cached software inventory data from database: {clear_err}")
            # logger.debug(f"Clear cache exception details: {type(clear_err).__name__}: {str(clear_err)}")
            return {
                "success": False,
                "error": f"Cache clear failed: {str(clear_err)}"
            }
        finally:
            self._full_cache_scopes.clear()

    @property
    def logs_client(self) -> Optional[LogsQueryClient]:
        if self._logs_client is None and self.workspace_id and LogsQueryClient is not None and self.credential is not None:
            try:
                self._logs_client = LogsQueryClient(self.credential)
                logger.info("✅ Software Inventory Agent Log Analytics client initialized")
            except Exception as e:
                logger.error("❌ Software Inventory Agent failed to initialize logs client: %s", e)
        return self._logs_client

    async def get_software_inventory(
        self,
        days: int = 90,
        software_filter: Optional[str] = None,
        computer_filter: Optional[str] = None,
        limit: Optional[int] = 10000,
        use_cache: bool = True,
        skip_eol_enrichment: bool = True,
    ) -> Dict[str, Any]:
        """Retrieve software inventory from ConfigurationData table with caching.
        
        Args:
            skip_eol_enrichment: If True, skip EOL data enrichment for faster initial load
        """

        full_dataset_requested = False
        normalized_limit: Optional[int]
        if limit is None:
            normalized_limit = None
            full_dataset_requested = True
        elif isinstance(limit, int):
            if limit > 0:
                normalized_limit = limit
            else:
                normalized_limit = None
                full_dataset_requested = True
        else:
            try:
                parsed_limit = int(str(limit))
                if parsed_limit > 0:
                    normalized_limit = parsed_limit
                else:
                    normalized_limit = None
                    full_dataset_requested = True
            except (TypeError, ValueError):
                normalized_limit = None
                full_dataset_requested = True

        query_params = {
            "days": days,
            "software_filter": software_filter,
            "computer_filter": computer_filter,
            "limit": normalized_limit if not full_dataset_requested else "all",
        }

        cache_key = self.agent_name if not computer_filter else f"{self.agent_name}:{computer_filter.lower()}"
        scope_note = f" for computer '{computer_filter}'" if computer_filter else ""

        cache_scope = cache_key
        cache_has_full = self._full_cache_scopes.get(cache_scope, False)
        cache_allowed = use_cache and (not full_dataset_requested or cache_has_full)

        if cache_allowed:
            logger.debug("🔍 Attempting to retrieve cached software inventory data from database%s", scope_note)
            try:
                cache_start_time = datetime.utcnow()
                cache_result = inventory_cache.get_cached_data_with_metadata(
                    cache_key=cache_key,
                    cache_type="software",
                )
                cache_end_time = datetime.utcnow()
                cache_response_time = (cache_end_time - cache_start_time).total_seconds() * 1000

                if cache_result and cache_result.get("data"):
                    cached_data = cache_result["data"]
                    if isinstance(cached_data, list) and normalized_limit is not None:
                        cached_data = cached_data[:normalized_limit]
                    cached_timestamp = cache_result["timestamp"]
                    cached_full_dataset = False
                    metadata = cache_result.get("metadata") if isinstance(cache_result, dict) else None
                    if isinstance(metadata, dict):
                        cached_full_dataset = bool(metadata.get("full_dataset"))
                    elif normalized_limit is not None and len(cached_data) < normalized_limit:
                        cached_full_dataset = True
                    if cached_full_dataset:
                        self._full_cache_scopes[cache_scope] = True
                    cached_count = len(cached_data) if isinstance(cached_data, list) else 0
                    logger.info(
                        "✅ Successfully retrieved cached software inventory data from database%s: %d items (cached at %s)",
                        scope_note,
                        cached_count,
                        cached_timestamp,
                    )
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=cache_response_time,
                        was_cache_hit=True,
                        had_error=False,
                        software_name="inventory_cache",
                        version="unified",
                        url=f"cache://software/{cache_key}",
                    )
                    return {
                        "success": True,
                        "data": cached_data,
                        "count": cached_count,
                        "query_params": query_params,
                        "cached_at": cached_timestamp,
                        "from_cache": True,
                        "source": "inventory_cache",
                        "target_computer": computer_filter,
                        "limit_applied": normalized_limit,
                        "full_dataset": cached_full_dataset,
                    }

                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=cache_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="inventory_cache",
                    version="unified",
                    url=f"cache://software/{cache_key}",
                )
                logger.info("❌ No cached software inventory data found in database%s", scope_note)
            except Exception as cache_err:  # pragma: no cover - defensive logging
                logger.error(
                    "❌ Error retrieving cached software inventory data from database%s: %s",
                    scope_note,
                    cache_err,
                )
                error_response_time = (datetime.utcnow() - cache_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=error_response_time,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="inventory_cache",
                    version="unified",
                    url=f"cache://software/{cache_key}",
                )
        else:
            logger.info("🚫 Cache retrieval skipped%s (use_cache=%s, full_dataset_requested=%s, cached_full=%s)", scope_note, use_cache, full_dataset_requested, cache_has_full)

        if not self.logs_client or not self.workspace_id:
            logger.warning("SoftwareInventoryAgent not fully configured (logs_client/workspace_id)")
            return {
                "success": False,
                "error": "Software inventory agent not fully configured",
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False,
                "target_computer": computer_filter,
            }

        query = f"""
        ConfigurationData
        | where TimeGenerated >= ago({days}d)
        | where ConfigDataType in ("Software", "WindowsUpdate")
        | where isnotempty(SoftwareName)
        | where isnotempty(Computer)
        """

        limit_clause = f"| take {normalized_limit}" if normalized_limit is not None else ""
        if full_dataset_requested:
            logger.info("📦 Software inventory request for full dataset%s (pagination managed by orchestrator)", scope_note)

        if software_filter:
            software_literal = _escape_kql_literal(software_filter)
            query += f'| where SoftwareName contains "{software_literal}"\n'

        if computer_filter:
            computer_literal = _escape_kql_literal(computer_filter.lower())
            query += f'| where tolower(Computer) == "{computer_literal}"\n'

        query += f"""
        | extend
            NormalizedPublisher = case(
                Publisher contains "Microsoft", "Microsoft Corporation",
                Publisher contains "Oracle", "Oracle Corporation",
                isempty(Publisher), "Unknown",
                Publisher
            ),
            ActualSoftwareType = coalesce(SoftwareType, "Application"),
            KBNumber = iff(ConfigDataType == "WindowsUpdate", extract(@"(KB\d+)", 1, SoftwareName), "")
        | summarize
            LastSeen = max(TimeGenerated),
            Publisher = any(NormalizedPublisher),
            SoftwareType = any(ActualSoftwareType),
            KBNumber = any(KBNumber)
            by Computer, SoftwareName, CurrentVersion
        | project Computer, SoftwareName, CurrentVersion, Publisher, SoftwareType, LastSeen, KBNumber
        | order by SoftwareName asc, Computer asc
        """
        if limit_clause:
            query += f"\n        {limit_clause}"

        logger.info(
            "🔍 Executing software inventory query for %s days%s (cache miss - querying LAW)",
            days,
            scope_note,
        )

        try:
            query_start_time = datetime.utcnow()
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query=query,
                timespan=timedelta(days=days),
            )
            query_end_time = datetime.utcnow()
            query_duration = (query_end_time - query_start_time).total_seconds()

            logger.info("📊 LAW query completed in %.2fs with status: %s", query_duration, response.status)

            if response.status != LogsQueryStatus.SUCCESS:
                logger.error("❌ LAW query failed with status: %s", response.status)
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "data": [],
                    "count": 0,
                    "query_params": query_params,
                    "from_cache": False,
                    "target_computer": computer_filter,
                }

            results: List[Dict[str, Any]] = []
            processed_rows = 0
            failed_rows = 0

            if response.tables and len(response.tables) > 0:
                table = response.tables[0]
                for row_index, row in enumerate(table.rows):
                    try:
                        item = {
                            "computer": row[0] if row[0] else "Unknown",
                            "name": row[1] if row[1] else "Unknown",
                            "version": row[2] if row[2] else "",
                            "publisher": row[3] if row[3] else "Unknown",
                            "software_type": row[4] if row[4] else "Unknown",
                            "install_date": None,
                            "last_seen": row[5].isoformat() if row[5] else None,
                            "kb_number": str(row[6]) if len(row) > 6 and row[6] else "",
                            "computer_count": 1,
                            "source": "log_analytics_configurationdata",
                        }
                        results.append(item)
                        processed_rows += 1
                    except Exception as row_err:  # pragma: no cover - unexpected row shapes
                        failed_rows += 1
                        logger.warning("Row %s parse error: %s", row_index, row_err)

            logger.info(
                "📦 Retrieved %d software inventory items from LAW%s (processed: %d, failed: %d)",
                len(results),
                scope_note,
                processed_rows,
                failed_rows,
            )

            # Enrich with EOL data (cache first, then agents with confidence logic)
            # Skip enrichment if requested for fast initial load
            await self._enrich_with_eol(results, skip_enrichment=skip_eol_enrichment)

            result_data = {
                "success": True,
                "data": results,
                "count": len(results),
                "query_params": query_params,
                "from_cache": False,
                "cached_at": datetime.utcnow().isoformat(),
                "target_computer": computer_filter,
                "limit_applied": normalized_limit,
                "full_dataset": full_dataset_requested,
            }

            if use_cache:
                logger.info(
                    "💾 Attempting to cache %d software inventory items to database%s",
                    len(results),
                    scope_note,
                )
                try:
                    cache_start_time = datetime.utcnow()
                    inventory_cache.store_cached_data(
                        cache_key=cache_key,
                        data=results,
                        cache_type="software",
                        metadata={
                            "full_dataset": full_dataset_requested or (
                                normalized_limit is not None and len(results) < normalized_limit
                            ),
                            "query_params": query_params,
                            "computer_filter": computer_filter,
                        },
                    )
                    cache_end_time = datetime.utcnow()
                    cache_duration = (cache_end_time - cache_start_time).total_seconds()
                    total_response_time = (cache_end_time - query_start_time).total_seconds() * 1000
                    logger.info(
                        "✅ Successfully cached software inventory data to database in %.2fs%s",
                        cache_duration,
                        scope_note,
                    )
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=total_response_time,
                        was_cache_hit=False,
                        had_error=False,
                        software_name="log_analytics",
                        version="configurationdata",
                        url=f"law://workspace/{self.workspace_id}/ConfigurationData",
                    )
                    # Persist to Postgres (fire-and-forget, non-blocking)
                    if not computer_filter:  # only on full inventory runs
                        asyncio.create_task(self._persist_software_inventory_to_postgres(results))
                except Exception as cache_err:  # pragma: no cover - cache failures shouldn't break flow
                    logger.error(
                        "❌ Failed to cache software inventory data to database%s: %s",
                        scope_note,
                        cache_err,
                    )
                    error_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=error_response_time,
                        was_cache_hit=False,
                        had_error=True,
                        software_name="log_analytics",
                        version="configurationdata",
                        url=f"law://workspace/{self.workspace_id}/ConfigurationData",
                    )
            else:
                total_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=total_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="log_analytics",
                    version="configurationdata",
                    url=f"law://workspace/{self.workspace_id}/ConfigurationData",
                )

            retrieved_full_dataset = full_dataset_requested or (
                normalized_limit is not None and len(results) < normalized_limit
            )
            self._full_cache_scopes[cache_scope] = retrieved_full_dataset

            result_data["full_dataset"] = retrieved_full_dataset

            # Trigger KB→CVE edge sync for WindowsUpdate KB numbers (fire-and-forget, non-blocking)
            # Runs unconditionally after a successful LAW query — not contingent on cache success.
            if not computer_filter:
                _kb_numbers = [r.get("kb_number", "") for r in results if r.get("kb_number")]
                if _kb_numbers and postgres_client is not None and getattr(postgres_client, "pool", None):
                    from utils.cve_sync_operations import sync_kb_edges_for_kbs
                    from utils.vendor_feed_client import VendorFeedClient
                    from utils.config import config as _config

                    async def _kb_edge_sync_task(kb_numbers, cve_cfg, pool):
                        vendor = None
                        try:
                            vendor = VendorFeedClient(
                                redhat_base_url=cve_cfg.redhat_base_url,
                                ubuntu_base_url=cve_cfg.ubuntu_base_url,
                                msrc_base_url=cve_cfg.msrc_base_url,
                                msrc_api_key=cve_cfg.msrc_api_key or None,
                                request_timeout=cve_cfg.request_timeout,
                            )
                            await sync_kb_edges_for_kbs(kb_numbers, vendor, pool=pool)
                            logger.info("KB→CVE edge sync complete for %d KB numbers from LAW inventory", len(kb_numbers))
                        except Exception as _exc:
                            logger.warning("KB edge sync from LAW inventory failed: %s", _exc)
                        finally:
                            if vendor is not None:
                                await vendor.close()

                    asyncio.create_task(
                        _kb_edge_sync_task(_kb_numbers, _config.cve_data, postgres_client.pool)
                    )

            return result_data

        except Exception as exc:  # pragma: no cover - broad safety net
            logger.error("SoftwareInventoryAgent query failed%s: %s", scope_note, exc)
            error_response_time = (
                (datetime.utcnow() - query_start_time).total_seconds() * 1000
                if "query_start_time" in locals()
                else 0
            )
            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=error_response_time,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="configurationdata",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData",
            )
            return {
                "success": False,
                "error": str(exc),
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False,
                "target_computer": computer_filter,
            }

    async def get_software_summary(self, days: int = 90, skip_eol_enrichment: bool = True) -> Dict[str, Any]:
        """Get aggregated software inventory summary.
        
        Args:
            days: Number of days to look back
            skip_eol_enrichment: If True, skip EOL data enrichment for faster response
        """
        inventory_result = await self.get_software_inventory(days=days, skip_eol_enrichment=skip_eol_enrichment)
        
        if not inventory_result.get("success"):
            return {
                "success": False,
                "error": inventory_result.get("error", "Failed to get software inventory"),
                "total_software": 0,
                "total_computers": 0,
                "last_updated": datetime.utcnow().isoformat()
            }
        
        software_items = inventory_result.get("data", [])
        total_software = len(software_items)
        total_computers = len({
            item.get("computer") for item in software_items if item.get("computer")
        })
        
        by_category = {}
        by_publisher = {}
        
        for item in software_items:
            category = item.get("software_type", "Other")
            publisher = item.get("publisher", "Unknown")
            
            by_category[category] = by_category.get(category, 0) + item.get("computer_count", 0)
            by_publisher[publisher] = by_publisher.get(publisher, 0) + item.get("computer_count", 0)

        # Top 5 in each category
        top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
        top_publishers = sorted(by_publisher.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "success": True,
            "total_software": total_software,
            "total_computers": total_computers,
            "by_category": dict(by_category),
            "by_publisher": dict(by_publisher),
            "top_categories": [{"category": k, "installations": v} for k, v in top_categories],
            "top_publishers": [{"publisher": k, "installations": v} for k, v in top_publishers],
            "last_updated": datetime.utcnow().isoformat(),
            "from_cache": inventory_result.get("from_cache", False),
            "cached_at": inventory_result.get("cached_at")
        }

    async def health_check(self) -> Dict[str, Any]:
        """Lightweight health check for the Software Inventory agent"""
        status = {
            "configured": bool(self.workspace_id),
            "logs_client": bool(self.logs_client is not None),
            "ok": False,
            "checked_at": datetime.utcnow().isoformat(),
        }
        
        if not self.workspace_id or not self.logs_client:
            return status

        # Attempt trivial query with short timespan
        try:
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query="ConfigurationData | where ConfigDataType == 'Software' | take 1",
                timespan=timedelta(days=1),
            )
            status["ok"] = response.status == LogsQueryStatus.SUCCESS
            
            if status["ok"] and response.tables and response.tables[0].rows:
                status["sample_data_available"] = True
            else:
                status["sample_data_available"] = False
                
        except Exception as e:
            logger.warning("SoftwareInventoryAgent health check failed: %s", e)
            status["ok"] = False
            status["error"] = str(e)
            
        return status

    async def get_software_publisher_summary(self, days: int = 90, top_n: Optional[int] = 25) -> Dict[str, Any]:
        """Summarize software installations by publisher."""
        if not self.logs_client or not self.workspace_id:
            return {
                "success": False,
                "error": "Software inventory agent not fully configured",
                "publisher_summary": [],
            }

        limit_clause = f"| take {int(top_n)}" if top_n else ""
        query = f"""
        ConfigurationData
        | where TimeGenerated >= ago({days}d)
        | where ConfigDataType == "Software"
        | where isnotempty(SoftwareName) and isnotempty(Computer)
        | extend 
            NormalizedPublisher = case(
                isempty(Publisher), "Unknown",
                Publisher contains "Microsoft", "Microsoft Corporation",
                Publisher contains "Oracle", "Oracle Corporation",
                Publisher contains "Adobe", "Adobe Inc.",
                Publisher contains "VMware", "VMware",
                Publisher
            )
        | summarize 
            Installations = dcount(Computer),
            SoftwareCount = dcount(SoftwareName),
            LastSeen = max(TimeGenerated)
          by Publisher = NormalizedPublisher
        | order by Installations desc
        {limit_clause}
        | project Publisher, Installations, SoftwareCount, LastSeen
        """

        try:
            query_start = datetime.utcnow()
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query=query,
                timespan=timedelta(days=days),
            )
            query_duration_ms = (datetime.utcnow() - query_start).total_seconds() * 1000

            if response.status != LogsQueryStatus.SUCCESS or not response.tables:
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=query_duration_ms,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="log_analytics",
                    version="configurationdata_publisher_summary",
                    url=f"law://workspace/{self.workspace_id}/ConfigurationData",
                )
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "publisher_summary": [],
                }

            table = response.tables[0]
            summary: List[Dict[str, Any]] = []
            for row in table.rows:
                publisher = str(row[0]) if row[0] else "Unknown"
                installations = int(row[1]) if row[1] is not None else 0
                software_count = int(row[2]) if row[2] is not None else 0
                last_seen = row[3].isoformat() if row[3] else None
                summary.append(
                    {
                        "publisher": publisher,
                        "installations": installations,
                        "unique_software": software_count,
                        "last_seen": last_seen,
                    }
                )

            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=query_duration_ms,
                was_cache_hit=False,
                had_error=False,
                software_name="log_analytics",
                version="configurationdata_publisher_summary",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData",
            )

            total_installations = sum(item["installations"] for item in summary)
            return {
                "success": True,
                "publisher_summary": summary,
                "total_publishers": len(summary),
                "total_installations": total_installations,
                "requested_days": days,
                "top": top_n,
                "queried_at": datetime.utcnow().isoformat(),
            }

        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error("Software publisher summary query failed: %s", exc)
            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=0,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="configurationdata_publisher_summary",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData",
            )
            return {
                "success": False,
                "error": str(exc),
                "publisher_summary": [],
            }

    async def get_top_software_packages(
        self,
        days: int = 90,
        top_n: Optional[int] = 50,
        include_versions: bool = True,
    ) -> Dict[str, Any]:
        """Return the most common software packages observed across computers."""
        if not self.logs_client or not self.workspace_id:
            return {
                "success": False,
                "error": "Software inventory agent not fully configured",
                "software_packages": [],
            }

        group_clause = "SoftwareName, CurrentVersion" if include_versions else "SoftwareName"
        projection = (
            "| project SoftwareName, CurrentVersion, Installations, SoftwareType, LastSeen, Publishers"
            if include_versions
            else "| project SoftwareName, Installations, SoftwareType, LastSeen, Versions, Publishers"
        )
        limit_clause = f"| take {int(top_n)}" if top_n else ""

        query = f"""
        ConfigurationData
        | where TimeGenerated >= ago({days}d)
        | where ConfigDataType == "Software"
        | where isnotempty(SoftwareName) and isnotempty(Computer)
        | extend 
            NormalizedPublisher = case(
                isempty(Publisher), "Unknown",
                Publisher contains "Microsoft", "Microsoft Corporation",
                Publisher contains "Oracle", "Oracle Corporation",
                Publisher contains "Adobe", "Adobe Inc.",
                Publisher contains "VMware", "VMware",
                Publisher
            ),
            ActualSoftwareType = coalesce(SoftwareType, "Application")
        | summarize 
            Installations = dcount(Computer),
            LastSeen = max(TimeGenerated),
            Publishers = make_set(NormalizedPublisher, 5),
            Versions = make_set(CurrentVersion, 5),
            SoftwareType = any(ActualSoftwareType)
          by {group_clause}
        | order by Installations desc
        {limit_clause}
        {projection}
        """

        try:
            query_start = datetime.utcnow()
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query=query,
                timespan=timedelta(days=days),
            )
            query_duration_ms = (datetime.utcnow() - query_start).total_seconds() * 1000

            if response.status != LogsQueryStatus.SUCCESS or not response.tables:
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=query_duration_ms,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="log_analytics",
                    version="configurationdata_top_software",
                    url=f"law://workspace/{self.workspace_id}/ConfigurationData",
                )
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "software_packages": [],
                }

            table = response.tables[0]
            packages: List[Dict[str, Any]] = []
            for row in table.rows:
                idx = 0
                name = str(row[idx]) if row[idx] else "Unknown"
                idx += 1
                version_value = None
                if include_versions:
                    version_value = str(row[idx]) if row[idx] else ""
                    idx += 1
                installations = int(row[idx]) if row[idx] is not None else 0
                idx += 1
                software_type = str(row[idx]) if row[idx] else "Unknown"
                idx += 1
                last_seen = row[idx].isoformat() if row[idx] else None
                idx += 1
                if include_versions:
                    publishers_raw = row[idx]
                    idx += 1
                    publishers = _to_string_list(publishers_raw)
                    package = {
                        "software_name": name,
                        "version": version_value,
                        "installations": installations,
                        "software_type": software_type,
                        "last_seen": last_seen,
                        "publishers": publishers,
                    }
                else:
                    versions_raw = row[idx]
                    idx += 1
                    publishers_raw = row[idx]
                    idx += 1
                    versions = _to_string_list(versions_raw)
                    publishers = _to_string_list(publishers_raw)
                    package = {
                        "software_name": name,
                        "versions": versions,
                        "installations": installations,
                        "software_type": software_type,
                        "last_seen": last_seen,
                        "publishers": publishers,
                    }
                packages.append(package)

            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=query_duration_ms,
                was_cache_hit=False,
                had_error=False,
                software_name="log_analytics",
                version="configurationdata_top_software",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData",
            )

            total_installations = sum(item["installations"] for item in packages)
            return {
                "success": True,
                "software_packages": packages,
                "total_packages": len(packages),
                "total_installations": total_installations,
                "requested_days": days,
                "top": top_n,
                "include_versions": include_versions,
                "queried_at": datetime.utcnow().isoformat(),
            }

        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error("Top software packages query failed: %s", exc)
            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=0,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="configurationdata_top_software",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData",
            )
            return {
                "success": False,
                "error": str(exc),
                "software_packages": [],
            }
