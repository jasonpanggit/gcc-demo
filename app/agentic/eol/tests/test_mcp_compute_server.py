"""
MCP Server Validation Tests - Compute Server

Tests validate that MCP server configuration and tool definitions exist.
These are smoke tests to ensure servers are properly structured.

Note: MCP servers run as separate processes. These tests validate structure,
not runtime behavior (which would require MCP protocol testing).

Created: 2026-02-27 (Phase 1, Task 3.1)
"""

import pytest
from pathlib import Path


# Get the base directory (tests/../mcp_servers)
BASE_DIR = Path(__file__).parent.parent / "mcp_servers"
SERVER_FILE = BASE_DIR / "compute_mcp_server.py"

@pytest.mark.unit
@pytest.mark.mcp
class TestComputeMCPServer:
    """Validation tests for Compute MCP Server structure."""

    def test_server_file_exists(self):
        """Test that compute MCP server file exists.

        Scenario: Check for compute_mcp_server.py
        Expected: File exists in mcp_servers directory
        """
        # Arrange
        server_path = SERVER_FILE

        # Assert
        assert server_path.exists(), f"Server file not found: {server_path}"

    def test_server_has_tool_definitions(self):
        """Test that server file contains tool definitions.

        Scenario: Read server source and check for @_server.tool()
        Expected: At least one tool decorator found
        """
        # Arrange
        server_path = SERVER_FILE
        content = server_path.read_text()

        # Assert
        assert "@_server.tool()" in content, "No @_server.tool() decorators found"
        assert "async def virtual_machine_list" in content, "virtual_machine_list tool not found"

    def test_server_has_fastmcp_import(self):
        """Test that server imports FastMCP.

        Scenario: Check imports in server file
        Expected: FastMCP import present
        """
        # Arrange
        server_path = SERVER_FILE
        content = server_path.read_text()

        # Assert
        assert "from mcp.server.fastmcp import" in content, "FastMCP import not found"
        assert "FastMCP" in content, "FastMCP not used"

    def test_server_has_server_instance(self):
        """Test that server creates FastMCP instance.

        Scenario: Check for _server = FastMCP(...)
        Expected: Server instance creation found
        """
        # Arrange
        server_path = SERVER_FILE
        content = server_path.read_text()

        # Assert
        assert "_server = FastMCP(" in content, "FastMCP instance not created"
        assert 'name="azure-compute"' in content, "Server name not set"

    def test_server_has_documentation(self):
        """Test that server has module docstring.

        Scenario: Check for module-level documentation
        Expected: Docstring present at top of file
        """
        # Arrange
        server_path = SERVER_FILE
        content = server_path.read_text()

        # Assert
        assert '"""' in content[:500], "No module docstring found"
        assert "Compute MCP Server" in content[:500], "Server description missing"

    def test_virtual_machine_list_has_docstring(self):
        """Test that virtual_machine_list tool has documentation.

        Scenario: Check tool function for docstring
        Expected: Docstring explains what the tool does
        """
        # Arrange
        server_path = SERVER_FILE
        content = server_path.read_text()

        # Find the function definition
        func_start = content.find("async def virtual_machine_list")
        func_section = content[func_start:func_start + 500] if func_start != -1 else ""

        # Assert
        assert func_start != -1, "virtual_machine_list function not found"
        assert '"""' in func_section, "No docstring for virtual_machine_list"
        assert "virtual machine" in func_section.lower(), "Tool purpose not documented"

    @pytest.mark.placeholder
    def test_server_runtime_behavior(self):
        """Test server runtime behavior (requires MCP stack).

        Scenario: Start server and test tool execution
        Expected: Tools execute successfully

        NOTE: Placeholder - requires MCP package installation
        """
        pytest.skip("MCP runtime testing requires mcp package (Phase 2)")
