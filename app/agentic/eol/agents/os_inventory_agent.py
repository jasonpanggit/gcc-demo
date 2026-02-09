"""Operating System Inventory Agent - Retrieves OS information from Azure Log Analytics."""

import asyncio
import json
import logging
import os
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:  # Optional Azure dependencies – absent when running unit tests with mock data
    from azure.identity import DefaultAzureCredential
except ImportError:  # pragma: no cover - exercised only in local testing environments without Azure SDK
    DefaultAzureCredential = None  # type: ignore[assignment]

try:
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus
except ImportError:  # pragma: no cover - avoid hard dependency during local testing
    LogsQueryClient = None  # type: ignore[assignment]

    class _FallbackLogsQueryStatus:
        SUCCESS = "success"

    LogsQueryStatus = _FallbackLogsQueryStatus()  # type: ignore[assignment]

try:
    from ..utils import get_logger, config
    from ..utils.inventory_cache import inventory_cache
    from ..utils.cache_stats_manager import cache_stats_manager
    from ..utils.normalization import normalize_os_name_version
except ImportError:  # pragma: no cover - support execution when run as script
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    from utils.normalization import normalize_os_name_version

    try:
        from utils.cache_stats_manager import cache_stats_manager
    except ImportError:  # pragma: no cover - last-resort fallback for tooling
        class _DummyCacheStatsManager:
            def record_agent_request(self, *args, **kwargs):  # noqa: D401 - simple stub
                """No-op fallback when cache stats manager is unavailable."""

        cache_stats_manager = _DummyCacheStatsManager()


logger = get_logger(__name__)

for azure_logger_name in (
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.core",
    "azure.monitor",
    "urllib3.connectionpool",
):
    logging.getLogger(azure_logger_name).setLevel(logging.WARNING)


