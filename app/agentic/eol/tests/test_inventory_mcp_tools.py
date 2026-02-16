"""
Test suite for Inventory MCP Server tools.

Tests all 7 inventory tools with mocked Log Analytics responses.
Covers success paths, error handling, filtering, and edge cases.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.unit, pytest.mark.asyncio, pytest.mark.mcp_inventory]


@pytest.fixture
def mock_workspace_id():
    """Mock Log Analytics workspace ID"""
    return "12345678-1234-1234-1234-workspace01"


@pytest.fixture
def mock_software_inventory_response():
    """Mock Log Analytics software inventory query response"""
    return {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": [
                    {"name": "computer", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "publisher", "type": "string"},
                    {"name": "install_date", "type": "datetime"},
                    {"name": "last_seen", "type": "datetime"},
                    {"name": "source", "type": "string"}
                ],
                "rows": [
                    ["WEBSRV-001", "Python", "3.11.5", "Python Software Foundation", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                    ["WEBSRV-001", "Node.js", "20.10.0", "Node.js Foundation", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                    ["DBSRV-001", "PostgreSQL", "16.1", "PostgreSQL Global Development Group", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                    ["WEBSRV-002", "Python", "2.7.18", "Python Software Foundation", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                ]
            }
        ]
    }


@pytest.fixture
def mock_os_inventory_response():
    """Mock Log Analytics OS inventory query response"""
    return {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": [
                    {"name": "computer_name", "type": "string"},
                    {"name": "os_name", "type": "string"},
                    {"name": "os_version", "type": "string"},
                    {"name": "os_type", "type": "string"},
                    {"name": "vendor", "type": "string"},
                    {"name": "computer_environment", "type": "string"},
                    {"name": "resource_id", "type": "string"},
                    {"name": "last_heartbeat", "type": "datetime"}
                ],
                "rows": [
                    ["WEBSRV-001", "Ubuntu", "22.04", "Linux", "Canonical Ltd.", "Azure", "/subscriptions/.../WEBSRV-001", "2025-02-15T12:00:00Z"],
                    ["WEBSRV-002", "Ubuntu", "18.04", "Linux", "Canonical Ltd.", "Azure", "/subscriptions/.../WEBSRV-002", "2025-02-15T12:00:00Z"],
                    ["DBSRV-001", "Windows Server", "2016", "Windows", "Microsoft", "Azure", "/subscriptions/.../DBSRV-001", "2025-02-15T12:00:00Z"],
                ]
            }
        ]
    }


@pytest.fixture
def mock_computer_list_response():
    """Mock computer list response"""
    return {
        "tables": [
            {
                "name": "PrimaryResult",
                "columns": [{"name": "computer", "type": "string"}],
                "rows": [["WEBSRV-001"], ["WEBSRV-002"], ["DBSRV-001"], ["APPSRV-001"]]
            }
        ]
    }


# ==========================================
# Inventory Query Tests (7 tools)
# ==========================================


@pytest.mark.asyncio
async def test_get_software_inventory_success(mock_workspace_id, mock_software_inventory_response):
    """Test get_software_inventory with successful query"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [mock_software_inventory_response["tables"][0]]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter=None,
            limit=10000
        )

        assert result["success"] is True
        assert "data" in result
        assert len(result["data"]) == 4  # 4 software items in mock
        assert result["count"] == 4


@pytest.mark.asyncio
async def test_get_software_inventory_with_filter(mock_workspace_id, mock_software_inventory_response):
    """Test get_software_inventory with software name filter"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        # Filter to only Python
        filtered_rows = [row for row in mock_software_inventory_response["tables"][0]["rows"] if "Python" in row[1]]
        mock_response.tables = [{
            "columns": mock_software_inventory_response["tables"][0]["columns"],
            "rows": filtered_rows
        }]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter="Python",
            limit=10000
        )

        assert result["success"] is True
        assert result["count"] == 2  # 2 Python installations
        assert all("Python" in item["name"] for item in result["data"])


@pytest.mark.asyncio
async def test_get_os_inventory_success(mock_workspace_id, mock_os_inventory_response):
    """Test get_os_inventory with successful query"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [mock_os_inventory_response["tables"][0]]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_os_inventory

        result = await get_os_inventory(
            workspace_id=mock_workspace_id,
            days=7,
            limit=10000
        )

        assert result["success"] is True
        assert "data" in result
        assert len(result["data"]) == 3  # 3 computers in mock
        assert result["count"] == 3


