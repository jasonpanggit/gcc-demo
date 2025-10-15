"""
Simplified Inventory Agent - Provides summary and status aggregation only
Frontend (inventory.html) now handles all data transformation and aggregation
"""

import time
from typing import Dict, Any
from datetime import datetime
import asyncio

from .os_inventory_agent import OSInventoryAgent
from .software_inventory_agent import SoftwareInventoryAgent

# Import utilities - handle both relative and absolute imports
try:
    from utils import get_logger, config
    from utils.cache_stats_manager import cache_stats_manager
except ImportError:
    # Fallback for testing or different import contexts
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from utils import get_logger, config
    try:
        from utils.cache_stats_manager import cache_stats_manager
    except ImportError:
        # Create dummy manager if not available
        class DummyCacheStatsManager:
            def record_agent_request(self, *args, **kwargs): pass
        cache_stats_manager = DummyCacheStatsManager()

# Initialize logger
logger = get_logger(__name__)


class InventoryAgent:
    """
    Inventory Agent - provides only summary/status aggregation
    
    This agent now serves a minimal coordination role:
    - Aggregating summary statistics from OS and software inventory specialized agents
    - Providing status information for monitoring endpoints
    
    All data transformation and aggregation is now handled by the frontend.
    """

    def __init__(self):
        # Initialize specialized inventory agents for summary data
        
        self.os_inventory_agent = OSInventoryAgent()
        self.software_inventory_agent = SoftwareInventoryAgent()
        self.agent_name = "inventory"

        logger.info("📊 Inventory Agent initialized with specialized agents for coordination")

    async def get_inventory_summary(self, days: int = 90) -> Dict[str, Any]:
        """Get aggregated inventory summary from specialized agents"""
        try:
            start_time = time.time()
            
            # Get summaries from both specialized agents
            software_summary = await self.software_inventory_agent.get_software_summary(days=days)
            os_summary = await self.os_inventory_agent.get_os_summary(days=days)
            
            # Record statistics
            response_time_ms = (time.time() - start_time) * 1000
            cache_stats_manager.record_agent_request(
                agent_name=self.agent_name,
                response_time_ms=response_time_ms,
                was_cache_hit=False,  # Summary is always fresh
                had_error=False,
                software_name="Inventory Summary",
                version="",
                url="Summary Aggregation"
            )

            # Ensure we have dict responses
            if not isinstance(software_summary, dict):
                logger.warning(f"⚠️ Software summary is not a dict: {type(software_summary)}")
                software_summary = {"data": {}, "success": False, "error": "Invalid summary format"}

            if not isinstance(os_summary, dict):
                logger.warning(f"⚠️ OS summary is not a dict: {type(os_summary)}")
                os_summary = {"data": {}, "success": False, "error": "Invalid summary format"}

            # Combine summaries for unified view
            combined_summary = {
                "software_inventory": (
                    software_summary if software_summary.get("success") 
                    else {"data": {}, "success": False}
                ),
                "os_inventory": (
                    os_summary if os_summary.get("success") 
                    else {"data": {}, "success": False}
                ),
                "last_updated": datetime.utcnow().isoformat(),
                "query_days": days,
            }

            return combined_summary

        except Exception as e:
            logger.error("❌ Error getting inventory summary: %s", e)
            return {
                "software_inventory": {"data": {}, "success": False, "error": str(e)},
                "os_inventory": {"data": {}, "success": False, "error": str(e)},
                "last_updated": datetime.utcnow().isoformat(),
                "query_days": days,
            }

    async def clear_cache(self):
        """Clear caches for all specialized inventory agents"""
        try:
            # Clear software inventory cache
            if hasattr(self.software_inventory_agent, "clear_cache"):
                await self.software_inventory_agent.clear_cache()
                logger.info("✅ Software inventory cache cleared")

            # Clear OS inventory cache
            if hasattr(self.os_inventory_agent, "clear_cache"):
                await self.os_inventory_agent.clear_cache()
                logger.info("✅ OS inventory cache cleared")

        except Exception as e:
            logger.error("❌ Error clearing inventory caches: %s", e)
            raise