class OSInventoryAgent:
    """Agent responsible for retrieving OS inventory (name, version, type) from Heartbeat"""

    def __init__(self):
        # Agent identification
        self.agent_name = "os_inventory"
        
        # Environment variable aligns with ConfigManager and Terraform app settings
        self.workspace_id = os.getenv("LOG_ANALYTICS_WORKSPACE_ID")
        logger.info(
            "🖥️ OS Inventory Agent initialized for workspace: %s",
            self.workspace_id[:8] + "..." if self.workspace_id else "NOT_SET",
        )

        # Always prioritize managed identity for better security when SDK is available
        if DefaultAzureCredential is None:
            self.credential = None
            logger.warning("Azure SDK not available – OS inventory agent will operate in mock mode")
        else:
            self.credential = DefaultAzureCredential()

        self._logs_client: Optional[LogsQueryClient] = None
        self._cache_has_full_dataset: bool = False

    async def _fetch_eol(self, os_name: str, version: Optional[str], skip_enrichment: bool = False) -> Optional[Dict[str, Any]]:
        """Resolve EOL for OS using Cosmos cache first, then agent orchestrator with confidence logic.
        
        Args:
            os_name: Operating system name
            version: OS version
            skip_enrichment: If True, return None immediately (for fast initial load)
        """
        if skip_enrichment:
            return None
        if not os_name:
            return None

        # Use centralized normalization for consistent cache keys
        normalized_name, normalized_version = normalize_os_name_version(os_name, version)
        
        logger.debug(
            f"Normalized OS: '{os_name}' v'{version}' -> '{normalized_name}' v'{normalized_version}'"
        )

        logger.debug(f"Looking up EOL cache for: {normalized_name} v{normalized_version}")

        try:
            from ..utils.eol_inventory import eol_inventory
            cached = await eol_inventory.get(normalized_name, normalized_version)
            if cached:
                cached_data = cached.get("data") if isinstance(cached, dict) else None
                if isinstance(cached_data, dict) and (
                    cached_data.get("eol_date")
                    or cached_data.get("support_end_date")
                    or cached_data.get("support")
                ):
                    logger.info(f"✅ EOL cache hit for {normalized_name} {normalized_version}")
                    return cached
                else:
                    logger.debug(f"Cache entry found but no EOL dates for {normalized_name} {normalized_version}")
        except Exception as exc:
            logger.debug("OS EOL cache lookup failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)

        logger.info(f"🔍 EOL cache miss for {normalized_name} {normalized_version}, querying orchestrator...")

        try:
            from ..main import get_eol_orchestrator

            orchestrator = get_eol_orchestrator()
            eol_result = await orchestrator.get_autonomous_eol_data(
                normalized_name, normalized_version, item_type="os"
            )
            if eol_result and eol_result.get("success"):
                data_block = eol_result.get("data") if isinstance(eol_result, dict) else None
                has_dates = isinstance(data_block, dict) and (
                    data_block.get("eol_date")
                    or data_block.get("support_end_date")
                    or data_block.get("support")
                )
                if has_dates:
                    try:
                        from ..utils.eol_inventory import eol_inventory
                        await eol_inventory.upsert(normalized_name, normalized_version, eol_result)
                    except Exception as exc:
                        logger.debug("OS EOL cache upsert failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)
                    return eol_result
        except Exception as exc:
            logger.debug("OS EOL agent lookup failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)

        if "windows server" in os_lower:
            try:
                from .microsoft_agent import MicrosoftEOLAgent

                ms_agent = MicrosoftEOLAgent()
                ms_result = await ms_agent.get_eol_data(normalized_name, normalized_version)
                if ms_result and ms_result.get("success"):
                    return ms_result
            except Exception as exc:
                logger.debug("OS EOL Microsoft fallback failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)

            try:
                from .microsoft_agent import MicrosoftEOLAgent

                ms_agent = MicrosoftEOLAgent()
                static_result = ms_agent._check_static_data(normalized_name, normalized_version)
                if static_result:
                    confidence = static_result.get("confidence", 90)
                    if confidence and confidence > 1:
                        confidence = confidence / 100.0
                    return ms_agent.create_success_response(
                        software_name=normalized_name,
                        version=normalized_version or static_result.get("cycle"),
                        eol_date=static_result.get("eol"),
                        support_end_date=static_result.get("support"),
                        release_date=static_result.get("releaseDate"),
                        confidence=confidence or 0.9,
                        source_url=ms_agent._get_scraping_url(normalized_name),
                        additional_data={
                            "cycle": static_result.get("cycle"),
                            "extendedSupport": static_result.get("extendedSupport"),
                            "source": static_result.get("source"),
                        },
                    )
            except Exception as exc:
                logger.debug("OS EOL Microsoft static fallback failed for %s %s: %s", normalized_name, normalized_version or "(any)", exc)

        return None

    async def _enrich_with_eol(self, items: List[Dict[str, Any]]) -> None:
        """Populate EOL fields for OS inventory entries."""
        if not items:
            return

        semaphore = asyncio.Semaphore(6)

        def _key(name: Optional[str], version: Optional[str]) -> Optional[str]:
            if not name:
                return None
            return f"{name.strip().lower()}::{(version or '').strip().lower()}"

        unique_pairs: Dict[str, Dict[str, Optional[str]]] = {}
        for item in items:
            name = item.get("os_name") or item.get("name")
            version = item.get("os_version") or item.get("version")
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
            name = item.get("os_name") or item.get("name")
            version = item.get("os_version") or item.get("version")
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
        """Clear cached OS inventory data"""
        cleared = inventory_cache.clear_cache(
            cache_key=self.agent_name,
            cache_type="os"
        )
        self._cache_has_full_dataset = False
        return cleared

    @property
    def logs_client(self) -> Optional[LogsQueryClient]:
        if self._logs_client is None and self.workspace_id and LogsQueryClient is not None and self.credential is not None:
            try:
                self._logs_client = LogsQueryClient(self.credential)
                logger.info("✅ OS Inventory Agent Log Analytics client initialized")
            except Exception as e:
                logger.error("❌ OS Inventory Agent failed to initialize logs client: %s", e)
        return self._logs_client

    async def get_os_inventory(self, days: int = 90, limit: Optional[int] = 2000, use_cache: bool = True) -> Dict[str, Any]:
        """Retrieve OS inventory from Heartbeat with caching support.

        Args:
            days: Number of days to look back for data
            limit: Maximum number of results to return
            use_cache: Whether to use cached data if available

        Returns:
            Dict with success status and OS inventory data
        """
        # Prepare query parameters for cache key
        # Normalize limit handling so the orchestrator can request the full dataset (limit=None)
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
            "limit": normalized_limit if not full_dataset_requested else "all"
        }
        
        # Try to get cached data first
        cache_allowed = use_cache and (not full_dataset_requested or self._cache_has_full_dataset)
        cache_result = None

        if cache_allowed:
            cache_start_time = datetime.utcnow()
            cache_result = inventory_cache.get_cached_data_with_metadata(
                cache_key=self.agent_name,
                cache_type="os"
            )
            cache_end_time = datetime.utcnow()
            cache_response_time = (cache_end_time - cache_start_time).total_seconds() * 1000  # Convert to ms
            
            if cache_result and cache_result.get('data'):
                cached_data = cache_result['data']
                if isinstance(cached_data, list) and normalized_limit is not None:
                    cached_data = cached_data[:normalized_limit]
                cached_timestamp = cache_result['timestamp']
                cached_full_dataset = False
                metadata = cache_result.get("metadata") if isinstance(cache_result, dict) else None
                if isinstance(metadata, dict):
                    cached_full_dataset = bool(metadata.get("full_dataset"))
                elif normalized_limit is not None and len(cached_data) < normalized_limit:
                    cached_full_dataset = True
                if cached_full_dataset:
                    self._cache_has_full_dataset = True
                logger.info(f"🖥️ Using cached OS inventory data: {len(cached_data)} items (cached at {cached_timestamp})")
                
                # Record cache hit statistics
                cache_stats_manager.record_agent_request(
                    agent_name="os_inventory",
                    response_time_ms=cache_response_time,
                    was_cache_hit=True,
                    had_error=False,
                    software_name="inventory_cache",
                    version="unified",
                    url=f"cache://os/{self.agent_name}"
                )
                
                return {
                    "success": True,
                    "data": cached_data,
                    "count": len(cached_data),
                    "query_params": query_params,
                    "cached_at": cached_timestamp,  # Use actual cache timestamp
                    "from_cache": True,
                    "full_dataset": cached_full_dataset,
                    "source": "cosmos_cache"
                }
            else:
                # Record cache miss statistics
                cache_stats_manager.record_agent_request(
                    agent_name="os_inventory",
                    response_time_ms=cache_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="inventory_cache",
                    version="unified",
                    url=f"cache://os/{self.agent_name}"
                )
        
        # If no cache or cache disabled, query LAW
        if not self.logs_client or not self.workspace_id:
            logger.warning("OSInventoryAgent not fully configured (logs_client/workspace_id)")
            return {
                "success": False,
                "error": "OS inventory agent not fully configured",
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False
            }

        limit_clause = f"| take {normalized_limit}" if normalized_limit is not None else ""
        if full_dataset_requested:
            logger.info("🖥️ OS inventory request for full dataset (pagination handled upstream)")

        query = f"""
        Heartbeat
        | where TimeGenerated >= ago({days}d)
        | where isnotempty(OSName)
        | where isnotempty(Computer)
        | summarize 
            OSName = any(OSName),
            OSVersion = any(OSMajorVersion),
            OSMinorVersion = any(OSMinorVersion),
            OSType = any(OSType),
            ComputerEnvironment = any(ComputerEnvironment),
            ResourceId = any(ResourceId),
            LastHeartbeat = max(TimeGenerated)
          by Computer
        | extend 
            VersionString = case(isnotempty(OSVersion), strcat(OSVersion, ".", OSMinorVersion), "Unknown"),
            Vendor = case(
                OSName contains "Windows", "Microsoft Corporation",
                OSName contains "Ubuntu", "Canonical Ltd.",
                OSName contains "Red Hat", "Red Hat Inc.",
                OSName contains "CentOS", "CentOS Project",
                OSName contains "SUSE", "SUSE",
                OSName contains "Debian", "Debian Project",
                OSName contains "Linux", "Various",
                "Unknown"
            ),
            ResourceGroup = tostring(extract(@"/resourceGroups/([^/]+)", 1, ResourceId)),
            ComputerType = case(
                // Primary detection: ComputerEnvironment field
                ComputerEnvironment =~ "Azure", "Azure VM",
                ComputerEnvironment =~ "Non-Azure", "Arc-enabled Server",
                ComputerEnvironment =~ "NonAzure", "Arc-enabled Server",
                // Secondary detection: ResourceId patterns
                isnotempty(ResourceId) and ResourceId contains "/virtualMachines/", "Azure VM",
                isnotempty(ResourceId) and ResourceId contains "/machines/", "Arc-enabled Server",
                // Tertiary: Any Azure resource (starts with / indicates Azure ARM resource)
                isnotempty(ResourceId) and ResourceId startswith "/", "Azure Resource",
                // Default for unknown
                "On-Premises"
            )
        | project Computer, OSName, VersionString, OSType, Vendor, ComputerEnvironment, ComputerType, ResourceGroup, ResourceId, LastHeartbeat
        {limit_clause}
        """

        try:
            query_start_time = datetime.utcnow()
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query=query,
                timespan=timedelta(days=days),
            )

            if response.status != LogsQueryStatus.SUCCESS or not response.tables:
                logger.warning("OSInventoryAgent query unsuccessful or returned no tables (status=%s)", response.status)
                return []

            table = response.tables[0]
            results: List[Dict[str, Any]] = []
            for row in table.rows:
                try:
                    computer = str(row[0]) if row[0] else "Unknown"
                    os_name = str(row[1]) if row[1] else "Unknown"
                    version = str(row[2]) if row[2] else "Unknown"
                    os_type = str(row[3]) if row[3] else "Unknown"
                    vendor = str(row[4]) if row[4] else "Unknown"
                    computer_environment = str(row[5]) if row[5] else "Unknown"
                    computer_type = str(row[6]) if row[6] else "Unknown"
                    resource_group = str(row[7]) if row[7] else ""
                    resource_id = str(row[8]) if row[8] else ""
                    last_hb = row[9].isoformat() if row[9] else None
                    
                    # Debug logging to diagnose computer_type detection
                    if computer_type == "?":
                        logger.warning(
                            f"❓ Computer type detection failed for {computer}: "
                            f"ComputerEnvironment='{computer_environment}', "
                            f"ResourceId='{resource_id}'"
                        )

                    results.append({
                        "computer_name": computer,
                        "os_name": os_name,
                        "os_version": version,
                        "os_type": os_type,
                        "vendor": vendor,
                        "computer_environment": computer_environment,
                        "computer_type": computer_type,
                        "resource_group": resource_group,
                        "resource_id": resource_id,
                        "last_heartbeat": last_hb,
                        "source": "log_analytics_heartbeat",
                        # backward-compatibility fields if UI consumes in a generic way
                        "computer": computer,
                        "name": os_name,
                        "version": version,
                        "software_type": "operating system",
                    })
                except Exception as row_err:
                    logger.warning("OSInventoryAgent row parse error: %s", row_err)
                    continue

            logger.info(f"🖥️ Retrieved {len(results)} OS inventory items from LAW")

            # Enrich with EOL data (Cosmos first, then agents with confidence logic)
            await self._enrich_with_eol(results)

            # Ensure Windows Server entries receive EOL data from static Microsoft mappings when missing
            try:
                from .microsoft_agent import MicrosoftEOLAgent

                ms_agent = MicrosoftEOLAgent()
                for item in results:
                    if item.get("eol_date"):
                        continue
                    os_name = (item.get("os_name") or item.get("name") or "").lower()
                    if "windows server" not in os_name:
                        continue
                    version_text = f"{item.get('os_name') or ''} {item.get('os_version') or ''}"
                    match = re.search(r"(20\d{2}|19\d{2})", version_text)
                    if not match:
                        continue
                    static_result = ms_agent._check_static_data("windows server", match.group(1))
                    if not static_result:
                        continue
                    item["eol_date"] = static_result.get("eol")
                    item["support_end_date"] = static_result.get("support")
                    item["eol_source"] = static_result.get("source") or "microsoft_official"
                    item["eol_confidence"] = static_result.get("confidence")
                    if item.get("eol_date"):
                        try:
                            days = math.floor((datetime.fromisoformat(item["eol_date"]) - datetime.utcnow()).total_seconds() / 86400)
                            item["days_until_eol"] = days
                        except Exception:
                            item["days_until_eol"] = None
            except Exception as exc:
                logger.debug("Windows Server static EOL enrichment failed: %s", exc)

            # Track whether the returned data represents the full dataset so pagination can surface all records
            retrieved_full_dataset = full_dataset_requested or (
                normalized_limit is not None and len(results) < normalized_limit
            )
            if retrieved_full_dataset:
                self._cache_has_full_dataset = True
            elif not full_dataset_requested:
                self._cache_has_full_dataset = False
            
            # Cache the results for future use
            if use_cache and results:
                cache_start_time = datetime.utcnow()
                inventory_cache.store_cached_data(
                    cache_key=self.agent_name,
                    data=results,
                    cache_type="os",
                    metadata={
                        "full_dataset": retrieved_full_dataset,
                        "query_params": query_params
                    }
                )
                cache_end_time = datetime.utcnow()
                
                # Record statistics for LAW query + cache store operation
                total_response_time = (cache_end_time - query_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="os_inventory",
                    response_time_ms=total_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="log_analytics",
                    version="heartbeat",
                    url=f"law://workspace/{self.workspace_id}/Heartbeat"
                )
            else:
                # Record statistics for LAW query without caching
                total_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="os_inventory",
                    response_time_ms=total_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="log_analytics",
                    version="heartbeat",
                    url=f"law://workspace/{self.workspace_id}/Heartbeat"
                )
            
            return {
                "success": True,
                "data": results,
                "count": len(results),
                "query_params": query_params,
                "from_cache": False,
                "cached_at": datetime.utcnow().isoformat(),
                "limit_applied": normalized_limit,
                "full_dataset": retrieved_full_dataset,
            }
            
        except Exception as e:
            logger.error("OSInventoryAgent query failed: %s", e)
            
            # Record error statistics for LAW query failure
            error_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000 if 'query_start_time' in locals() else 0
            cache_stats_manager.record_agent_request(
                agent_name="os_inventory",
                response_time_ms=error_response_time,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="heartbeat",
                url=f"law://workspace/{self.workspace_id}/Heartbeat"
            )
            
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False
            }

    async def get_os_summary(self, days: int = 90) -> Dict[str, Any]:
        """Summarize OS inventory by OS name and type."""
        inventory_result = await self.get_os_inventory(days=days)
        if not inventory_result.get("success", False):
            return {
                "error": inventory_result.get("error", "Failed to get OS inventory"),
                "total_computers": 0,
                "windows_count": 0,
                "linux_count": 0,
                "by_name": {},
                "top_versions": [],
                "last_updated": datetime.utcnow().isoformat(),
            }
        
        inventory = inventory_result.get("data", [])
        total = len(inventory)
        by_name: Dict[str, int] = {}
        by_version: Dict[str, int] = {}
        windows = 0
        linux = 0

        for item in inventory:
            name = item.get("os_name", "Unknown")
            ver = item.get("os_version", "Unknown")
            otype = item.get("os_type", "Unknown").lower()
            by_name[name] = by_name.get(name, 0) + 1
            by_version[f"{name} {ver}"] = by_version.get(f"{name} {ver}", 0) + 1
            if "windows" in name.lower() or "windows" in otype:
                windows += 1
            elif "linux" in name.lower() or "linux" in otype:
                linux += 1

        # Top 5 versions
        top_versions = sorted(by_version.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_versions = [{"name_version": k, "count": v} for k, v in top_versions]

        return {
            "total_computers": total,
            "windows_count": windows,
            "linux_count": linux,
            "by_name": by_name,
            "top_versions": top_versions,
            "last_updated": datetime.utcnow().isoformat(),
            "from_cache": inventory_result.get("from_cache", False),
            "cached_at": inventory_result.get("cached_at", None),
        }

    async def get_os_environment_breakdown(self, days: int = 90, top_n: Optional[int] = None) -> Dict[str, Any]:
        """Summarize OS inventory by environment and computed device classification."""
        if not self.logs_client or not self.workspace_id:
            return {
                "success": False,
                "error": "OS inventory agent not fully configured",
                "environment_breakdown": [],
            }

        limit_clause = f"| take {int(top_n)}" if top_n else ""
        query = f"""
        Heartbeat
        | where TimeGenerated >= ago({days}d)
        | where isnotempty(OSName) and isnotempty(Computer)
        | extend 
            ComputerEnvironmentNormalized = case(
                isempty(ComputerEnvironment), "Unknown",
                ComputerEnvironment =~ "NonAzure", "Non-Azure",
                tolower(ComputerEnvironment) == "nonazure", "Non-Azure",
                ComputerEnvironment
            ),
            ResourceIdText = tostring(ResourceId),
            ComputerType = case(
                ComputerEnvironmentNormalized =~ "Azure", "Azure VM",
                ComputerEnvironmentNormalized =~ "Non-Azure", "Arc-enabled Server",
                isnotempty(ResourceIdText) and ResourceIdText contains "/virtualMachines/", "Azure VM",
                isnotempty(ResourceIdText) and ResourceIdText contains "/machines/", "Arc-enabled Server",
                isnotempty(ResourceIdText) and ResourceIdText startswith "/", "Azure Resource",
                "On-Premises"
            )
        | summarize 
            DeviceCount = dcount(Computer),
            LastHeartbeat = max(TimeGenerated)
          by ComputerEnvironmentNormalized, ComputerType
        | order by DeviceCount desc
        {limit_clause}
        | project ComputerEnvironment = ComputerEnvironmentNormalized, ComputerType, DeviceCount, LastHeartbeat
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
                    agent_name="os_inventory",
                    response_time_ms=query_duration_ms,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="log_analytics",
                    version="heartbeat_environment_breakdown",
                    url=f"law://workspace/{self.workspace_id}/Heartbeat",
                )
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "environment_breakdown": [],
                }

            table = response.tables[0]
            results: List[Dict[str, Any]] = []
            for row in table.rows:
                environment = str(row[0]) if row[0] else "Unknown"
                computer_type = str(row[1]) if row[1] else "Unknown"
                device_count = int(row[2]) if row[2] is not None else 0
                last_heartbeat = row[3].isoformat() if row[3] else None
                results.append(
                    {
                        "computer_environment": environment,
                        "computer_type": computer_type,
                        "device_count": device_count,
                        "last_heartbeat": last_heartbeat,
                    }
                )

            cache_stats_manager.record_agent_request(
                agent_name="os_inventory",
                response_time_ms=query_duration_ms,
                was_cache_hit=False,
                had_error=False,
                software_name="log_analytics",
                version="heartbeat_environment_breakdown",
                url=f"law://workspace/{self.workspace_id}/Heartbeat",
            )

            total_devices = sum(item["device_count"] for item in results)
            return {
                "success": True,
                "environment_breakdown": results,
                "total_segments": len(results),
                "total_devices": total_devices,
                "queried_at": datetime.utcnow().isoformat(),
                "requested_days": days,
                "top": top_n,
            }

        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error("OS environment breakdown query failed: %s", exc)
            cache_stats_manager.record_agent_request(
                agent_name="os_inventory",
                response_time_ms=0,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="heartbeat_environment_breakdown",
                url=f"law://workspace/{self.workspace_id}/Heartbeat",
            )
            return {
                "success": False,
                "error": str(exc),
                "environment_breakdown": [],
            }

    async def get_os_vendor_summary(self, days: int = 90, top_n: Optional[int] = None) -> Dict[str, Any]:
        """Summarize OS inventory by detected vendor and OS type."""
        if not self.logs_client or not self.workspace_id:
            return {
                "success": False,
                "error": "OS inventory agent not fully configured",
                "vendor_summary": [],
            }

        limit_clause = f"| take {int(top_n)}" if top_n else ""
        query = f"""
        Heartbeat
        | where TimeGenerated >= ago({days}d)
        | where isnotempty(OSName) and isnotempty(Computer)
        | extend 
            Vendor = case(
                OSName contains "Windows", "Microsoft Corporation",
                OSName contains "Ubuntu", "Canonical Ltd.",
                OSName contains "Red Hat", "Red Hat Inc.",
                OSName contains "CentOS", "CentOS Project",
                OSName contains "SUSE", "SUSE",
                OSName contains "Debian", "Debian Project",
                OSName contains "Linux", "Various",
                "Unknown"
            ),
            NormalizedOSType = coalesce(OSType, "Unknown")
        | summarize 
            DeviceCount = dcount(Computer),
            LastHeartbeat = max(TimeGenerated),
            SampleOS = any(OSName)
          by Vendor, NormalizedOSType
        | order by DeviceCount desc
        {limit_clause}
        | project Vendor, os_type = NormalizedOSType, DeviceCount, LastHeartbeat, SampleOS
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
                    agent_name="os_inventory",
                    response_time_ms=query_duration_ms,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="log_analytics",
                    version="heartbeat_vendor_summary",
                    url=f"law://workspace/{self.workspace_id}/Heartbeat",
                )
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "vendor_summary": [],
                }

            table = response.tables[0]
            results: List[Dict[str, Any]] = []
            for row in table.rows:
                vendor = str(row[0]) if row[0] else "Unknown"
                os_type = str(row[1]) if row[1] else "Unknown"
                device_count = int(row[2]) if row[2] is not None else 0
                last_heartbeat = row[3].isoformat() if row[3] else None
                sample_os = str(row[4]) if row[4] else None
                results.append(
                    {
                        "vendor": vendor,
                        "os_type": os_type,
                        "device_count": device_count,
                        "last_heartbeat": last_heartbeat,
                        "sample_os": sample_os,
                    }
                )

            cache_stats_manager.record_agent_request(
                agent_name="os_inventory",
                response_time_ms=query_duration_ms,
                was_cache_hit=False,
                had_error=False,
                software_name="log_analytics",
                version="heartbeat_vendor_summary",
                url=f"law://workspace/{self.workspace_id}/Heartbeat",
            )

            total_devices = sum(item["device_count"] for item in results)
            return {
                "success": True,
                "vendor_summary": results,
                "total_entries": len(results),
                "total_devices": total_devices,
                "queried_at": datetime.utcnow().isoformat(),
                "requested_days": days,
                "top": top_n,
            }

        except Exception as exc:  # pragma: no cover - defensive catch
            logger.error("OS vendor summary query failed: %s", exc)
            cache_stats_manager.record_agent_request(
                agent_name="os_inventory",
                response_time_ms=0,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="heartbeat_vendor_summary",
                url=f"law://workspace/{self.workspace_id}/Heartbeat",
            )
            return {
                "success": False,
                "error": str(exc),
                "vendor_summary": [],
            }

    async def health_check(self) -> Dict[str, Any]:
        """Lightweight health check for the OS Inventory agent."""
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
                query="Heartbeat | take 1",
                timespan=timedelta(days=1),
            )
            status["ok"] = response.status == LogsQueryStatus.SUCCESS
        except Exception as e:
            logger.warning("OSInventoryAgent health check failed: %s", e)
            status["ok"] = False
            status["error"] = str(e)
        return status
