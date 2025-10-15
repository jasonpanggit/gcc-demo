"""
API Test Runner - Test all endpoints with mock data
Run this to validate the refactored codebase without Azure dependencies
"""
import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import test utilities
from tests.test_config import test_config, enable_mock_mode
from tests.mock_agents import get_software_inventory_agent, get_os_inventory_agent


class APITester:
    """Test all API endpoints with mock data"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
    
    def log_test(self, test_name: str, success: bool, duration: float, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "success": success,
            "duration": duration,
            "details": details
        })
        print(f"{status} | {test_name:40s} | {duration:6.3f}s | {details}")
    
    async def test_software_inventory(self):
        """Test software inventory endpoint"""
        test_start = datetime.utcnow()
        try:
            agent = get_software_inventory_agent()
            result = await agent.get_software_inventory(days=90)
            
            assert result['success'], "API returned success=False"
            assert 'data' in result, "Missing 'data' key"
            assert 'count' in result, "Missing 'count' key"
            assert len(result['data']) > 0, "No data returned"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/inventory (software)",
                True,
                duration,
                f"{result['count']} items"
            )
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/inventory (software)", False, duration, str(e))
            return None
    
    async def test_software_inventory_filtered(self):
        """Test software inventory with filter"""
        test_start = datetime.utcnow()
        try:
            agent = get_software_inventory_agent()
            result = await agent.get_software_inventory(days=90, software_filter="Python")
            
            assert result['success'], "API returned success=False"
            assert len(result['data']) > 0, "Filter returned no results"
            
            # Verify all results contain filter term
            for item in result['data']:
                assert 'python' in item['name'].lower(), f"Item {item['name']} doesn't match filter"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/inventory?filter=Python",
                True,
                duration,
                f"{result['count']} items"
            )
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/inventory?filter=Python", False, duration, str(e))
            return None
    
    async def test_software_summary(self):
        """Test software inventory summary"""
        test_start = datetime.utcnow()
        try:
            agent = get_software_inventory_agent()
            result = await agent.get_software_summary(days=90)
            
            assert result['success'], "API returned success=False"
            assert 'total_software' in result, "Missing 'total_software'"
            assert 'total_computers' in result, "Missing 'total_computers'"
            assert 'top_categories' in result, "Missing 'top_categories'"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/inventory/summary",
                True,
                duration,
                f"{result['total_software']} software, {result['total_computers']} computers"
            )
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/inventory/summary", False, duration, str(e))
            return None
    
    async def test_os_inventory(self):
        """Test OS inventory endpoint"""
        test_start = datetime.utcnow()
        try:
            agent = get_os_inventory_agent()
            result = await agent.get_os_inventory(days=7)
            
            assert result['success'], "API returned success=False"
            assert 'data' in result, "Missing 'data' key"
            assert 'count' in result, "Missing 'count' key"
            assert len(result['data']) > 0, "No data returned"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/inventory/raw/os",
                True,
                duration,
                f"{result['count']} items"
            )
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/inventory/raw/os", False, duration, str(e))
            return None
    
    async def test_os_summary(self):
        """Test OS inventory summary"""
        test_start = datetime.utcnow()
        try:
            agent = get_os_inventory_agent()
            result = await agent.get_os_summary(days=90)
            
            assert 'total_computers' in result, "Missing 'total_computers'"
            assert 'windows_count' in result, "Missing 'windows_count'"
            assert 'linux_count' in result, "Missing 'linux_count'"
            assert 'top_versions' in result, "Missing 'top_versions'"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/inventory/os/summary",
                True,
                duration,
                f"{result['total_computers']} computers (Win: {result['windows_count']}, Linux: {result['linux_count']})"
            )
            return result
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/inventory/os/summary", False, duration, str(e))
            return None
    
    async def test_cache_operations(self):
        """Test cache operations"""
        test_start = datetime.utcnow()
        try:
            sw_agent = get_software_inventory_agent()
            os_agent = get_os_inventory_agent()
            
            # Test software cache clear
            sw_clear = await sw_agent.clear_cache()
            assert sw_clear['success'], "Software cache clear failed"
            
            # Test OS cache clear
            os_clear = await os_agent.clear_cache()
            assert os_clear['success'], "OS cache clear failed"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "POST /api/cache/clear",
                True,
                duration,
                "Software & OS caches cleared"
            )
            return {"software": sw_clear, "os": os_clear}
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("POST /api/cache/clear", False, duration, str(e))
            return None
    
    async def test_health_checks(self):
        """Test health check endpoints"""
        test_start = datetime.utcnow()
        try:
            sw_agent = get_software_inventory_agent()
            os_agent = get_os_inventory_agent()
            
            # Test software health
            sw_health = await sw_agent.health_check()
            assert sw_health['ok'], "Software agent health check failed"
            
            # Test OS health
            os_health = await os_agent.health_check()
            assert os_health['ok'], "OS agent health check failed"
            
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test(
                "GET /api/health",
                True,
                duration,
                "All agents healthy"
            )
            return {"software": sw_health, "os": os_health}
            
        except Exception as e:
            duration = (datetime.utcnow() - test_start).total_seconds()
            self.log_test("GET /api/health", False, duration, str(e))
            return None
    
    async def run_all_tests(self):
        """Run all tests"""
        self.start_time = datetime.utcnow()
        
        print("\n" + "=" * 100)
        print("🧪 API TEST SUITE - Mock Data Mode")
        print("=" * 100)
        print(f"Test Config: {test_config.num_computers} computers, Mock Mode: {test_config.use_mock_data}")
        print(f"Started: {self.start_time.isoformat()}")
        print("-" * 100)
        print(f"{'Status':6s} | {'Test Name':40s} | {'Time':8s} | Details")
        print("-" * 100)
        
        # Run all tests
        await self.test_health_checks()
        await self.test_software_inventory()
        await self.test_software_inventory_filtered()
        await self.test_software_summary()
        await self.test_os_inventory()
        await self.test_os_summary()
        await self.test_cache_operations()
        
        # Summary
        end_time = datetime.utcnow()
        total_duration = (end_time - self.start_time).total_seconds()
        passed = sum(1 for r in self.results if r['success'])
        failed = len(self.results) - passed
        
        print("-" * 100)
        print(f"\n📊 TEST SUMMARY")
        print(f"  Total Tests: {len(self.results)}")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⏱️  Total Duration: {total_duration:.3f}s")
        print(f"  📅 Completed: {end_time.isoformat()}")
        
        if failed > 0:
            print(f"\n⚠️  {failed} test(s) failed!")
            return False
        else:
            print(f"\n🎉 All tests passed!")
            return True


async def main():
    """Main test execution"""
    print("\n🔧 Initializing test environment...")
    
    # Enable mock mode
    enable_mock_mode(num_computers=25, cache_enabled=False)
    
    # Run tests
    tester = APITester()
    success = await tester.run_all_tests()
    
    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
