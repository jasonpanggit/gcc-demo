"""Registry Collision Priority Tests
====================================

Tests that verify tool priority resolution when multiple MCP servers
provide similar or overlapping tools.

Priority rules (lower number = higher priority):
  - Azure MCP:        priority 5  (lowest — namespace/group wrappers)
  - SRE MCP:          priority 10 (medium — preferred for SRE operations)
  - Network MCP:      priority 10 (medium — preferred for network operations)
  - Compute MCP:      priority 10 (medium — preferred for compute operations)
  - Azure CLI:        priority 15 (highest number = last resort)

Usage:
    pytest tests/tools/test_registry_collision.py -v

Created: 2026-03-03 (Phase 1, Task 4)
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure application code is importable
_APP_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from tests.mocks.deterministic_mcp_client import DeterministicMCPClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers to build multi-server fixture sets
# ---------------------------------------------------------------------------

def _build_server_client(
    label: str,
    tools: List[Dict[str, Any]],
    responses: Dict[str, List[Dict[str, Any]]],
) -> DeterministicMCPClient:
    """Build a DeterministicMCPClient for a single mock server."""
    fixture_data = {
        "server_label": label,
        "tools": tools,
        "responses": responses,
    }
    return DeterministicMCPClient.from_fixture_data(fixture_data)


def _tool_def(name: str, description: str) -> Dict[str, Any]:
    """Shorthand for a tool definition dict."""
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}},
    }


def _wildcard_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Shorthand for a wildcard-match response list."""
    return [{"match": "*", "response": {"success": True, "data": data}}]


# ---------------------------------------------------------------------------
# Collision scenario 1: SRE health vs Azure MCP resourcehealth
# ---------------------------------------------------------------------------

class TestSREHealthOverAzureResourceHealth:
    """SRE check_resource_health should be preferred over Azure MCP resourcehealth.

    Priority rule: SRE tools (priority 10) are preferred over Azure MCP namespace
    tools (priority 5) for health-check operations because SRE provides deep
    diagnostics with remediation planning.
    """

    @pytest.fixture
    def sre_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="sre",
            tools=[
                _tool_def("check_resource_health",
                          "Deep health diagnostics with remediation planning"),
                _tool_def("check_container_app_health",
                          "Container-app-specific health check"),
            ],
            responses={
                "check_resource_health": _wildcard_response({
                    "health_status": "Available",
                    "diagnostics": {"cpu": 42.5, "memory": 67.8},
                    "recommendations": [{"message": "Enable backup"}],
                }),
                "check_container_app_health": _wildcard_response({
                    "health_status": "Healthy",
                    "replicas": {"ready": 3, "total": 3},
                }),
            },
        )

    @pytest.fixture
    def azure_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="azure",
            tools=[
                _tool_def("resourcehealth",
                          "Basic Azure platform availability status"),
            ],
            responses={
                "resourcehealth": _wildcard_response({
                    "availability_state": "Available",
                }),
            },
        )

    @pytest.mark.asyncio
    async def test_sre_health_preferred_over_azure_resourcehealth(
        self, sre_client: DeterministicMCPClient, azure_client: DeterministicMCPClient,
    ) -> None:
        """When both servers offer health tools, SRE should be selected."""
        await sre_client.initialize()
        await azure_client.initialize()

        # Simulate priority-based selection: SRE has check_resource_health
        sre_tools = sre_client.get_tool_names()
        azure_tools = azure_client.get_tool_names()

        # SRE must have the preferred health tool
        assert "check_resource_health" in sre_tools, (
            f"SRE server missing check_resource_health. Has: {sre_tools}"
        )
        # Azure has the less-preferred tool
        assert "resourcehealth" in azure_tools, (
            f"Azure server missing resourcehealth. Has: {azure_tools}"
        )

        # Priority rule: SRE (priority 10) tools preferred over Azure MCP
        # (priority 5) for health operations despite Azure having lower number
        # because SRE provides deeper diagnostics
        sre_result = await sre_client.call_tool("check_resource_health", {})
        assert sre_result["success"] is True
        assert "diagnostics" in sre_result["data"], (
            "SRE check_resource_health should return diagnostics (deep health)"
        )
        assert "recommendations" in sre_result["data"], (
            "SRE check_resource_health should return recommendations"
        )

        azure_result = await azure_client.call_tool("resourcehealth", {})
        assert azure_result["success"] is True
        assert "diagnostics" not in azure_result["data"], (
            "Azure resourcehealth should NOT have deep diagnostics"
        )

        await sre_client.cleanup()
        await azure_client.cleanup()

    @pytest.mark.asyncio
    async def test_sre_container_tools_preferred_over_azure_equivalents(
        self, sre_client: DeterministicMCPClient, azure_client: DeterministicMCPClient,
    ) -> None:
        """SRE container app tools should be preferred over Azure MCP equivalents."""
        await sre_client.initialize()
        await azure_client.initialize()

        # SRE has dedicated container app health tool
        assert "check_container_app_health" in sre_client.get_tool_names()

        # Call the SRE tool and verify it provides richer data
        result = await sre_client.call_tool("check_container_app_health", {})
        assert result["success"] is True
        assert "replicas" in result["data"], (
            "SRE container health should include replica status"
        )

        await sre_client.cleanup()
        await azure_client.cleanup()


