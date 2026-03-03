"""Mock infrastructure for deterministic MCP tool selection testing.

This package provides drop-in replacements for real MCP clients that return
deterministic responses from fixture files, enabling local testing without
Azure dependencies.

Usage:
    from tests.mocks import DeterministicMCPClient, FixtureLoader

    client = DeterministicMCPClient.from_fixture_file("sre_health_check.json")
    result = await client.call_tool("check_resource_health", {"resource_id": "vm-001"})
"""

from .deterministic_mcp_client import DeterministicMCPClient, FixtureLoader

__all__ = ["DeterministicMCPClient", "FixtureLoader"]
