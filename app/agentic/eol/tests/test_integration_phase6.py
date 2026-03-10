"""
Phase 6 Integration Tests
=========================

Covers Phase 5 + 6 cross-component contracts without Azure connections:

  1. MCPHost.from_config() with all servers disabled → valid empty host
  2. MCPConfigLoader env-var toggle excludes the correct server
    3. MCPConfigLoader.get_all_servers() always returns all 11 (ignores enabled)
  4. UnifiedRouter.route() produces a valid RoutingPlan for a plain query
  5. MCPHost.from_config() with one server enabled doesn't raise

No real Azure connections. No browser instances.
Markers: @pytest.mark.integration (registered in pytest.ini)
"""
import asyncio
import sys
import os
from typing import List

import pytest

# Ensure app path is importable when running from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.mcp_config_loader import MCPConfigLoader
from utils.mcp_host import MCPHost
from utils.unified_router import get_unified_router


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# All 11 environment variable toggle keys from config/mcp_servers.yaml
ALL_DISABLED_KEYS = [
    "AZURE_MCP_ENABLED",
    "SRE_ENABLED",
    "NETWORK_MCP_ENABLED",
    "COMPUTE_MCP_ENABLED",
    "STORAGE_MCP_ENABLED",
    "MONITOR_MCP_ENABLED",
    "PATCH_MCP_ENABLED",
    "CVE_MCP_ENABLED",
    "OS_EOL_MCP_ENABLED",
    "INVENTORY_MCP_ENABLED",
    "AZURE_CLI_EXECUTOR_ENABLED",
]


# ---------------------------------------------------------------------------
# Test 1: MCPHost.from_config() with all servers disabled → valid empty host
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_host_from_config_all_disabled():
    """MCPHost.from_config() with all servers disabled returns a valid MCPHost with 0 tools."""
    # Save original environment
    original_env = {key: os.environ.get(key) for key in ALL_DISABLED_KEYS}

    try:
        # Disable all servers
        for key in ALL_DISABLED_KEYS:
            os.environ[key] = "false"

        # Create MCPHost from config (should succeed with 0 clients)
        host = await MCPHost.from_config()

        # Verify it's a valid MCPHost instance
        assert isinstance(host, MCPHost), "Expected MCPHost instance"

        # Verify it has 0 tools (all servers disabled)
        available_tools = host.get_available_tools()
        assert isinstance(available_tools, list), "Expected list of tools"
        assert len(available_tools) == 0, (
            f"Expected 0 tools when all servers disabled, got {len(available_tools)}"
        )

        # Verify client labels are empty
        client_labels = host.get_client_labels()
        assert len(client_labels) == 0, (
            f"Expected 0 clients when all servers disabled, got {len(client_labels)}"
        )

    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Test 2: MCPConfigLoader env-var toggle excludes the correct server
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_config_loader_env_toggle():
    """MCPConfigLoader env-var toggle (SRE_ENABLED=false) excludes the correct server from enabled list."""
    # Save original environment
    original_sre_enabled = os.environ.get("SRE_ENABLED")

    try:
        # Disable SRE server only
        os.environ["SRE_ENABLED"] = "false"

        # Create loader and get enabled servers
        loader = MCPConfigLoader()
        enabled_servers = loader.get_enabled_servers()

        # Verify SRE server is NOT in enabled list
        enabled_labels = [s.label for s in enabled_servers]
        assert "sre" not in enabled_labels, (
            f"Expected 'sre' to be excluded when SRE_ENABLED=false, but found in: {enabled_labels}"
        )

        # Verify we have exactly 10 enabled servers (11 total - 1 disabled)
        assert len(enabled_servers) == 10, (
            f"Expected 10 enabled servers (11 - 1 disabled), got {len(enabled_servers)}"
        )

        # Verify other servers are still enabled
        # Should have: azure, network, compute, storage, monitor, patch, cve, os_eol, inventory, azure_cli_executor
        expected_enabled = {
            "azure", "network", "compute", "storage", "monitor",
            "patch", "cve", "os_eol", "inventory", "azure_cli_executor"
        }
        assert set(enabled_labels) == expected_enabled, (
            f"Expected enabled servers {expected_enabled}, got {set(enabled_labels)}"
        )

    finally:
        # Restore original environment
        if original_sre_enabled is None:
            os.environ.pop("SRE_ENABLED", None)
        else:
            os.environ["SRE_ENABLED"] = original_sre_enabled