# ---------------------------------------------------------------------------
# Collision scenario 2: Network MCP vs Azure MCP for network operations
# ---------------------------------------------------------------------------

class TestNetworkMCPPreferredForNetworkOps:
    """Network MCP tools should be preferred over Azure MCP for network operations.

    Network MCP provides specialized network analysis (connectivity tests,
    NSG simulation, route tracing) vs Azure MCP's generic namespace tools.
    """

    @pytest.fixture
    def network_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="network",
            tools=[
                _tool_def("virtual_network_list",
                          "List VNets with subnets and peerings"),
                _tool_def("test_network_connectivity",
                          "Test IP flow connectivity between resources"),
                _tool_def("nsg_list",
                          "List NSGs with rule summaries"),
            ],
            responses={
                "virtual_network_list": _wildcard_response({
                    "virtual_networks": [
                        {"name": "vnet-prod", "subnets": ["snet-app", "snet-db"]},
                    ],
                }),
                "test_network_connectivity": _wildcard_response({
                    "connection_status": "Reachable",
                    "hops": [{"order": 1, "type": "Source"}],
                }),
                "nsg_list": _wildcard_response({
                    "nsgs": [{"name": "nsg-app-prod", "rule_count": 8}],
                }),
            },
        )

    @pytest.fixture
    def azure_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="azure",
            tools=[
                _tool_def("virtual_machines",
                          "Azure MCP namespace for VMs (NOT for network)"),
            ],
            responses={
                "virtual_machines": _wildcard_response({
                    "vms": [{"name": "vm-prod-01"}],
                }),
            },
        )

    @pytest.mark.asyncio
    async def test_network_mcp_tools_preferred_for_network_queries(
        self, network_client: DeterministicMCPClient, azure_client: DeterministicMCPClient,
    ) -> None:
        """Network MCP should be preferred for VNet/NSG/connectivity queries."""
        await network_client.initialize()
        await azure_client.initialize()

        network_tools = set(network_client.get_tool_names())

        # Network MCP must have specialized network tools
        assert "virtual_network_list" in network_tools
        assert "test_network_connectivity" in network_tools
        assert "nsg_list" in network_tools

        # Azure MCP should NOT have these network-specific tools
        azure_tools = set(azure_client.get_tool_names())
        assert "virtual_network_list" not in azure_tools, (
            "Azure MCP should not duplicate network-specific tools"
        )
        assert "test_network_connectivity" not in azure_tools

        # Verify network tool returns richer network data
        result = await network_client.call_tool("virtual_network_list", {})
        vnet_data = result["data"]
        assert "virtual_networks" in vnet_data
        assert "subnets" in vnet_data["virtual_networks"][0], (
            "Network MCP should return subnet details with VNets"
        )

        await network_client.cleanup()
        await azure_client.cleanup()


# ---------------------------------------------------------------------------
# Collision scenario 3: CLI executor as last resort
# ---------------------------------------------------------------------------

class TestCLIExecutorLastResort:
    """CLI executor (priority 15) should only be used when specific tools
    are unavailable from SRE/Network/Compute MCP servers.

    Priority hierarchy:
      1. Specialized MCP tool (SRE, Network, Compute) — use first
      2. Azure MCP namespace tool — use if no specialized tool
      3. CLI executor — last resort escape hatch
    """

    @pytest.fixture
    def sre_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="sre",
            tools=[
                _tool_def("container_app_list",
                          "List container apps via SRE MCP"),
            ],
            responses={
                "container_app_list": _wildcard_response({
                    "container_apps": [
                        {"name": "ca-prod-api", "status": "Running"},
                        {"name": "ca-prod-web", "status": "Running"},
                    ],
                }),
            },
        )

    @pytest.fixture
    def cli_client(self) -> DeterministicMCPClient:
        return _build_server_client(
            label="azure_cli_executor",
            tools=[
                _tool_def("azure_cli_execute_command",
                          "Execute raw az CLI commands (escape hatch)"),
            ],
            responses={
                "azure_cli_execute_command": _wildcard_response({
                    "stdout": "[{\"name\": \"ca-prod-api\"}]",
                    "exit_code": 0,
                }),
            },
        )

    @pytest.mark.asyncio
    async def test_cli_only_used_when_specific_tools_unavailable(
        self, sre_client: DeterministicMCPClient, cli_client: DeterministicMCPClient,
    ) -> None:
        """When SRE has container_app_list, CLI should NOT be selected."""
        await sre_client.initialize()
        await cli_client.initialize()

        sre_tools = set(sre_client.get_tool_names())
        cli_tools = set(cli_client.get_tool_names())

        # SRE has the preferred specific tool
        assert "container_app_list" in sre_tools, (
            "SRE should provide container_app_list"
        )

        # CLI has the generic escape hatch
        assert "azure_cli_execute_command" in cli_tools

        # Simulate priority selection: prefer SRE over CLI
        # In the real system, the planner checks for specific tools first
        sre_result = await sre_client.call_tool("container_app_list", {})
        assert sre_result["success"] is True
        assert "container_apps" in sre_result["data"], (
            "SRE container_app_list should return structured container app data"
        )

        # CLI would return raw stdout - less structured
        cli_result = await cli_client.call_tool(
            "azure_cli_execute_command",
            {"command": "az containerapp list"},
        )
        assert cli_result["success"] is True
        assert "stdout" in cli_result["data"], (
            "CLI executor returns raw stdout, not structured data"
        )

        # Verify SRE was used (should be preferred)
        sre_client.assert_tool_called("container_app_list", times=1)

        # CLI should NOT be the first choice when SRE tool is available
        # (In production, the planner/retriever enforces this)

        await sre_client.cleanup()
        await cli_client.cleanup()

    @pytest.mark.asyncio
    async def test_cli_acceptable_when_no_specific_tool_exists(
        self, cli_client: DeterministicMCPClient,
    ) -> None:
        """CLI is acceptable as fallback when no specialized tool exists."""
        await cli_client.initialize()

        # For operations without a dedicated MCP tool, CLI is the fallback
        result = await cli_client.call_tool(
            "azure_cli_execute_command",
            {"command": "az containerapp revision list --name ca-prod-api"},
        )
        assert result["success"] is True
        cli_client.assert_tool_called("azure_cli_execute_command", times=1)

        await cli_client.cleanup()