@pytest.mark.asyncio
async def test_get_computer_list_success(mock_workspace_id, mock_computer_list_response):
    """Test get_computer_list with successful query"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [mock_computer_list_response["tables"][0]]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_computer_list

        result = await get_computer_list(
            workspace_id=mock_workspace_id,
            days=7
        )

        assert result["success"] is True
        assert "computers" in result
        assert len(result["computers"]) == 4
        assert "WEBSRV-001" in result["computers"]


@pytest.mark.asyncio
async def test_search_software_success(mock_workspace_id, mock_software_inventory_response):
    """Test search_software with keyword search"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        # Search for "Node"
        filtered_rows = [row for row in mock_software_inventory_response["tables"][0]["rows"] if "Node" in row[1]]
        mock_response.tables = [{
            "columns": mock_software_inventory_response["tables"][0]["columns"],
            "rows": filtered_rows
        }]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import search_software

        result = await search_software(
            workspace_id=mock_workspace_id,
            search_term="Node",
            days=90
        )

        assert result["success"] is True
        assert result["count"] >= 1
        assert any("Node" in item["name"] for item in result["data"])


@pytest.mark.asyncio
async def test_get_software_by_computer_success(mock_workspace_id, mock_software_inventory_response):
    """Test get_software_by_computer for specific computer"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        # Filter to WEBSRV-001
        filtered_rows = [row for row in mock_software_inventory_response["tables"][0]["rows"] if row[0] == "WEBSRV-001"]
        mock_response.tables = [{
            "columns": mock_software_inventory_response["tables"][0]["columns"],
            "rows": filtered_rows
        }]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_by_computer

        result = await get_software_by_computer(
            workspace_id=mock_workspace_id,
            computer_name="WEBSRV-001",
            days=90
        )

        assert result["success"] is True
        assert result["computer"] == "WEBSRV-001"
        assert len(result["software"]) == 2  # Python and Node.js
        assert all(item["computer"] == "WEBSRV-001" for item in result["software"])


@pytest.mark.asyncio
async def test_get_computer_details_success(mock_workspace_id, mock_os_inventory_response, mock_software_inventory_response):
    """Test get_computer_details with OS and software info"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value

        # Mock two queries: OS info and software list
        os_response = MagicMock()
        os_response.tables = [{"columns": mock_os_inventory_response["tables"][0]["columns"],
                               "rows": [mock_os_inventory_response["tables"][0]["rows"][0]]}]

        software_response = MagicMock()
        software_filtered = [row for row in mock_software_inventory_response["tables"][0]["rows"] if row[0] == "WEBSRV-001"]
        software_response.tables = [{"columns": mock_software_inventory_response["tables"][0]["columns"],
                                     "rows": software_filtered}]

        mock_instance.query_workspace = AsyncMock(side_effect=[os_response, software_response])

        from mcp_servers.inventory_mcp_server import get_computer_details

        result = await get_computer_details(
            workspace_id=mock_workspace_id,
            computer_name="WEBSRV-001",
            days=7
        )

        assert result["success"] is True
        assert result["computer_name"] == "WEBSRV-001"
        assert "os_info" in result
        assert "software" in result
        assert result["os_info"]["os_name"] == "Ubuntu"
        assert len(result["software"]) == 2


@pytest.mark.asyncio
async def test_get_inventory_stats_success(mock_workspace_id, mock_computer_list_response, mock_software_inventory_response, mock_os_inventory_response):
    """Test get_inventory_stats with aggregate statistics"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value

        # Mock three queries: computers, software, OS
        computer_response = MagicMock()
        computer_response.tables = [mock_computer_list_response["tables"][0]]

        software_response = MagicMock()
        software_response.tables = [mock_software_inventory_response["tables"][0]]

        os_response = MagicMock()
        os_response.tables = [mock_os_inventory_response["tables"][0]]

        mock_instance.query_workspace = AsyncMock(side_effect=[computer_response, software_response, os_response])

        from mcp_servers.inventory_mcp_server import get_inventory_stats

        result = await get_inventory_stats(
            workspace_id=mock_workspace_id,
            days=90
        )

        assert result["success"] is True
        assert "total_computers" in result
        assert "total_software_items" in result
        assert "unique_software" in result
        assert "os_distribution" in result
        assert result["total_computers"] == 4


# ==========================================
# Error Handling Tests
# ==========================================


@pytest.mark.asyncio
async def test_get_software_inventory_auth_error(mock_workspace_id):
    """Test get_software_inventory with authentication failure"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.query_workspace = AsyncMock(side_effect=Exception("AuthenticationFailed: Invalid credentials"))

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter=None,
            limit=10000
        )

        assert result["success"] is False
        assert "error" in result
        assert "authentication" in result["error"].lower() or "credential" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_os_inventory_timeout(mock_workspace_id):
    """Test get_os_inventory with query timeout"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.query_workspace = AsyncMock(side_effect=TimeoutError("Query exceeded timeout limit"))

        from mcp_servers.inventory_mcp_server import get_os_inventory

        result = await get_os_inventory(
            workspace_id=mock_workspace_id,
            days=7,
            limit=10000
        )

        assert result["success"] is False
        assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_computer_details_not_found(mock_workspace_id):
    """Test get_computer_details for non-existent computer"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value

        # Empty result
        empty_response = MagicMock()
        empty_response.tables = [{"columns": [], "rows": []}]
        mock_instance.query_workspace = AsyncMock(return_value=empty_response)

        from mcp_servers.inventory_mcp_server import get_computer_details

        result = await get_computer_details(
            workspace_id=mock_workspace_id,
            computer_name="NONEXISTENT-COMPUTER",
            days=7
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_invalid_workspace_id():
    """Test inventory tool with invalid workspace ID"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.query_workspace = AsyncMock(side_effect=Exception("Workspace not found"))

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id="invalid-workspace-id",
            days=90,
            software_filter=None,
            limit=10000
        )

        assert result["success"] is False
        assert "workspace" in result["error"].lower() or "not found" in result["error"].lower()


# ==========================================
# Edge Case Tests
# ==========================================


@pytest.mark.asyncio
async def test_empty_inventory(mock_workspace_id):
    """Test get_software_inventory with no results"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [{"columns": [], "rows": []}]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter="NonExistentSoftware",
            limit=10000
        )

        assert result["success"] is True
        assert result["count"] == 0
        assert len(result["data"]) == 0


