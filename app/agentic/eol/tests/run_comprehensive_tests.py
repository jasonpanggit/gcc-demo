#!/usr/bin/env python3

"""Comprehensive Pytest runner for the EOL Multi-Agent application."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Resolve key directories and ensure project imports work regardless of CWD
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


def find_repo_root() -> Path:
    """Locate the repository root by walking up from this script."""

    search_path = [SCRIPT_DIR] + list(SCRIPT_DIR.parents)
    for candidate in search_path:
        if (candidate / ".venv").exists() and (
            (candidate / ".venv" / "bin" / "python").exists()
            or (candidate / ".venv" / "Scripts" / "python.exe").exists()
        ):
            return candidate
        if (candidate / ".git").exists():
            return candidate

    return search_path[-1]


REPO_ROOT = find_repo_root()


def ensure_project_interpreter() -> None:
    """Re-exec using the repo's virtualenv when available."""

    if sys.platform == "win32":
        expected_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        expected_python = REPO_ROOT / ".venv" / "bin" / "python"

    if not expected_python.exists():
        return

    current_executable = Path(sys.executable).resolve()
    if current_executable != expected_python.resolve():
        print(f"🔁 Re-launching under project virtualenv: {expected_python}")
        os.execv(str(expected_python), [str(expected_python)] + sys.argv)


ensure_project_interpreter()

# Add parent directory to path
sys.path.insert(0, str(PROJECT_ROOT))

# Default configuration values (overridden via CLI arguments)
DEFAULT_LOCAL_BASE_URL = "http://localhost:8000"
DEFAULT_REMOTE_BASE_URL = "https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io/"

USE_MOCK_DATA = True
TESTING = True
BASE_URL = DEFAULT_LOCAL_BASE_URL
TEST_MODE = "LOCAL (Mock Data)"


def configure_environment(use_mock_data: bool, testing: bool, base_url: str | None = None) -> None:
    """Update module configuration and propagate values to environment variables."""

    global USE_MOCK_DATA, TESTING, BASE_URL, TEST_MODE

    USE_MOCK_DATA = use_mock_data
    TESTING = testing

    if base_url:
        BASE_URL = base_url
    else:
        BASE_URL = DEFAULT_LOCAL_BASE_URL if USE_MOCK_DATA else DEFAULT_REMOTE_BASE_URL

    TEST_MODE = "LOCAL (Mock Data)" if USE_MOCK_DATA else "REMOTE (Live Data)"

    os.environ["USE_MOCK_DATA"] = str(USE_MOCK_DATA).lower()
    os.environ["TESTING"] = str(TESTING).lower()
    os.environ["BASE_URL"] = BASE_URL


# Ensure environment defaults are applied on import
configure_environment(USE_MOCK_DATA, TESTING, BASE_URL)


def run_all_tests() -> bool:
    """Run every test module with categorized reporting."""

    print("=" * 80)
    print("EOL MULTI-AGENT APP - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print(f"Start Time: {datetime.utcnow().isoformat()}")
    print(f"Test Mode: {TEST_MODE}")
    print(f"Base URL: {BASE_URL}")
    print(f"Mock Data: {'ENABLED' if USE_MOCK_DATA else 'DISABLED'}")
    print("-" * 80)

    test_modules = [
        ("Health & Status Endpoints", "test_health_endpoints.py"),
        ("Inventory Endpoints", "test_inventory_endpoints.py"),
        ("EOL Search Endpoints", "test_eol_search_endpoints.py"),
        ("Cache Management Endpoints", "test_cache_endpoints.py"),
        ("Advanced Cache Endpoints", "test_cache_advanced_endpoints.py"),
        ("Alert Endpoints", "test_alert_endpoints.py"),
        ("Agent Management Endpoints", "test_agent_endpoints.py"),
        ("Agent Framework Inventory Assistant Endpoints", "test_inventory_asst_endpoints.py"),
        ("Azure MCP Endpoints", "test_azure_mcp_endpoints.py"),
        ("Cosmos DB Endpoints", "test_cosmos_endpoints.py"),
        ("Communication Endpoints", "test_communication_endpoints.py"),
        ("UI/HTML Endpoints", "test_ui_endpoints.py"),
    ]

    results: dict[str, str] = {}
    total_passed = 0
    total_failed = 0

    for category, module in test_modules:
        print(f"\n📋 Testing: {category}")
        print(f"   Module: {module}")
        print("   " + "-" * 60)

        exit_code = pytest.main(
            [
                str(SCRIPT_DIR / module),
                "-v",
                "--tb=short",
                "--no-header",
                "-q",
            ]
        )

        results[category] = "PASSED" if exit_code == 0 else "FAILED"
        if exit_code == 0:
            total_passed += 1
            print(f"   ✅ {category}: PASSED")
        else:
            total_failed += 1
            print(f"   ❌ {category}: FAILED")

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
    success_rate = (total_passed / len(test_modules) * 100) if test_modules else 0.0
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"End Time: {datetime.utcnow().isoformat()}")
    print("=" * 80)

    return total_failed == 0


