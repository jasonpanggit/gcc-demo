"""
Comprehensive Test Runner for EOL Multi-Agent App
Runs all endpoint tests with detailed reporting
"""
import pytest
import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Determine test mode and base URL
USE_MOCK_DATA = os.getenv('USE_MOCK_DATA', 'true').lower() == 'true'
TESTING = os.getenv('TESTING', 'true').lower() == 'true'

# Set base URL based on mock data setting
if USE_MOCK_DATA:
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
    TEST_MODE = "LOCAL (Mock Data)"
else:
    BASE_URL = os.getenv('BASE_URL', 'https://app-eol-agentic-gcc-demo.azurewebsites.net')
    TEST_MODE = "REMOTE (Live Data)"

# Set environment variables
os.environ['USE_MOCK_DATA'] = str(USE_MOCK_DATA).lower()
os.environ['TESTING'] = str(TESTING).lower()
os.environ['BASE_URL'] = BASE_URL


def run_all_tests():
    """
    Run all tests with comprehensive reporting
    """
    print("=" * 80)
    print("EOL MULTI-AGENT APP - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print(f"Start Time: {datetime.utcnow().isoformat()}")
    print(f"Test Mode: {TEST_MODE}")
    print(f"Base URL: {BASE_URL}")
    print(f"Mock Data: {'ENABLED' if USE_MOCK_DATA else 'DISABLED'}")
    print("-" * 80)
    
    # Test categories to run
    test_modules = [
        ("Health & Status Endpoints", "test_health_endpoints.py"),
        ("Inventory Endpoints", "test_inventory_endpoints.py"),
        ("EOL Search Endpoints", "test_eol_search_endpoints.py"),
        ("Cache Management Endpoints", "test_cache_endpoints.py"),
        ("Alert Endpoints", "test_alert_endpoints.py"),
        ("Agent Management Endpoints", "test_agent_endpoints.py"),
        ("Cosmos DB Endpoints", "test_cosmos_endpoints.py"),
        ("Communication Endpoints", "test_communication_endpoints.py"),
        ("UI/HTML Endpoints", "test_ui_endpoints.py"),
    ]
    
    results = {}
    total_passed = 0
    total_failed = 0
    
    # Run each test module
    for category, module in test_modules:
        print(f"\n📋 Testing: {category}")
        print(f"   Module: {module}")
        print("   " + "-" * 60)
        
        # Run pytest for this module
        exit_code = pytest.main([
            f"{module}",
            "-v",
            "--tb=short",
            "--no-header",
            "-q"
        ])
        
        results[category] = "PASSED" if exit_code == 0 else "FAILED"
        if exit_code == 0:
            total_passed += 1
            print(f"   ✅ {category}: PASSED")
        else:
            total_failed += 1
            print(f"   ❌ {category}: FAILED")
    
    # Summary report
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for category, result in results.items():
        status_icon = "✅" if result == "PASSED" else "❌"
        print(f"{status_icon} {category}: {result}")
    
    print("-" * 80)
    print(f"Total Categories: {len(test_modules)}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Success Rate: {(total_passed/len(test_modules)*100):.1f}%")
    print(f"End Time: {datetime.utcnow().isoformat()}")
    print("=" * 80)
    
    return total_failed == 0


def run_specific_category(category_name: str):
    """
    Run tests for a specific category
    
    Args:
        category_name: Name of test category (e.g., 'health', 'inventory', 'cache')
    """
    test_file_map = {
        'health': 'test_health_endpoints.py',
        'inventory': 'test_inventory_endpoints.py',
        'eol': 'test_eol_search_endpoints.py',
        'cache': 'test_cache_endpoints.py',
        'alerts': 'test_alert_endpoints.py',
        'agents': 'test_agent_endpoints.py',
        'cosmos': 'test_cosmos_endpoints.py',
        'communications': 'test_communication_endpoints.py',
        'ui': 'test_ui_endpoints.py',
    }
    
    if category_name.lower() not in test_file_map:
        print(f"❌ Unknown category: {category_name}")
        print(f"Available categories: {', '.join(test_file_map.keys())}")
        return False
    
    test_file = test_file_map[category_name.lower()]
    print(f"🧪 Running {category_name.upper()} tests from {test_file}")
    print(f"📍 Base URL: {BASE_URL}")
    print(f"🔧 Test Mode: {TEST_MODE}")
    print("-" * 80)
    
    exit_code = pytest.main([
        f"tests/{test_file}",
        "-v",
        "--tb=short"
    ])
    
    return exit_code == 0


def run_with_coverage():
    """
    Run all tests with coverage reporting
    """
    print("=" * 80)
    print("RUNNING TESTS WITH COVERAGE ANALYSIS")
    print("=" * 80)
    print(f"Test Mode: {TEST_MODE}")
    print(f"Base URL: {BASE_URL}")
    print("-" * 80)
    
    exit_code = pytest.main([
        "tests/",
        "-v",
        "--cov=.",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--tb=short"
    ])
    
    print("\n" + "=" * 80)
    print("Coverage report generated in htmlcov/index.html")
    print("=" * 80)
    
    return exit_code == 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run EOL App Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test local server with mock data (default)
  python3 run_comprehensive_tests.py
  
  # Test remote Azure server with live data
  USE_MOCK_DATA=false python3 run_comprehensive_tests.py
  
  # Test specific category against remote server
  USE_MOCK_DATA=false python3 run_comprehensive_tests.py --category health
  
  # Test with custom base URL
  BASE_URL=http://localhost:5000 python3 run_comprehensive_tests.py
        """
    )
    parser.add_argument(
        '--category',
        type=str,
        help='Run specific test category (health, inventory, cache, etc.)'
    )
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Run tests with coverage analysis'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick smoke tests only'
    )
    parser.add_argument(
        '--remote',
        action='store_true',
        help='Test against remote Azure server (sets USE_MOCK_DATA=false)'
    )
    parser.add_argument(
        '--url',
        type=str,
        help='Override base URL for testing'
    )
    
    args = parser.parse_args()
    
    # Handle --remote flag
    if args.remote:
        os.environ['USE_MOCK_DATA'] = 'false'
        # Re-evaluate globals after changing environment
        globals()['USE_MOCK_DATA'] = False
        globals()['BASE_URL'] = os.getenv('BASE_URL', 'https://app-eol-agentic-gcc-demo.azurewebsites.net')
        globals()['TEST_MODE'] = "REMOTE (Live Data)"
        os.environ['BASE_URL'] = BASE_URL
    
    # Handle --url flag
    if args.url:
        globals()['BASE_URL'] = args.url
        os.environ['BASE_URL'] = args.url
        print(f"🔧 Custom Base URL: {args.url}")
    
    if args.category:
        success = run_specific_category(args.category)
    elif args.coverage:
        success = run_with_coverage()
    elif args.quick:
        # Quick smoke test - just health endpoints
        success = run_specific_category('health')
    else:
        success = run_all_tests()
    
    sys.exit(0 if success else 1)
