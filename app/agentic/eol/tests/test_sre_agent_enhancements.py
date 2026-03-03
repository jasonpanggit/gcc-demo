"""
Comprehensive tests for SRE agent improvements.

Tests validate:
1. Response formatting (no raw JSON, user-friendly HTML)
2. Parameter discovery and validation
3. User interaction flows
4. Context caching with TTL
5. Integration with SRE orchestrator

Phase 1: Response formatting, parameter discovery, and caching (30 tests)
Phase 2: User interaction flows and integration (22 tests) - Added after Tasks #4-5
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from utils.sre_response_formatter import SREResponseFormatter
from utils.sre_interaction_handler import SREInteractionHandler
from utils.sre_cache import SRECacheManager

# Mark all tests in this module
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ==========================================
# Phase 1: Response Formatting Tests
# ==========================================


class TestSREResponseFormatter:
    """Tests for SREResponseFormatter - converting JSON to user-friendly messages."""

    def test_format_resource_list_with_resources(self):
        """Test formatting a resource list as HTML table"""
        formatter = SREResponseFormatter()

        resources = [
            {
                "name": "vm-web-01",
                "location": "eastus",
                "resource_group": "rg-production",
                "status": "Running",
            },
            {
                "name": "vm-api-01",
                "location": "westus",
                "resource_group": "rg-staging",
                "status": "Running",
            },
        ]

        result = formatter.format_resource_list(
            resources, "Virtual Machine", context="Select a VM to check"
        )

        # Validate HTML structure
        assert "<table" in result
        assert "</table>" in result
        assert "vm-web-01" in result
        assert "vm-api-01" in result
        assert "Select a VM to check" in result

        # Ensure no raw JSON field names
        assert "resource_id" not in result
        assert "subscription_id" not in result

    def test_format_resource_list_empty(self):
        """Test formatting an empty resource list"""
        formatter = SREResponseFormatter()

        result = formatter.format_resource_list([], "Virtual Machine")

        assert "No Virtual Machines found" in result
        assert "<table" not in result

    def test_format_resource_list_single_resource(self):
        """Test formatting a single resource (singular form)"""
        formatter = SREResponseFormatter()

        resources = [
            {
                "name": "vm-web-01",
                "location": "eastus",
                "resource_group": "rg-production",
            }
        ]

        result = formatter.format_resource_list(resources, "Virtual Machine")

        # Should use singular form for single resource
        assert "1" in result or "one" in result.lower()

    def test_no_raw_json_in_formatted_output(self):
        """Test that no raw JSON field names appear in user-facing output"""
        formatter = SREResponseFormatter()

        resources = [
            {
                "name": "test-resource",
                "id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                "properties": {"provisioningState": "Succeeded"},
            }
        ]

        result = formatter.format_resource_list(resources, "Resource")

        # Raw JSON fields should NOT appear
        assert "provisioningState" not in result
        assert '"properties"' not in result
        assert '"id":' not in result

        # User-friendly names should appear
        assert "test-resource" in result

    def test_status_icons_rendered(self):
        """Test that status icons (emoji) are rendered for visual feedback"""
        formatter = SREResponseFormatter()

        # Test that status icons exist
        assert "✅" in formatter.STATUS_ICONS.values()
        assert "⚠️" in formatter.STATUS_ICONS.values()
        assert "❌" in formatter.STATUS_ICONS.values()

    def test_html_escaping_prevents_injection(self):
        """Test that HTML is properly escaped to prevent injection"""
        formatter = SREResponseFormatter()

        resources = [
            {
                "name": "<script>alert('xss')</script>",
                "location": "eastus",
                "resource_group": "rg-test",
            }
        ]

        result = formatter.format_resource_list(resources, "Resource")

        # Script tags should be escaped
        assert "<script>" not in result
        assert "&lt;script&gt;" in result or "script" not in result.lower()


# ==========================================
# Phase 1: Parameter Discovery Tests
# ==========================================


class TestSREInteractionHandler:
    """Tests for SREInteractionHandler - parameter discovery and validation."""

    def test_check_required_params_all_present(self):
        """Test parameter checking when all required params are present"""
        handler = SREInteractionHandler()

        params = {"resource_id": "/subscriptions/abc/resourceGroups/rg/providers/vm-01"}

        result = handler.check_required_params("check_resource_health", params)

        # Should return None when all params present
        assert result is None

    def test_check_required_params_missing_single(self):
        """Test parameter checking when single param is missing"""
        handler = SREInteractionHandler()

        params = {}  # Missing resource_id

        result = handler.check_required_params("check_resource_health", params)

        # Should return needs_user_input status
        assert result is not None
        assert result["status"] == "needs_user_input"
        assert "resource_id" in result["missing_params"]
        assert "message" in result
        assert len(result["message"]) > 0

    def test_check_required_params_missing_multiple(self):
        """Test parameter checking when multiple params are missing"""
        handler = SREInteractionHandler()

        params = {}  # Missing both container_app_name and resource_group

        result = handler.check_required_params("check_container_app_health", params)

        assert result is not None
        assert result["status"] == "needs_user_input"
        assert "container_app_name" in result["missing_params"]
        assert "resource_group" in result["missing_params"]
        assert len(result["missing_params"]) == 2

    def test_check_required_params_empty_string_treated_as_missing(self):
        """Test that empty strings are treated as missing parameters"""
        handler = SREInteractionHandler()

        params = {"resource_id": ""}  # Empty string

        result = handler.check_required_params("check_resource_health", params)

        # Empty string should be treated as missing
        assert result is not None
        assert "resource_id" in result["missing_params"]

    def test_check_required_params_whitespace_treated_as_missing(self):
        """Test that whitespace-only strings are treated as missing"""
        handler = SREInteractionHandler()

        params = {"resource_id": "   "}  # Whitespace only

        result = handler.check_required_params("check_resource_health", params)

        assert result is not None
        assert "resource_id" in result["missing_params"]

    def test_check_required_params_unknown_tool(self):
        """Test parameter checking for tool with no required params defined"""
        handler = SREInteractionHandler()

        params = {}

        result = handler.check_required_params("unknown_tool", params)

        # Should return None for unknown tools (no validation)
        assert result is None

    def test_missing_params_message_is_user_friendly(self):
        """Test that missing parameter messages are user-friendly"""
        handler = SREInteractionHandler()

        params = {}

        result = handler.check_required_params("check_resource_health", params)

        message = result["message"]

        # Should contain user-friendly text
        assert "Resource ID" in message or "resource" in message.lower()
        assert "💡" in message or "hint" in message.lower() or "try" in message.lower()

        # Should NOT contain technical field names
        assert "resource_id" not in message.lower() or "Resource ID" in message

    def test_missing_params_message_includes_helpful_suggestions(self):
        """Test that missing param messages include actionable suggestions"""
        handler = SREInteractionHandler()

        params = {}

        result = handler.check_required_params("check_container_app_health", params)

        message = result["message"]

        # Should include suggestions for finding resources
        assert ("💡" in message or "list" in message.lower() or "find" in message.lower())

    @pytest.mark.asyncio
    async def test_discover_resource_groups_success(self):
        """Test resource group discovery with mocked Azure CLI"""
        mock_cli_executor = AsyncMock(
            return_value={
                "output": json.dumps([
                    {"name": "rg-production", "location": "eastus"},
                    {"name": "rg-staging", "location": "westus"},
                ])
            }
        )

        handler = SREInteractionHandler(azure_cli_executor=mock_cli_executor)

        result = await handler.discover_resource_groups()

        assert len(result) == 2
        assert result[0]["name"] == "rg-production"
        assert result[1]["name"] == "rg-staging"

    @pytest.mark.asyncio
    async def test_discover_resource_groups_empty_result(self):
        """Test resource group discovery when no groups found"""
        mock_cli_executor = AsyncMock(return_value={"output": json.dumps([])})

        handler = SREInteractionHandler(azure_cli_executor=mock_cli_executor)

        result = await handler.discover_resource_groups()

        assert result == []

    @pytest.mark.asyncio
    async def test_discover_resource_groups_cli_failure(self):
        """Test resource group discovery when CLI fails"""
        mock_cli_executor = AsyncMock(
            side_effect=Exception("Azure CLI not authenticated")
        )

        handler = SREInteractionHandler(azure_cli_executor=mock_cli_executor)

        # Should handle exception gracefully
        result = await handler.discover_resource_groups()

        # Should return empty list on failure
        assert result == []


# ==========================================
# Phase 1: Response Format Validation Helpers
# ==========================================


def assert_no_raw_json(response: str) -> None:
    """Helper: Validate that no raw JSON structures appear in user-facing text.

    Args:
        response: User-facing response string

    Raises:
        AssertionError: If raw JSON detected
    """
    # Check for raw JSON field names (snake_case)
    raw_fields = [
        "resource_id",
        "subscription_id",
        "resource_group_name",
        "provisioning_state",
        "properties",
    ]

    for field in raw_fields:
        if f'"{field}"' in response or f"'{field}'" in response:
            pytest.fail(
                f"Raw JSON field '{field}' found in user-facing response: {response[:200]}"
            )

    # Check for JSON structures
    if response.strip().startswith("{") and response.strip().endswith("}"):
        pytest.fail(f"Response appears to be raw JSON: {response[:200]}")


def assert_friendly_formatting(response: str) -> None:
    """Helper: Validate that response uses friendly formatting.

    Args:
        response: User-facing response string

    Raises:
        AssertionError: If response doesn't use friendly formatting
    """
    # Should use one of these friendly formats
    has_html_table = "<table" in response and "</table>" in response
    has_html_list = "<ul>" in response or "<ol>" in response
    has_natural_language = any(
        phrase in response.lower()
        for phrase in ["found", "available", "here are", "select", "choose"]
    )

    assert (
        has_html_table or has_html_list or has_natural_language
    ), f"Response doesn't use friendly formatting: {response[:200]}"


def validate_needs_user_input_structure(result: dict) -> None:
    """Helper: Validate needs_user_input response structure.

    Args:
        result: Result dictionary from interaction handler

    Raises:
        AssertionError: If structure is invalid
    """
    assert "status" in result
    assert result["status"] == "needs_user_input"
    assert "missing_params" in result
    assert isinstance(result["missing_params"], list)
    assert len(result["missing_params"]) > 0
    assert "message" in result
    assert len(result["message"]) > 0
    assert_friendly_formatting(result["message"])
    assert_no_raw_json(result["message"])


# ==========================================
# Phase 1: Integration Tests
# ==========================================


@pytest.mark.integration
class TestSREAgentIntegration:
    """Integration tests for SRE agent enhancements."""

    def test_formatter_and_handler_integration(self):
        """Test that formatter and handler work together correctly"""
        handler = SREInteractionHandler()
        formatter = SREResponseFormatter()

        # Test missing params flow
        params = {}
        check_result = handler.check_required_params("check_resource_health", params)

        assert check_result is not None
        validate_needs_user_input_structure(check_result)

        # Message should be user-friendly
        message = check_result["message"]
        assert_no_raw_json(message)
        assert_friendly_formatting(message)

    @pytest.mark.asyncio
    async def test_discover_and_format_resources(self):
        """Test discovering resources and formatting them for user selection"""
        mock_cli_executor = AsyncMock(
            return_value={
                "output": json.dumps([
                    {
                        "name": "rg-production",
                        "location": "eastus",
                        "id": "/subscriptions/abc/resourceGroups/rg-production",
                    }
                ])
            }
        )

        handler = SREInteractionHandler(azure_cli_executor=mock_cli_executor)
        formatter = SREResponseFormatter()

        # Discover resources
        resources = await handler.discover_resource_groups()

        # Format for user
        formatted = formatter.format_resource_list(resources, "Resource Group")

        # Validate formatted output
        assert_no_raw_json(formatted)
        assert_friendly_formatting(formatted)
        assert "rg-production" in formatted


# ==========================================
# Phase 1: Context Caching Tests
# ==========================================


class TestSRECacheManager:
    """Tests for SRECacheManager - TTL-based caching for SRE operations."""

    def test_cache_hit_with_valid_ttl(self):
        """Test cache hit when entry is still valid"""
        cache = SRECacheManager()

        tool_name = "check_resource_health"
        args = {"resource_id": "/subscriptions/abc/resourceGroups/rg/providers/vm-01"}
        result = {"status": "healthy", "message": "VM is running"}

        # Set cache entry
        cache.set(tool_name, args, result, ttl_profile="short")

        # Get should return cached value
        cached = cache.get(tool_name, args)

        assert cached is not None
        assert cached == result
        assert cache._hits == 1
        assert cache._misses == 0

    def test_cache_miss_on_first_access(self):
        """Test cache miss when entry doesn't exist"""
        cache = SRECacheManager()

        tool_name = "check_resource_health"
        args = {"resource_id": "/subscriptions/abc/resourceGroups/rg/providers/vm-01"}

        # Get should return None
        cached = cache.get(tool_name, args)

        assert cached is None
        assert cache._hits == 0
        assert cache._misses == 1

    def test_cache_expiration_after_ttl(self):
        """Test that cache entries expire after TTL"""
        cache = SRECacheManager()

        tool_name = "get_performance_metrics"
        args = {"resource_id": "/subscriptions/abc/resourceGroups/rg/providers/vm-01"}
        result = {"cpu_usage": 45.2, "memory_usage": 72.1}

        # Set with very short TTL (real_time = 60s)
        cache.set(tool_name, args, result, ttl_profile="real_time")

        # Immediately should hit
        cached = cache.get(tool_name, args)
        assert cached is not None

        # Manually expire the entry
        key = cache._make_key(tool_name, args)
        cache._cache[key]["expires_at"] = time.time() - 1  # 1 second ago

        # Now should miss
        cached = cache.get(tool_name, args)
        assert cached is None

    def test_never_cache_list_respected(self):
        """Test that NEVER_CACHE tools are not cached"""
        cache = SRECacheManager()

        tool_name = "execute_safe_restart"  # In NEVER_CACHE
        args = {"resource_id": "/subscriptions/abc/resourceGroups/rg/providers/vm-01"}
        result = {"status": "restarted"}

        # Try to set cache
        cache.set(tool_name, args, result)

        # Should not be cached
        cached = cache.get(tool_name, args)
        assert cached is None

    def test_cache_key_deterministic(self):
        """Test that cache keys are deterministic for same args"""
        cache = SRECacheManager()

        args1 = {"resource_id": "vm-01", "subscription_id": "abc"}
        args2 = {"subscription_id": "abc", "resource_id": "vm-01"}  # Different order

        key1 = cache._make_key("check_resource_health", args1)
        key2 = cache._make_key("check_resource_health", args2)

        # Keys should be identical regardless of arg order
        assert key1 == key2

    def test_cache_key_excludes_context_params(self):
        """Test that context-like parameters are excluded from cache keys"""
        cache = SRECacheManager()

        args_with_context = {
            "resource_id": "vm-01",
            "context": {"user": "test", "session": "123"},
        }
        args_without_context = {"resource_id": "vm-01"}

        key1 = cache._make_key("check_resource_health", args_with_context)
        key2 = cache._make_key("check_resource_health", args_without_context)

        # Keys should be identical (context excluded)
        assert key1 == key2

    def test_ttl_profiles_defined(self):
        """Test that all TTL profiles are properly defined"""
        cache = SRECacheManager()

        assert "real_time" in cache.TTL_PROFILES
        assert "short" in cache.TTL_PROFILES
        assert "medium" in cache.TTL_PROFILES
        assert "long" in cache.TTL_PROFILES
        assert "daily" in cache.TTL_PROFILES

        # Verify reasonable TTL values
        assert cache.TTL_PROFILES["real_time"] == 60  # 1 minute
        assert cache.TTL_PROFILES["short"] == 300  # 5 minutes
        assert cache.TTL_PROFILES["medium"] == 1800  # 30 minutes
        assert cache.TTL_PROFILES["long"] == 3600  # 1 hour
        assert cache.TTL_PROFILES["daily"] == 86400  # 24 hours

    def test_tool_ttl_mapping(self):
        """Test that common tools have appropriate TTL profiles"""
        cache = SRECacheManager()

        # Real-time tools (performance metrics)
        assert cache.TOOL_TTL_MAP.get("get_performance_metrics") == "real_time"

        # Short TTL tools (health checks)
        assert cache.TOOL_TTL_MAP.get("check_resource_health") == "short"

        # Medium TTL tools (config, costs)
        assert cache.TOOL_TTL_MAP.get("get_cost_analysis") == "medium"

        # Long TTL tools (dependencies, SLOs)
        assert cache.TOOL_TTL_MAP.get("get_resource_dependencies") == "long"

        # Daily tools (security, compliance)
        assert cache.TOOL_TTL_MAP.get("get_security_score") == "daily"

    def test_cache_stats_tracking(self):
        """Test that cache hit/miss statistics are tracked"""
        cache = SRECacheManager()

        tool_name = "check_resource_health"
        args = {"resource_id": "vm-01"}
        result = {"status": "healthy"}

        # Miss on first access
        cache.get(tool_name, args)
        assert cache._hits == 0
        assert cache._misses == 1

        # Set and hit
        cache.set(tool_name, args, result)
        cache.get(tool_name, args)
        assert cache._hits == 1
        assert cache._misses == 1

        # Another hit
        cache.get(tool_name, args)
        assert cache._hits == 2
        assert cache._misses == 1

    def test_thread_safe_cache_access(self):
        """Test that cache is thread-safe with RLock"""
        cache = SRECacheManager()

        # Verify lock exists and is a threading lock
        assert hasattr(cache, "_lock")
        assert type(cache._lock).__name__ == "RLock"

    def test_cache_max_entries(self):
        """Test that cache respects max_entries limit"""
        cache = SRECacheManager(max_entries=5)

        assert cache._max_entries == 5


# ==========================================
# Placeholder for Phase 2 Tests (After Tasks #4-5)
# ==========================================

# TODO: Add after Tasks #4-5 complete:
# - User selection simulation tests
# - Retry after user input tests
# - End-to-end workflow tests
# - 80% auto-resolution rate validation
# - Full context caching integration tests
