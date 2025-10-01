"""
Software Inventory Agent - Retrieves software inventory from Azure Log Analytics ConfigurationData table
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.identity import DefaultAzureCredential

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

class SoftwareInventoryAgent:
    """Agent responsible for retrieving software inventory from ConfigurationData table"""
    
    def __init__(self):
        # Agent identification
        self.agent_name = "software_inventory"
        
        self.workspace_id = getattr(config.azure, 'log_analytics_workspace_id', None)
        self.credential = DefaultAzureCredential()
        self._logs_client: Optional[LogsQueryClient] = None
        
        logger.info(f"✅ SoftwareInventoryAgent initialized with workspace: {self.workspace_id}")

    async def clear_cache(self) -> Dict[str, Any]:
        """Clear cached software inventory data"""
        logger.info(f"🗑️ Attempting to clear cached software inventory data from Cosmos DB")
        # logger.debug(f"Clear cache parameters - type: 'software', agent: '{self.agent_name}'")
        
        try:
            clear_start_time = datetime.utcnow()
            result = inventory_cache.clear_cache(
                cache_key=self.agent_name,
                cache_type="software"
            )
            clear_end_time = datetime.utcnow()
            clear_duration = (clear_end_time - clear_start_time).total_seconds()
            
            logger.info(f"✅ Successfully cleared cached software inventory data from Cosmos DB in {clear_duration:.2f}s")
            # logger.debug(f"Clear cache result: {result}")
            return result
            
        except Exception as clear_err:
            logger.error(f"❌ Failed to clear cached software inventory data from Cosmos DB: {clear_err}")
            # logger.debug(f"Clear cache exception details: {type(clear_err).__name__}: {str(clear_err)}")
            return {
                "success": False,
                "error": f"Cache clear failed: {str(clear_err)}"
            }

    @property
    def logs_client(self) -> Optional[LogsQueryClient]:
        if self._logs_client is None and self.workspace_id:
            try:
                self._logs_client = LogsQueryClient(self.credential)
                logger.info("✅ Software Inventory Agent Log Analytics client initialized")
            except Exception as e:
                logger.error("❌ Software Inventory Agent failed to initialize logs client: %s", e)
        return self._logs_client

    async def get_software_inventory(self, days: int = 90, software_filter: Optional[str] = None, limit: int = 10000, use_cache: bool = True) -> Dict[str, Any]:
        """Retrieve software inventory from ConfigurationData table with caching"""
        
        # Prepare query parameters for cache key
        query_params = {
            "days": days,
            "software_filter": software_filter,
            "limit": limit
        }
        
        # Try to get cached data first
        if use_cache:
            logger.info(f"🔍 Attempting to retrieve cached software inventory data from Cosmos DB")
            # logger.debug(f"Cache query parameters: {query_params}")
            # logger.debug(f"Cache key components - type: 'software', agent: '{self.agent_name}', workspace: '{self.workspace_id or 'unknown'}'")
            
            try:
                cache_start_time = datetime.utcnow()
                cache_result = inventory_cache.get_cached_data_with_metadata(
                    cache_key=self.agent_name,
                    cache_type="software"
                )
                cache_end_time = datetime.utcnow()
                cache_response_time = (cache_end_time - cache_start_time).total_seconds() * 1000  # Convert to ms
                
                if cache_result and cache_result.get('data'):
                    # cache_result contains both data and timestamp
                    cached_data = cache_result['data']
                    cached_timestamp = cache_result['timestamp']
                    cached_count = len(cached_data) if isinstance(cached_data, list) else 0
                    logger.info(f"✅ Successfully retrieved cached software inventory data from Cosmos DB: {cached_count} items (cached at {cached_timestamp})")
                    # logger.debug(f"Cached data type: {type(cached_data).__name__}")
                    # logger.debug(f"Cached data sample: {cached_data[:2] if isinstance(cached_data, list) and len(cached_data) > 0 else 'empty or invalid'}")
                    
                    # Record cache hit statistics
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=cache_response_time,
                        was_cache_hit=True,
                        had_error=False,
                        software_name="inventory_cache",
                        version="unified",
                        url=f"cache://software/{self.agent_name}"
                    )
                    
                    # Wrap cached list in the expected result format
                    return {
                        "success": True,
                        "data": cached_data,
                        "count": cached_count,
                        "query_params": query_params,
                        "cached_at": cached_timestamp,  # Use actual cache timestamp
                        "from_cache": True,
                        "source": "cosmos_cache"
                    }
                else:
                    logger.info(f"❌ No cached software inventory data found in Cosmos DB for the specified parameters")
                    # logger.debug(f"Cache miss - will proceed with LAW query")
                    
                    # Record cache miss statistics
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=cache_response_time,
                        was_cache_hit=False,
                        had_error=False,
                        software_name="inventory_cache",
                        version="unified",
                        url=f"cache://software/{self.agent_name}"
                    )
                    
            except Exception as cache_err:
                logger.error(f"❌ Error retrieving cached software inventory data from Cosmos DB: {cache_err}")
                # logger.debug(f"Cache retrieval exception details: {type(cache_err).__name__}: {str(cache_err)}")
                
                # Record error statistics for cache retrieval
                error_response_time = (datetime.utcnow() - cache_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=error_response_time,
                    was_cache_hit=False,
                    had_error=True,
                    software_name="inventory_cache",
                    version="unified",
                    url=f"cache://software/{self.agent_name}"
                )
                # Continue with LAW query if cache fails
        else:
            logger.info(f"🚫 Cache disabled (use_cache=False) - skipping Cosmos DB cache retrieval")
        
        # If no cache or cache disabled, query LAW
        if not self.logs_client or not self.workspace_id:
            logger.warning("SoftwareInventoryAgent not fully configured (logs_client/workspace_id)")
            return {
                "success": False,
                "error": "Software inventory agent not fully configured",
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False
            }

        # Build KQL query - FIXED VERSION
        query = f"""
        ConfigurationData
        | where TimeGenerated >= ago({days}d)
        | where ConfigDataType == "Software"
        | where isnotempty(SoftwareName)
        | where isnotempty(Computer)
        """
        
        # Add software filter if specified
        if software_filter:
            query += f'| where SoftwareName contains "{software_filter}"\n'

        # Complete the query with proper KQL syntax - return per-computer data for better inventory visibility
        query += f"""
        | extend 
            NormalizedPublisher = case(
                Publisher contains "Microsoft", "Microsoft Corporation",
                Publisher contains "Oracle", "Oracle Corporation",
                isempty(Publisher), "Unknown",
                Publisher
            ),
            ActualSoftwareType = coalesce(SoftwareType, "Application")
        | project SoftwareName, CurrentVersion, NormalizedPublisher, ActualSoftwareType, 
                 TimeGenerated, Computer
        | order by SoftwareName asc, Computer asc
        | take {limit}
        """

        logger.info(f"🔍 Executing software inventory query for {days} days (cache miss - querying LAW)")
        # logger.debug(f"LAW query parameters - workspace: {self.workspace_id}, days: {days}, filter: {software_filter}, limit: {limit}")
        
        try:
            query_start_time = datetime.utcnow()
            response = self.logs_client.query_workspace(
                workspace_id=self.workspace_id,
                query=query,
                timespan=timedelta(days=days)
            )
            query_end_time = datetime.utcnow()
            query_duration = (query_end_time - query_start_time).total_seconds()
            
            logger.info(f"📊 LAW query completed in {query_duration:.2f}s with status: {response.status}")
            
            if response.status != LogsQueryStatus.SUCCESS:
                logger.error(f"❌ LAW query failed with status: {response.status}")
                return {
                    "success": False,
                    "error": f"Query unsuccessful with status: {response.status}",
                    "data": [],
                    "count": 0,
                    "query_params": query_params,
                    "from_cache": False
                }

            # Process results
            # logger.debug(f"LAW response contains {len(response.tables)} table(s)")
            if response.tables:
                pass  # logger.debug(f"First table contains {len(response.tables[0].rows)} rows")
            results = []
            processed_rows = 0
            failed_rows = 0
            
            if response.tables and len(response.tables) > 0:
                table = response.tables[0]
                # logger.debug(f"Processing {len(table.rows)} rows from LAW response")
                
                for row_index, row in enumerate(table.rows):
                    try:
                        # Row mapping for non-aggregated query:
                        # row[0] = SoftwareName, row[1] = CurrentVersion, row[2] = NormalizedPublisher, 
                        # row[3] = ActualSoftwareType, row[4] = TimeGenerated, row[5] = Computer
                        
                        item = {
                            "name": row[0] if row[0] else "Unknown",
                            "version": row[1] if row[1] else "",
                            "publisher": row[2] if row[2] else "Unknown",
                            "software_type": row[3] if row[3] else "Unknown",
                            "install_date": None,  # Not available in ConfigurationData
                            "last_seen": row[4].isoformat() if row[4] else None,
                            "computer_count": 1,  # Each row represents one computer installation
                            "computer": row[5] if row[5] else "Unknown",
                            "source": "log_analytics_configurationdata",
                        }
                        results.append(item)
                        processed_rows += 1
                        
                        # Log every 100th row for progress tracking
                        if (row_index + 1) % 100 == 0:
                            # logger.debug(f"Processed {row_index + 1}/{len(table.rows)} rows from LAW response")
                            pass
                            
                    except Exception as row_err:
                        failed_rows += 1
                        logger.warning(f"Row {row_index} parse error: {row_err}")
                        # logger.debug(f"Failed row data: {row}")
                        continue

            logger.info(f"📦 Retrieved {len(results)} software inventory items from LAW (processed: {processed_rows}, failed: {failed_rows})")
            # logger.debug(f"Processing summary - Total rows: {len(table.rows) if 'table' in locals() else 0}, Success: {processed_rows}, Failed: {failed_rows}")

            # Cache the results
            result_data = {
                "success": True,
                "data": results,
                "count": len(results),
                "query_params": query_params,
                "from_cache": False,
                "cached_at": datetime.utcnow().isoformat()
            }

            if use_cache:
                logger.info(f"💾 Attempting to cache {len(results)} software inventory items to Cosmos DB")
                # logger.debug(f"Cache data size: {len(str(result_data))} characters")
                # logger.debug(f"Cache storage parameters - type: 'software', agent: '{self.agent_name}', workspace: '{self.workspace_id}'")
                
                try:
                    cache_start_time = datetime.utcnow()
                    inventory_cache.store_cached_data(
                        cache_key=self.agent_name,
                        data=results,  # Store the actual results list, not the wrapped result_data
                        cache_type="software"
                    )
                    cache_end_time = datetime.utcnow()
                    cache_duration = (cache_end_time - cache_start_time).total_seconds()
                    cache_response_time = cache_duration * 1000  # Convert to ms
                    
                    logger.info(f"✅ Successfully cached software inventory data to Cosmos DB in {cache_duration:.2f}s")
                    # logger.debug(f"Cached {len(results)} items at timestamp: {cache_start_time.isoformat()}")
                    
                    # Record statistics for LAW query + cache store operation
                    total_response_time = (cache_end_time - query_start_time).total_seconds() * 1000
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=total_response_time,
                        was_cache_hit=False,
                        had_error=False,
                        software_name="log_analytics",
                        version="configurationdata",
                        url=f"law://workspace/{self.workspace_id}/ConfigurationData"
                    )
                    
                except Exception as cache_err:
                    logger.error(f"❌ Failed to cache software inventory data to Cosmos DB: {cache_err}")
                    # logger.debug(f"Cache storage exception details: {type(cache_err).__name__}: {str(cache_err)}")
                    
                    # Record error statistics
                    error_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000
                    cache_stats_manager.record_agent_request(
                        agent_name="software_inventory",
                        response_time_ms=error_response_time,
                        was_cache_hit=False,
                        had_error=True,
                        software_name="log_analytics",
                        version="configurationdata",
                        url=f"law://workspace/{self.workspace_id}/ConfigurationData"
                    )
                    # Continue execution even if caching fails
            else:
                logger.info(f"🚫 Cache disabled (use_cache=False) - skipping Cosmos DB cache storage")
                
                # Record statistics for LAW query without caching
                total_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000
                cache_stats_manager.record_agent_request(
                    agent_name="software_inventory",
                    response_time_ms=total_response_time,
                    was_cache_hit=False,
                    had_error=False,
                    software_name="log_analytics",
                    version="configurationdata",
                    url=f"law://workspace/{self.workspace_id}/ConfigurationData"
                )

            return result_data

        except Exception as e:
            logger.error(f"SoftwareInventoryAgent query failed: {e}")
            
            # Record error statistics for LAW query failure
            error_response_time = (datetime.utcnow() - query_start_time).total_seconds() * 1000 if 'query_start_time' in locals() else 0
            cache_stats_manager.record_agent_request(
                agent_name="software_inventory",
                response_time_ms=error_response_time,
                was_cache_hit=False,
                had_error=True,
                software_name="log_analytics",
                version="configurationdata",
                url=f"law://workspace/{self.workspace_id}/ConfigurationData"
            )
            
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "count": 0,
                "query_params": query_params,
                "from_cache": False
            }

    async def get_software_summary(self, days: int = 90) -> Dict[str, Any]:
        """Get aggregated software inventory summary"""
        inventory_result = await self.get_software_inventory(days=days)
        
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
        total_computers = len(set(comp for item in software_items for comp in item.get("computers", [])))
        
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