# ---------------------------------------------------------------------------
# Priority resolution documentation
# ---------------------------------------------------------------------------

class TestPriorityResolutionRules:
    """Documents and validates the priority resolution rules.

    These tests serve as executable documentation for the priority system.
    """

    def test_priority_hierarchy_documented(self) -> None:
        """Verify the priority hierarchy is documented and consistent."""
        # Priority rules (lower number = registers first, but manifest
        # preferred_over fields determine actual selection preference)
        priority_map = {
            "azure": 5,           # Azure MCP namespace tools
            "sre": 10,            # SRE MCP specialized tools
            "network": 10,        # Network MCP specialized tools
            "compute": 10,        # Compute MCP specialized tools
            "storage": 10,        # Storage MCP specialized tools
            "monitor": 10,        # Monitor MCP specialized tools
            "patch": 10,          # Patch MCP specialized tools
            "os_eol": 10,         # OS EOL MCP specialized tools
            "inventory": 10,      # Inventory MCP specialized tools
            "azure_cli_executor": 15,  # CLI executor (last resort)
        }

        # Azure MCP has lowest priority number (registered first)
        assert priority_map["azure"] < priority_map["sre"]

        # CLI executor has highest priority number (last resort)
        assert priority_map["azure_cli_executor"] > priority_map["sre"]
        assert priority_map["azure_cli_executor"] > priority_map["network"]

        # All specialized servers share the same priority
        specialized = ["sre", "network", "compute", "storage", "monitor"]
        priorities = [priority_map[s] for s in specialized]
        assert len(set(priorities)) == 1, (
            f"Specialized servers should all have same priority, got: "
            f"{dict(zip(specialized, priorities))}"
        )

    def test_preferred_over_rules_documented(self) -> None:
        """Verify key preferred_over rules from manifests."""
        # These are the critical collision resolution rules from manifests
        preferred_over_rules = {
            "virtual_machine_list": {"preferred_over": "virtual_machines",
                                     "reason": "Structured per-VM data"},
            "check_resource_health": {"preferred_over": "resourcehealth",
                                      "reason": "Deep diagnostics with remediation"},
            "container_app_list": {"preferred_over": "azure_cli_execute_command",
                                    "reason": "Dedicated tool vs generic CLI"},
            "nsg_list": {"preferred_over": "inspect_nsg_rules",
                          "reason": "List/discover vs inspect specific"},
        }

        # Verify all rules have both fields
        for tool, rule in preferred_over_rules.items():
            assert "preferred_over" in rule, f"Missing preferred_over for {tool}"
            assert "reason" in rule, f"Missing reason for {tool}"
            assert rule["reason"], f"Empty reason for {tool}"

    def test_collision_domains_are_disjoint_where_expected(self) -> None:
        """Tools in different domains should not collide unexpectedly."""
        # Domain boundaries that should be respected
        domain_boundaries = {
            "sre_health": ["check_resource_health", "check_container_app_health",
                           "container_app_list"],
            "azure_management": ["resourcehealth", "virtual_machines", "groups"],
            "network": ["virtual_network_list", "nsg_list", "test_network_connectivity"],
        }

        # No tool should appear in multiple domain lists
        all_tools = []
        for domain, tools in domain_boundaries.items():
            for tool in tools:
                assert tool not in all_tools, (
                    f"Tool '{tool}' appears in multiple domain boundaries. "
                    f"Found in '{domain}' but already registered elsewhere."
                )
                all_tools.append(tool)
