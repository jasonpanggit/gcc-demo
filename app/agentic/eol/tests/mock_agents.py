"""
Mock Agents for Local Testing
These agents return mock data instead of querying Azure services
"""
import asyncio
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# Get configuration from environment
MOCK_NUM_COMPUTERS = int(os.getenv("MOCK_NUM_COMPUTERS", "50"))

# Import mock data generators
try:
    from .mock_data import mock_generator, get_mock_software_inventory, get_mock_os_inventory
except ImportError:
    from mock_data import mock_generator, get_mock_software_inventory, get_mock_os_inventory


class MockSoftwareInventoryAgent:
    """Mock version of SoftwareInventoryAgent that returns generated data"""
    
    def __init__(self):
        self.agent_name = "software_inventory"
        self.workspace_id = "mock-workspace-id"
        print(f"✅ MockSoftwareInventoryAgent initialized (mock mode)")
    
    async def get_software_inventory(
        self, 
        days: int = 90, 
        software_filter: Optional[str] = None,
        use_cache: bool = True,
        limit: int = 10000
    ) -> Dict[str, Any]:
        """
        Get mock software inventory data
        
        Args:
            days: Days of data (ignored in mock)
            software_filter: Filter by software name (applied to mock data)
            use_cache: Whether to use caching (ignored in mock)
            limit: Max results (applied to mock data)
            
        Returns:
            Dict matching real API response format
        """
        # Simulate query delay
        await asyncio.sleep(0.1)
        
        # Generate mock data
        result = get_mock_software_inventory(num_computers=MOCK_NUM_COMPUTERS)
        
        # Apply software filter if specified
        if software_filter:
            filtered_data = [
                item for item in result['data']
                if software_filter.lower() in item['name'].lower()
            ]
            result['data'] = filtered_data
            result['count'] = len(filtered_data)
        
        # Apply limit
        if len(result['data']) > limit:
            result['data'] = result['data'][:limit]
            result['count'] = limit
        
        result['query_params'] = {
            "days": days,
            "software_filter": software_filter,
            "limit": limit
        }
        
        print(f"🧪 [MOCK] Retrieved {result['count']} software items")
        return result
    
    async def get_software_summary(self, days: int = 90) -> Dict[str, Any]:
        """Get aggregated software inventory summary"""
        inventory_result = await self.get_software_inventory(days=days)
        
        if not inventory_result.get("success"):
            return {
                "success": False,
                "error": "Mock data generation failed",
                "total_software": 0,
                "total_computers": 0,
                "last_updated": datetime.utcnow().isoformat()
            }
        
        software_items = inventory_result.get("data", [])
        
        # Count unique software and computers
        unique_software = set((item['name'], item['version']) for item in software_items)
        unique_computers = set(item['computer'] for item in software_items)
        
        by_category = {}
        by_publisher = {}
        
        for item in software_items:
            category = item.get("software_type", "Other")
            publisher = item.get("publisher", "Unknown")
            
            by_category[category] = by_category.get(category, 0) + 1
            by_publisher[publisher] = by_publisher.get(publisher, 0) + 1
        
        # Top 5 in each category
        top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
        top_publishers = sorted(by_publisher.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "success": True,
            "total_software": len(unique_software),
            "total_computers": len(unique_computers),
            "total_installations": len(software_items),
            "by_category": by_category,
            "by_publisher": by_publisher,
            "top_categories": [{"category": k, "count": v} for k, v in top_categories],
            "top_publishers": [{"publisher": k, "count": v} for k, v in top_publishers],
            "last_updated": datetime.utcnow().isoformat(),
            "from_cache": False,
            "cached_at": None
        }
    
    async def clear_cache(self) -> Dict[str, Any]:
        """Mock cache clearing"""
        await asyncio.sleep(0.05)
        print(f"🧪 [MOCK] Cleared software inventory cache")
        return {
            "success": True,
            "message": "Mock cache cleared",
            "agent": self.agent_name
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Mock health check - always healthy"""
        return {
            "configured": True,
            "logs_client": True,
            "ok": True,
            "sample_data_available": True,
            "checked_at": datetime.utcnow().isoformat(),
            "mode": "mock"
        }


class MockOSInventoryAgent:
    """Mock version of OSInventoryAgent that returns generated data"""
    
    def __init__(self):
        self.agent_name = "os_inventory"
        self.workspace_id = "mock-workspace-id"
        print(f"✅ MockOSInventoryAgent initialized (mock mode)")
    
    async def get_os_inventory(
        self,
        days: int = 7,
        use_cache: bool = True,
        limit: int = 10000
    ) -> Dict[str, Any]:
        """
        Get mock OS inventory data
        
        Args:
            days: Days of data (ignored in mock)
            use_cache: Whether to use caching (ignored in mock)
            limit: Max results (applied to mock data)
            
        Returns:
            Dict matching real API response format
        """
        # Simulate query delay
        await asyncio.sleep(0.1)
        
        # Generate mock data
        result = get_mock_os_inventory(num_computers=MOCK_NUM_COMPUTERS)
        
        # Apply limit
        if len(result['data']) > limit:
            result['data'] = result['data'][:limit]
            result['count'] = limit
        
        result['query_params'] = {
            "days": days,
            "limit": limit
        }
        
        print(f"🧪 [MOCK] Retrieved {result['count']} OS items")
        return result
    
    async def get_os_summary(self, days: int = 90) -> Dict[str, Any]:
        """Summarize OS inventory by OS name and type."""
        inventory_result = await self.get_os_inventory(days=days)
        
        if not inventory_result.get("success", False):
            return {
                "error": "Mock data generation failed",
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
        by_type: Dict[str, int] = {}
        windows = 0
        linux = 0
        
        for item in inventory:
            name = item.get("os_name", "Unknown")
            ver = item.get("os_version", "Unknown")
            otype = item.get("os_type", "Unknown").lower()
            computer_type = item.get("computer_type", "Unknown")
            
            by_name[name] = by_name.get(name, 0) + 1
            by_version[f"{name} {ver}"] = by_version.get(f"{name} {ver}", 0) + 1
            by_type[computer_type] = by_type.get(computer_type, 0) + 1
            
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
            "azure_vms": by_type.get("Azure VM", 0),
            "arc_servers": by_type.get("Arc-enabled Server", 0),
            "by_name": by_name,
            "by_type": by_type,
            "top_versions": top_versions,
            "last_updated": datetime.utcnow().isoformat(),
            "from_cache": inventory_result.get("from_cache", False),
            "cached_at": inventory_result.get("cached_at", None),
        }
    
    async def clear_cache(self) -> Dict[str, Any]:
        """Mock cache clearing"""
        await asyncio.sleep(0.05)
        print(f"🧪 [MOCK] Cleared OS inventory cache")
        return {
            "success": True,
            "message": "Mock cache cleared",
            "agent": self.agent_name
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Mock health check - always healthy"""
        return {
            "configured": True,
            "logs_client": True,
            "ok": True,
            "sample_data_available": True,
            "checked_at": datetime.utcnow().isoformat(),
            "mode": "mock"
        }


# Factory function to get appropriate agent based on config
def get_software_inventory_agent():
    """Get software inventory agent (mock or real based on config)"""
    use_mock = os.getenv('USE_MOCK_DATA', 'true').lower() == 'true'
    if use_mock:
        return MockSoftwareInventoryAgent()
    else:
        # Import real agent only when needed
        from agents.software_inventory_agent import SoftwareInventoryAgent
        return SoftwareInventoryAgent()


def get_os_inventory_agent():
    """Get OS inventory agent (mock or real based on config)"""
    use_mock = os.getenv('USE_MOCK_DATA', 'true').lower() == 'true'
    if use_mock:
        return MockOSInventoryAgent()
    else:
        # Import real agent only when needed
        from agents.os_inventory_agent import OSInventoryAgent
        return OSInventoryAgent()


if __name__ == "__main__":
    import asyncio
    
    async def test_mock_agents():
        print("🧪 Testing Mock Agents\n")
        print("=" * 80)
        
        # Test software agent
        print("\n📦 Testing MockSoftwareInventoryAgent")
        print("-" * 80)
        sw_agent = MockSoftwareInventoryAgent()
        sw_result = await sw_agent.get_software_inventory(days=90)
        print(f"Success: {sw_result['success']}")
        print(f"Count: {sw_result['count']}")
        print(f"Sample items: {sw_result['data'][:2]}")
        
        sw_summary = await sw_agent.get_software_summary()
        print(f"\nSummary:")
        print(f"  Total Software: {sw_summary['total_software']}")
        print(f"  Total Computers: {sw_summary['total_computers']}")
        print(f"  Top Categories: {sw_summary['top_categories']}")
        
        # Test OS agent
        print("\n" + "=" * 80)
        print("\n🖥️  Testing MockOSInventoryAgent")
        print("-" * 80)
        os_agent = MockOSInventoryAgent()
        os_result = await os_agent.get_os_inventory(days=7)
        print(f"Success: {os_result['success']}")
        print(f"Count: {os_result['count']}")
        print(f"Sample items: {os_result['data'][:2]}")
        
        os_summary = await os_agent.get_os_summary()
        print(f"\nSummary:")
        print(f"  Total Computers: {os_summary['total_computers']}")
        print(f"  Windows: {os_summary['windows_count']}")
        print(f"  Linux: {os_summary['linux_count']}")
        print(f"  Top Versions: {os_summary['top_versions']}")
    
    asyncio.run(test_mock_agents())