# ---------------------------------------------------------------------------
# Test 3: MCPConfigLoader.get_all_servers() always returns all 11
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_config_loader_all_servers_always_10():
    """MCPConfigLoader.get_all_servers() returns all 11 servers regardless of enabled flag."""
    # Save original environment
    original_sre_enabled = os.environ.get("SRE_ENABLED")

    try:
        # Disable SRE server
        os.environ["SRE_ENABLED"] = "false"

        # Create loader and get ALL servers (ignores enabled flag)
        loader = MCPConfigLoader()
        all_servers = loader.get_all_servers()

        # Verify we get exactly 11 servers regardless of enabled state
        assert len(all_servers) == 11, (
            f"Expected get_all_servers() to return all 11 servers, got {len(all_servers)}"
        )

        # Verify all expected server labels are present
        all_labels = [s.label for s in all_servers]
        expected_labels = {
            "azure", "sre", "network", "compute", "storage",
            "monitor", "patch", "cve", "os_eol", "inventory", "azure_cli_executor"
        }
        assert set(all_labels) == expected_labels, (
            f"Expected server labels {expected_labels}, got {set(all_labels)}"
        )

        # Verify SRE server is present but disabled
        sre_server = next((s for s in all_servers if s.label == "sre"), None)
        assert sre_server is not None, "Expected SRE server in all_servers list"
        assert sre_server.enabled is False, (
            f"Expected SRE server to be disabled, got enabled={sre_server.enabled}"
        )

    finally:
        # Restore original environment
        if original_sre_enabled is None:
            os.environ.pop("SRE_ENABLED", None)
        else:
            os.environ["SRE_ENABLED"] = original_sre_enabled


# ---------------------------------------------------------------------------
# Test 4: UnifiedRouter.route() produces a valid RoutingPlan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_unified_router_routes_sre_query():
    """UnifiedRouter.route() produces a valid RoutingPlan for a plain English query."""
    # Get router singleton
    router = get_unified_router()

    # Route a typical SRE health check query
    plan = await router.route("check health of my VMs", strategy="fast")

    # Verify plan structure
    assert plan is not None, "Expected RoutingPlan to be returned"
    assert hasattr(plan, "orchestrator"), "RoutingPlan missing orchestrator attribute"
    assert hasattr(plan, "domain"), "RoutingPlan missing domain attribute"
    assert hasattr(plan, "tools"), "RoutingPlan missing tools attribute"
    assert hasattr(plan, "confidence"), "RoutingPlan missing confidence attribute"
    assert hasattr(plan, "classification_time_ms"), "RoutingPlan missing classification_time_ms attribute"

    # Verify orchestrator value is valid
    assert plan.orchestrator in ("mcp", "sre"), (
        f"Expected orchestrator to be 'mcp' or 'sre', got '{plan.orchestrator}'"
    )

    # Verify tools is a list
    assert isinstance(plan.tools, list), f"Expected tools to be a list, got {type(plan.tools)}"

    # Verify confidence is a float between 0 and 1
    assert isinstance(plan.confidence, float), f"Expected confidence to be a float, got {type(plan.confidence)}"
    assert 0.0 <= plan.confidence <= 1.0, (
        f"Expected confidence in range [0.0, 1.0], got {plan.confidence}"
    )

    # Verify classification time is non-negative
    assert plan.classification_time_ms >= 0, (
        f"Expected classification_time_ms >= 0, got {plan.classification_time_ms}"
    )

    # Verify secondary_domains is a list (may be empty)
    assert hasattr(plan, "secondary_domains"), "RoutingPlan missing secondary_domains attribute"
    assert isinstance(plan.secondary_domains, list), (
        f"Expected secondary_domains to be a list, got {type(plan.secondary_domains)}"
    )


# ---------------------------------------------------------------------------
# Test 5: MCPHost.from_config() with one server enabled (graceful degradation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_host_from_config_single_server_enabled():
    """MCPHost.from_config() with one server enabled doesn't raise (graceful degradation)."""
    # Save original environment
    original_env = {key: os.environ.get(key) for key in ALL_DISABLED_KEYS}

    try:
        # Disable all servers except SRE
        for key in ALL_DISABLED_KEYS:
            if key == "SRE_ENABLED":
                os.environ[key] = "true"
            else:
                os.environ[key] = "false"

        # Create MCPHost from config - should not raise even if factory fails
        # The graceful degradation means factory failures are logged but don't crash
        host = await MCPHost.from_config()

        # Verify it's a valid MCPHost instance (not None)
        assert host is not None, "Expected MCPHost instance, got None"
        assert isinstance(host, MCPHost), f"Expected MCPHost instance, got {type(host)}"

        # NOTE: We cannot assert tool count > 0 because the SRE MCP server factory
        # may fail gracefully if the mcp package isn't installed or the server
        # process can't start. The test verifies NO EXCEPTION is raised.

        # Verify get_available_tools() returns a list (may be empty)
        available_tools = host.get_available_tools()
        assert isinstance(available_tools, list), (
            f"Expected get_available_tools() to return a list, got {type(available_tools)}"
        )

    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
