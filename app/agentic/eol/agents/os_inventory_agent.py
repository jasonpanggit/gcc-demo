"""
Operating System Inventory Agent - Retrieves OS information from Azure Log Analytics Heartbeat table
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

# Import utilities
try:
    from ..utils import get_logger, config
    from ..utils.inventory_cache import inventory_cache
    from ..utils.cache_stats_manager import cache_stats_manager
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    try:
        from utils.cache_stats_manager import cache_stats_manager
    except ImportError:
        # Create dummy stats manager if import fails
        class DummyCacheStatsManager:
            def record_agent_request(self, *args, **kwargs): pass
        cache_stats_manager = DummyCacheStatsManager()

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
import os
from typing import List, Dict, Any, Optional
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.identity import DefaultAzureCredential
from datetime import datetime, timedelta

# Import utilities
try:
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    from utils.cache_stats_manager import cache_stats_manager
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config
    from utils.inventory_cache import inventory_cache
    try:
        from utils.cache_stats_manager import cache_stats_manager
    except ImportError:
        # Create dummy stats manager if import fails
        class DummyCacheStatsManager:
            def record_agent_request(self, *args, **kwargs): pass
        cache_stats_manager = DummyCacheStatsManager()

# Initialize logger
logger = get_logger(__name__)


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

        # Always prioritize managed identity for better security
        self.credential = DefaultAzureCredential()
        self._logs_client: Optional[LogsQueryClient] = None

    async def clear_cache(self) -> Dict[str, Any]:
        """Clear cached OS inventory data"""
        return inventory_cache.clear_cache(
            cache_key=self.agent_name,
            cache_type="os"
        )

    @property
    def logs_client(self) -> Optional[LogsQueryClient]:
        if self._logs_client is None and self.workspace_id:
            try:
                self._logs_client = LogsQueryClient(self.credential)
                logger.info("✅ OS Inventory Agent Log Analytics client initialized")
            except Exception as e:
                logger.error("❌ OS Inventory Agent failed to initialize logs client: %s", e)
        return self._logs_client

    async def get_os_inventory(self, days: int = 90, limit: int = 2000, use_cache: bool = True) -> Dict[str, Any]:
        """Retrieve OS inventory from Heartbeat with caching support.

        Args:
            days: Number of days to look back for data
            limit: Maximum number of results to return
            use_cache: Whether to use cached data if available

        Returns:
            Dict with success status and OS inventory data
        """
        # Prepare query parameters for cache key
        query_params = {
            "days": days,
            "limit": limit
        }
        
        # Try to get cached data first
        if use_cache:
            cache_start_time = datetime.utcnow()
            cache_result = inventory_cache.get_cached_data_with_metadata(
                cache_key=self.agent_name,
                cache_type="os"
            )
            cache_end_time = datetime.utcnow()
            cache_response_time = (cache_end_time - cache_start_time).total_seconds() * 1000  # Convert to ms
            
            if cache_result and cache_result.get('data'):
                cached_data = cache_result['data']
                cached_timestamp = cache_result['timestamp']
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
            ComputerType = case(
                ComputerEnvironment == "Azure", "Azure VM",
                ComputerEnvironment == "Non-Azure", "Arc-enabled Server",
                isnotempty(ResourceId) and ResourceId contains "/virtualMachines/", "Azure VM",
                isnotempty(ResourceId) and ResourceId contains "/machines/", "Arc-enabled Server", 
                "Unknown"
            )
        | project Computer, OSName, VersionString, OSType, Vendor, ComputerEnvironment, ComputerType, ResourceId, LastHeartbeat
        | take {limit}
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
                    resource_id = str(row[7]) if row[7] else ""
                    last_hb = row[8].isoformat() if row[8] else None

                    results.append({
                        "computer_name": computer,
                        "os_name": os_name,
                        "os_version": version,
                        "os_type": os_type,
                        "vendor": vendor,
                        "computer_environment": computer_environment,
                        "computer_type": computer_type,
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
            
            # Cache the results for future use
            if use_cache and results:
                cache_start_time = datetime.utcnow()
                inventory_cache.store_cached_data(
                    cache_key=self.agent_name,
                    data=results,
                    cache_type="os"
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
                "cached_at": datetime.utcnow().isoformat()
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
