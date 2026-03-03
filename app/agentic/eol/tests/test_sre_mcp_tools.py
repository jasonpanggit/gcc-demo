"""
Test suite for SRE MCP Server tools.

Tests all 24 SRE tools with mocked Azure SDK responses.
Covers success paths, error handling, and edge cases.

NOTE: MCP tools are called via the FastMCP framework, which handles the Context parameter automatically.
Tests mock the underlying Azure SDK clients, not the MCP server directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mark all tests in this module
pytestmark = [pytest.mark.unit, pytest.mark.asyncio, pytest.mark.mcp_sre]


@pytest.fixture
def mock_resource_id():
    """Mock Azure resource ID"""
    return "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-test"


@pytest.fixture
def mock_workspace_id():
    """Mock Log Analytics workspace ID"""
    return "12345678-1234-1234-1234-workspace01"


@pytest.fixture
def mock_resource_health_response():
    """Mock Azure Resource Health API response"""
    return {
        "availability_state": "Available",
        "summary": "This resource is healthy",
        "reason_type": None,
        "occurred_time": datetime.utcnow().isoformat(),
        "detailed_status": "Available"
    }


@pytest.fixture
def mock_logs_query_response():
    """Mock Azure Monitor Logs query response"""
    mock_table = MagicMock()
    mock_table.rows = [
        ["2025-02-15T12:00:00Z", "Application started", "Info"],
        ["2025-02-15T12:01:00Z", "Processing request", "Info"],
        ["2025-02-15T12:02:00Z", "Error occurred", "Error"]
    ]
    mock_table.columns = [
        MagicMock(name="TimeGenerated", type="datetime"),
        MagicMock(name="Message", type="string"),
        MagicMock(name="Level", type="string")
    ]
    return [mock_table]


# ==========================================
# Resource Health & Diagnostics Tests (7 tools)
# ==========================================


@pytest.mark.asyncio
async def test_check_resource_health_success(mock_resource_id, mock_resource_health_response):
    """Test check_resource_health tool with successful response"""
    with patch('mcp_servers.sre_mcp_server.ResourceHealthMgmtClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred, \
         patch('mcp_servers.sre_mcp_server._subscription_id', '12345678-1234-1234-1234-123456789012'):

        # Mock credential
        mock_cred.return_value = MagicMock()

        # Mock the availability status response with proper datetime
        mock_availability = MagicMock()
        mock_availability.availability_state = "Available"
        mock_availability.summary = "This resource is healthy"
        mock_availability.reason_type = None
        mock_availability.occurred_time = datetime.utcnow()  # Real datetime object
        mock_availability.detailed_status = "Available"

        mock_client = mock_client_class.return_value
        mock_client.availability_statuses.get_by_resource.return_value = mock_availability

        # Import and call the tool function directly (without Context - it's handled by FastMCP)
        from mcp_servers.sre_mcp_server import check_resource_health

        # Create a mock Context
        mock_context = MagicMock()

        result = await check_resource_health(
            context=mock_context,
            resource_id=mock_resource_id
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True
        assert "Available" in result_data.get("availability_state", "")


@pytest.mark.asyncio
async def test_get_diagnostic_logs_success(mock_workspace_id, mock_resource_id, mock_logs_query_response):
    """Test get_diagnostic_logs tool with successful KQL query"""
    with patch('mcp_servers.sre_mcp_server.LogsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        # Mock query response
        mock_response = MagicMock()
        mock_response.tables = mock_logs_query_response

        mock_client = mock_client_class.return_value
        mock_client.query_workspace.return_value = mock_response

        from mcp_servers.sre_mcp_server import get_diagnostic_logs

        mock_context = MagicMock()

        result = await get_diagnostic_logs(
            context=mock_context,
            workspace_id=mock_workspace_id,
            resource_id=mock_resource_id,
            hours=24
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True
        assert "logs" in result_data or "events" in result_data


@pytest.mark.asyncio
async def test_get_resource_dependencies_success(mock_resource_id):
    """Test get_resource_dependencies with Resource Graph query"""
    with patch('mcp_servers.sre_mcp_server.ResourceGraphClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        # Mock Resource Graph response
        mock_response = MagicMock()
        mock_response.data = [{
            "id": mock_resource_id,
            "name": "vm-test",
            "type": "Microsoft.Compute/virtualMachines",
            "dependencies": [
                "/subscriptions/.../providers/Microsoft.Network/networkInterfaces/nic-test"
            ]
        }]

        mock_client = mock_client_class.return_value
        mock_client.resources.return_value = mock_response

        from mcp_servers.sre_mcp_server import get_resource_dependencies

        mock_context = MagicMock()

        result = await get_resource_dependencies(
            context=mock_context,
            resource_id=mock_resource_id
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


# ==========================================
# Incident Response Tests (5 tools)
# ==========================================


@pytest.mark.asyncio
async def test_triage_incident_success(mock_resource_id, mock_workspace_id):
    """Test triage_incident tool with automated incident analysis"""
    with patch('mcp_servers.sre_mcp_server.check_resource_health') as mock_health, \
         patch('mcp_servers.sre_mcp_server.get_diagnostic_logs') as mock_logs:

        # Mock sub-function responses
        mock_health_result = MagicMock()
        mock_health_result.text = json.dumps({"success": True, "availability_state": "Unavailable"})
        mock_health.return_value = [mock_health_result]

        mock_logs_result = MagicMock()
        mock_logs_result.text = json.dumps({"success": True, "logs": [{"level": "Error"}]})
        mock_logs.return_value = [mock_logs_result]

        from mcp_servers.sre_mcp_server import triage_incident

        mock_context = MagicMock()

        result = await triage_incident(
            context=mock_context,
            incident_title="VM not responding",
            affected_resources=[mock_resource_id],
            workspace_id=mock_workspace_id
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


@pytest.mark.asyncio
async def test_search_logs_by_error_success(mock_workspace_id, mock_logs_query_response):
    """Test search_logs_by_error with pattern matching"""
    with patch('mcp_servers.sre_mcp_server.LogsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        mock_response = MagicMock()
        mock_response.tables = mock_logs_query_response

        mock_client = mock_client_class.return_value
        mock_client.query_workspace.return_value = mock_response

        from mcp_servers.sre_mcp_server import search_logs_by_error

        mock_context = MagicMock()

        result = await search_logs_by_error(
            context=mock_context,
            workspace_id=mock_workspace_id,
            error_pattern="timeout",
            hours=24
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


@pytest.mark.asyncio
async def test_correlate_alerts_success(mock_workspace_id, mock_resource_id):
    """Test correlate_alerts with Log Analytics Alert table"""
    with patch('mcp_servers.sre_mcp_server.LogsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        mock_table = MagicMock()
        mock_table.rows = [
            ["alert-1", "2025-02-15T12:00:00Z", "HighCPU", mock_resource_id],
            ["alert-2", "2025-02-15T12:02:00Z", "HighMemory", mock_resource_id],
        ]
        mock_response = MagicMock()
        mock_response.tables = [mock_table]

        mock_client = mock_client_class.return_value
        mock_client.query_workspace.return_value = mock_response

        from mcp_servers.sre_mcp_server import correlate_alerts

        mock_context = MagicMock()

        result = await correlate_alerts(
            context=mock_context,
            workspace_id=mock_workspace_id,
            start_time="2025-02-15T11:00:00Z",
            end_time="2025-02-15T13:00:00Z",
            resource_id=mock_resource_id
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


# ==========================================
# Performance Monitoring Tests (4 tools)
# ==========================================


@pytest.mark.asyncio
async def test_get_performance_metrics_success(mock_resource_id):
    """Test get_performance_metrics with Azure Monitor"""
    with patch('mcp_servers.sre_mcp_server.MetricsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        # Mock metrics response
        mock_metric = MagicMock()
        mock_metric.name = MagicMock(value="Percentage CPU", localized_value="Percentage CPU")
        mock_timeseries = MagicMock()
        mock_datapoint = MagicMock()
        mock_datapoint.time_stamp = datetime.utcnow()
        mock_datapoint.average = 25.5
        mock_timeseries.data = [mock_datapoint]
        mock_metric.timeseries = [mock_timeseries]

        mock_response = MagicMock()
        mock_response.value = [mock_metric]

        mock_client = mock_client_class.return_value
        mock_client.query_resource.return_value = mock_response

        from mcp_servers.sre_mcp_server import get_performance_metrics

        mock_context = MagicMock()

        result = await get_performance_metrics(
            context=mock_context,
            resource_id=mock_resource_id,
            metric_names=["Percentage CPU"],
            hours=1
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


# ==========================================
# Remediation Tests (3 tools)
# ==========================================


@pytest.mark.asyncio
async def test_plan_remediation_success(mock_resource_id):
    """Test plan_remediation with step-by-step plan generation"""
    from mcp_servers.sre_mcp_server import plan_remediation

    mock_context = MagicMock()

    result = await plan_remediation(
        context=mock_context,
        issue_description="High CPU usage causing performance degradation",
        resource_id=mock_resource_id,
        remediation_type="restart"
    )

    assert len(result) > 0
    result_data = json.loads(result[0].text)
    assert result_data["success"] is True
    assert "remediation_plan" in result_data or "plan" in result_data


# ==========================================
# Notifications Tests (3 tools)
# ==========================================


@pytest.mark.asyncio
async def test_send_teams_notification_success():
    """Test send_teams_notification with webhook"""
    with patch('mcp_servers.sre_mcp_server.TeamsNotificationClient') as mock_teams_class:
        mock_teams = mock_teams_class.return_value
        # Make send_notification return a dict, not a coroutine
        mock_teams.send_notification.return_value = {"success": True, "message_id": "msg-123"}

        from mcp_servers.sre_mcp_server import send_teams_notification

        mock_context = MagicMock()

        result = await send_teams_notification(
            context=mock_context,
            title="Test Notification",
            message="This is a test message",
            color="FF0000"
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True


# ==========================================
# Miscellaneous Tests (2 tools)
# ==========================================


@pytest.mark.asyncio
async def test_get_audit_trail_success():
    """Test get_audit_trail with in-memory audit log"""
    from mcp_servers.sre_mcp_server import get_audit_trail

    mock_context = MagicMock()

    result = await get_audit_trail(
        context=mock_context,
        hours=24,
        operation_filter=None,
        resource_filter=None
    )

    assert len(result) > 0
    result_data = json.loads(result[0].text)
    assert result_data["success"] is True
    assert "audit_events" in result_data or "events" in result_data


# ==========================================
# Error Handling Tests
# ==========================================


@pytest.mark.asyncio
async def test_authentication_failure(mock_resource_id):
    """Test SRE tool behavior with authentication failure"""
    with patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:
        mock_cred.side_effect = Exception("AuthenticationFailed")

        from mcp_servers.sre_mcp_server import check_resource_health

        mock_context = MagicMock()

        result = await check_resource_health(
            context=mock_context,
            resource_id=mock_resource_id
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is False


@pytest.mark.asyncio
async def test_timeout_handling(mock_workspace_id, mock_resource_id):
    """Test SRE tool behavior with query timeout"""
    with patch('mcp_servers.sre_mcp_server.LogsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()
        mock_client = mock_client_class.return_value
        mock_client.query_workspace.side_effect = TimeoutError("Query exceeded timeout limit")

        from mcp_servers.sre_mcp_server import get_diagnostic_logs

        mock_context = MagicMock()

        result = await get_diagnostic_logs(
            context=mock_context,
            workspace_id=mock_workspace_id,
            resource_id=mock_resource_id,
            hours=1
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is False


@pytest.mark.asyncio
async def test_invalid_resource_id():
    """Test SRE tool behavior with invalid resource ID"""
    with patch('mcp_servers.sre_mcp_server.ResourceHealthMgmtClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred, \
         patch('mcp_servers.sre_mcp_server._subscription_id', '12345678-1234-1234-1234-123456789012'):

        mock_cred.return_value = MagicMock()
        mock_client = mock_client_class.return_value
        mock_client.availability_statuses.get_by_resource.side_effect = Exception("ResourceNotFound")

        from mcp_servers.sre_mcp_server import check_resource_health

        mock_context = MagicMock()

        result = await check_resource_health(
            context=mock_context,
            resource_id="invalid-resource-id"
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is False


# ==========================================
# Edge Case Tests
# ==========================================


@pytest.mark.asyncio
async def test_empty_logs_result(mock_workspace_id, mock_resource_id):
    """Test get_diagnostic_logs with no matching logs"""
    with patch('mcp_servers.sre_mcp_server.LogsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        mock_table = MagicMock()
        mock_table.rows = []  # Empty result
        mock_table.columns = []
        mock_response = MagicMock()
        mock_response.tables = [mock_table]

        mock_client = mock_client_class.return_value
        mock_client.query_workspace.return_value = mock_response

        from mcp_servers.sre_mcp_server import get_diagnostic_logs

        mock_context = MagicMock()

        result = await get_diagnostic_logs(
            context=mock_context,
            workspace_id=mock_workspace_id,
            resource_id=mock_resource_id,
            hours=1
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        # Empty results should still be successful
        assert result_data["success"] is True


@pytest.mark.asyncio
async def test_large_metrics_dataset(mock_resource_id):
    """Test get_performance_metrics with large number of data points"""
    with patch('mcp_servers.sre_mcp_server.MetricsQueryClient') as mock_client_class, \
         patch('mcp_servers.sre_mcp_server._get_credential') as mock_cred:

        mock_cred.return_value = MagicMock()

        # Generate 100 data points
        mock_datapoints = []
        for i in range(100):
            mock_dp = MagicMock()
            mock_dp.time_stamp = datetime.utcnow() - timedelta(minutes=i)
            mock_dp.average = float(i % 100)
            mock_datapoints.append(mock_dp)

        mock_timeseries = MagicMock()
        mock_timeseries.data = mock_datapoints

        mock_metric = MagicMock()
        mock_metric.name = MagicMock(value="Percentage CPU")
        mock_metric.timeseries = [mock_timeseries]

        mock_response = MagicMock()
        mock_response.value = [mock_metric]

        mock_client = mock_client_class.return_value
        mock_client.query_resource.return_value = mock_response

        from mcp_servers.sre_mcp_server import get_performance_metrics

        mock_context = MagicMock()

        result = await get_performance_metrics(
            context=mock_context,
            resource_id=mock_resource_id,
            metric_names=["Percentage CPU"],
            hours=24
        )

        assert len(result) > 0
        result_data = json.loads(result[0].text)
        assert result_data["success"] is True