def run_specific_category(category_name: str) -> bool:
    """Run tests for a specific category."""

    test_file_map = {
        "health": "test_health_endpoints.py",
        "inventory": "test_inventory_endpoints.py",
        "eol": "test_eol_search_endpoints.py",
        "cache": "test_cache_endpoints.py",
        "cache_advanced": "test_cache_advanced_endpoints.py",
        "alerts": "test_alert_endpoints.py",
        "agents": "test_agent_endpoints.py",
        "inventory_asst": "test_inventory_asst_endpoints.py",
        "mcp": "test_azure_mcp_endpoints.py",
        "cosmos": "test_cosmos_endpoints.py",
        "communications": "test_communication_endpoints.py",
        "ui": "test_ui_endpoints.py",
    }

    key = category_name.lower()
    if key not in test_file_map:
        print(f"❌ Unknown category: {category_name}")
        print(f"Available categories: {', '.join(sorted(test_file_map.keys()))}")
        return False

    test_file = test_file_map[key]
    print(f"🧪 Running {key.upper()} tests from {test_file}")
    print(f"📍 Base URL: {BASE_URL}")
    print(f"🔧 Test Mode: {TEST_MODE}")
    print("-" * 80)

    exit_code = pytest.main([
        str(SCRIPT_DIR / test_file),
        "-v",
        "--tb=short",
    ])

    return exit_code == 0


def run_with_coverage() -> bool:
    """Run the entire suite with coverage reporting enabled."""

    print("=" * 80)
    print("RUNNING TESTS WITH COVERAGE ANALYSIS")
    print("=" * 80)
    print(f"Test Mode: {TEST_MODE}")
    print(f"Base URL: {BASE_URL}")
    print("-" * 80)

    exit_code = pytest.main(
        [
            str(SCRIPT_DIR),
            "-v",
            "--cov=.",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--tb=short",
        ]
    )

    print("\n" + "=" * 80)
    print("Coverage report generated in htmlcov/index.html")
    print("=" * 80)

    return exit_code == 0


def parse_args() -> argparse.Namespace:
    """Configure and parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Run EOL App Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test local server with mock data (default)
  python3 run_comprehensive_tests.py

  # Test remote Azure server with live data
  python3 run_comprehensive_tests.py --remote

  # Test specific category against remote server
  python3 run_comprehensive_tests.py --remote --category health

  # Test with custom base URL and disable mock data
  python3 run_comprehensive_tests.py --use-mock-data false --base-url http://localhost:5000
        """,
    )

    parser.add_argument(
        "--category",
        type=str,
        help="Run specific test category (health, inventory, cache, etc.)",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with coverage analysis",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick smoke tests only",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Shortcut for remote testing (equivalent to --use-mock-data false)",
    )
    parser.add_argument(
        "--use-mock-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable mock data (default: enabled)",
    )
    parser.add_argument(
        "--testing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Toggle testing mode (default: enabled)",
    )
    parser.add_argument(
        "--base-url",
        "--url",
        dest="base_url",
        type=str,
        help="Override the service base URL",
    )

    return parser.parse_args()


def main() -> int:
    """Entry point for the CLI."""

    args = parse_args()

    use_mock_data = args.use_mock_data
    if args.remote:
        use_mock_data = False

    base_url = args.base_url
    if args.remote and not base_url:
        base_url = DEFAULT_REMOTE_BASE_URL

    if not base_url:
        base_url = DEFAULT_LOCAL_BASE_URL if use_mock_data else DEFAULT_REMOTE_BASE_URL

    configure_environment(use_mock_data=use_mock_data, testing=args.testing, base_url=base_url)

    if args.base_url:
        print(f"🔧 Custom Base URL: {args.base_url}")

    if args.category:
        success = run_specific_category(args.category)
    elif args.coverage:
        success = run_with_coverage()
    elif args.quick:
        success = run_specific_category("health")
    else:
        success = run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