@pytest.mark.asyncio
async def test_large_inventory_dataset(mock_workspace_id):
    """Test get_software_inventory with large result set (10K+ items)"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()

        # Generate 15000 software items
        large_dataset = []
        for i in range(15000):
            large_dataset.append([
                f"COMP-{i:05d}",
                f"Software-{i % 100}",
                f"1.{i % 10}.{i % 20}",
                f"Publisher-{i % 50}",
                None,
                "2025-02-15T12:00:00Z",
                "ConfigurationData"
            ])

        mock_response.tables = [{
            "columns": [
                {"name": "computer", "type": "string"},
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "publisher", "type": "string"},
                {"name": "install_date", "type": "datetime"},
                {"name": "last_seen", "type": "datetime"},
                {"name": "source", "type": "string"}
            ],
            "rows": large_dataset
        }]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter=None,
            limit=20000  # Request more than default
        )

        assert result["success"] is True
        assert result["count"] == 15000
        assert len(result["data"]) == 15000


@pytest.mark.asyncio
async def test_special_characters_in_filter(mock_workspace_id, mock_software_inventory_response):
    """Test get_software_inventory with special characters in filter"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [mock_software_inventory_response["tables"][0]]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        # Should handle special characters without KQL injection
        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter="Node.js | ' OR 1=1 --",  # Potential injection attempt
            limit=10000
        )

        # Should either escape or handle safely
        assert result["success"] is True  # Should not crash


@pytest.mark.asyncio
async def test_days_parameter_edge_cases(mock_workspace_id, mock_software_inventory_response):
    """Test get_software_inventory with various days parameter values"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()
        mock_response.tables = [mock_software_inventory_response["tables"][0]]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        # Test various days values
        for days in [1, 7, 30, 90, 365, 730]:
            result = await get_software_inventory(
                workspace_id=mock_workspace_id,
                days=days,
                software_filter=None,
                limit=10000
            )
            assert result["success"] is True


# ==========================================
# Data Normalization Tests
# ==========================================


@pytest.mark.asyncio
async def test_software_name_normalization(mock_workspace_id):
    """Test software name normalization and mapping"""
    with patch('mcp_servers.inventory_mcp_server.LogsQueryClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_response = MagicMock()

        # Mix of different naming conventions
        mock_response.tables = [{
            "columns": [
                {"name": "computer", "type": "string"},
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "publisher", "type": "string"},
                {"name": "install_date", "type": "datetime"},
                {"name": "last_seen", "type": "datetime"},
                {"name": "source", "type": "string"}
            ],
            "rows": [
                ["COMP-001", "python 3.11", "3.11.5", "Python", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                ["COMP-002", "Python 3.11.5", "3.11.5", "Python", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
                ["COMP-003", "Python3", "3.11.5", "Python Foundation", None, "2025-02-15T12:00:00Z", "ConfigurationData"],
            ]
        }]
        mock_instance.query_workspace = AsyncMock(return_value=mock_response)

        from mcp_servers.inventory_mcp_server import get_software_inventory

        result = await get_software_inventory(
            workspace_id=mock_workspace_id,
            days=90,
            software_filter="Python",
            limit=10000
        )

        assert result["success"] is True
        # All should be recognized as Python (normalization may or may not happen in inventory server)
        assert result["count"] >= 1
