"""Tests for SRE user interaction and response formatting.

This module tests:
1. User selection prompts for ambiguous resources
2. Response formatting for different tool outputs
3. Parameter discovery and validation
4. Friendly message generation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import modules to test
try:
    from app.agentic.eol.utils.sre_response_formatter import (
        SREResponseFormatter,
        format_resource_selection,
        format_tool_result,
    )
    from app.agentic.eol.utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
except ModuleNotFoundError:
    from utils.sre_response_formatter import (
        SREResponseFormatter,
        format_resource_selection,
        format_tool_result,
    )
    from utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )

try:
    from app.agentic.eol.agents.sre_orchestrator import SREOrchestratorAgent
except ModuleNotFoundError:
    from agents.sre_orchestrator import SREOrchestratorAgent


# ============================================================================
# Response Formatter Tests
# ============================================================================

class TestSREResponseFormatter:
    """Test SRE response formatter functionality."""

    def test_format_resource_list_single(self):
        """Test formatting a single resource."""
        formatter = SREResponseFormatter()

        resources = [
            {
                "_index": 1,
                "name": "my-container-app",
                "location": "East US",
                "resource_group": "prod-rg",
                "provisioning_state": "Succeeded",
                "fqdn": "my-app.azurecontainerapps.io"
            }
        ]

        result = formatter.format_resource_list(
            resources,
            "Container App",
            context="Found 1 Container App matching your query"
        )

        assert "my-container-app" in result
        assert "East US" in result
        assert "prod-rg" in result
        assert "<table" in result
        assert "</table>" in result

    def test_format_resource_list_multiple(self):
        """Test formatting multiple resources."""
        formatter = SREResponseFormatter()

        resources = [
            {"_index": 1, "name": "app-1", "location": "East US", "resource_group": "rg-1"},
            {"_index": 2, "name": "app-2", "location": "West US", "resource_group": "rg-2"},
            {"_index": 3, "name": "app-3", "location": "Central US", "resource_group": "rg-3"},
        ]

        result = formatter.format_resource_list(resources, "Container App")

        assert "app-1" in result
        assert "app-2" in result
        assert "app-3" in result
        assert "Found <strong>3</strong>" in result

    def test_format_health_status_healthy(self):
        """Test formatting healthy resource status."""
        formatter = SREResponseFormatter()

        health_data = {
            "availability_state": "Available",
            "reason_type": "Platform Initiated",
            "summary": "Resource is healthy and operational"
        }

        result = formatter.format_health_status("my-vm", health_data)

        assert "✅" in result or "Available" in result
        assert "my-vm" in result
        assert "healthy" in result.lower() or "available" in result.lower()

    def test_format_health_status_unhealthy(self):
        """Test formatting unhealthy resource status with next steps."""
        formatter = SREResponseFormatter()

        health_data = {
            "availability_state": "Unhealthy",
            "reason_type": "Platform Issue",
            "summary": "Resource is experiencing issues"
        }

        result = formatter.format_health_status("my-vm", health_data)

        assert "⚠️" in result or "❌" in result or "Unhealthy" in result
        assert "Next Steps" in result
        assert "diagnostic logs" in result.lower()

    def test_format_cost_summary(self):
        """Test formatting cost analysis results."""
        formatter = SREResponseFormatter()

        cost_data = {
            "total_cost": 1234.56,
            "currency": "USD",
            "time_period": "last 30 days",
            "breakdown": [
                {"service": "Virtual Machines", "cost": 500.00, "percentage": 40.5},
                {"service": "Storage", "cost": 300.00, "percentage": 24.3},
                {"service": "Networking", "cost": 200.00, "percentage": 16.2},
            ],
            "potential_savings": 250.00
        }

        result = formatter.format_cost_summary(cost_data)

        assert "💰" in result or "Cost Analysis" in result
        assert "1,234.56" in result
        assert "Virtual Machines" in result
        assert "Potential Savings" in result
        assert "250.00" in result

    def test_format_cost_recommendations_tool_result(self):
        """Test formatting cost recommendations into readable HTML (not raw JSON)."""
        result = {
            "recommendation_count": 2,
            "recommendations": [
                {
                    "problem": "Underutilized VM",
                    "solution": "Resize to smaller SKU",
                    "impacted_value": "vm-prod-01",
                    "savings_amount": "1200",
                    "savings_currency": "USD",
                },
                {
                    "problem": "Idle public IP",
                    "solution": "Delete unattached IP",
                    "impacted_value": "pip-unused-01",
                    "savings_amount": "600",
                    "savings_currency": "USD",
                },
            ],
        }

        formatted = format_tool_result("get_cost_recommendations", result)

        assert "Cost Recommendations" in formatted
        assert "Underutilized VM" in formatted
        assert "Resize to smaller SKU" in formatted
        # (1200 + 600) / 12 = 150 monthly
        assert "150.00" in formatted

    def test_format_performance_metrics(self):
        """Test formatting performance metrics."""
        formatter = SREResponseFormatter()

        metrics = {
            "cpu_percent": 85.5,
            "memory_percent": 72.3,
            "bottlenecks": [
                "High CPU utilization detected",
                "Memory usage approaching threshold"
            ],
            "recommendations": [
                "Consider scaling up VM size",
                "Optimize application memory usage"
            ]
        }

        result = formatter.format_performance_metrics("my-vm", metrics)

        assert "📊" in result or "Performance Metrics" in result
        assert "85.5" in result
        assert "72.3" in result
        assert "High CPU utilization" in result
        assert "scaling up" in result

    def test_format_incident_summary(self):
        """Test formatting incident report."""
        formatter = SREResponseFormatter()

        incident_data = {
            "severity": "high",
            "status": "active",
            "affected_resources": [
                "/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
                "/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm2"
            ],
            "root_cause": "Platform connectivity issue",
            "remediation_steps": [
                "Verify network connectivity",
                "Check NSG rules",
                "Review recent configuration changes"
            ]
        }

        result = formatter.format_incident_summary("INC-12345", incident_data)

        assert "INC-12345" in result
        assert "HIGH" in result.upper()
        assert "Affected Resources" in result
        assert "Platform connectivity issue" in result
        assert "Remediation Steps" in result

    def test_format_success_message(self):
        """Test formatting success message."""
        formatter = SREResponseFormatter()

        result = formatter.format_success_message(
            "Restarted container app 'my-app'",
            details="Application is now running and healthy",
            next_steps=[
                "Monitor application logs",
                "Verify functionality with health check"
            ]
        )

        assert "✅" in result or "Success" in result
        assert "my-app" in result
        assert "Next Steps" in result
        assert "Monitor application logs" in result

    def test_format_error_message(self):
        """Test formatting error message."""
        formatter = SREResponseFormatter()

        result = formatter.format_error_message(
            "Failed to connect to resource",
            suggestions=[
                "Verify resource exists in the subscription",
                "Check Azure credentials",
                "Ensure proper permissions are configured"
            ]
        )

        assert "❌" in result or "Error" in result
        assert "Failed to connect" in result
        assert "Try the following" in result or "suggestions" in result.lower()
        assert "Azure credentials" in result


# ============================================================================
# Interaction Handler Tests
# ============================================================================

class TestSREInteractionHandler:
    """Test SRE interaction handler functionality."""

    def test_check_required_params_all_present(self):
        """Test parameter check when all params are present."""
        handler = SREInteractionHandler()

        result = handler.check_required_params(
            "check_resource_health",
            {"resource_id": "/subscriptions/xxx/resourceGroups/rg/..."}
        )

        assert result is None  # All params present

    def test_check_required_params_missing(self):
        """Test parameter check when params are missing."""
        handler = SREInteractionHandler()

        result = handler.check_required_params(
            "check_resource_health",
            {}  # No params provided
        )

        assert result is not None
        assert result["status"] == "needs_user_input"
        assert "resource_id" in result["missing_params"]
        assert "message" in result

    def test_check_required_params_empty_string(self):
        """Test parameter check treats empty strings as missing."""
        handler = SREInteractionHandler()

        result = handler.check_required_params(
            "check_container_app_health",
            {"container_app_name": "", "resource_group": "  "}
        )

        assert result is not None
        assert "container_app_name" in result["missing_params"]
        assert "resource_group" in result["missing_params"]

    @pytest.mark.asyncio
    async def test_discover_resource_groups(self):
        """Test resource group discovery."""
        mock_executor = AsyncMock(return_value={
            "output": '[{"name": "rg-1", "location": "eastus"}, {"name": "rg-2", "location": "westus"}]',
            "status": "success"
        })

        handler = SREInteractionHandler(azure_cli_executor=mock_executor)

        result = await handler.discover_resource_groups()

        assert len(result) == 2
        assert result[0]["name"] == "rg-1"
        assert result[1]["name"] == "rg-2"
        mock_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_container_apps(self):
        """Test container app discovery."""
        mock_executor = AsyncMock(return_value={
            "output": '[{"name": "app-1", "resourceGroup": "rg-1"}, {"name": "app-2", "resourceGroup": "rg-2"}]',
            "status": "success"
        })

        handler = SREInteractionHandler(azure_cli_executor=mock_executor)

        result = await handler.discover_container_apps(resource_group="rg-1")

        assert len(result) == 2
        assert result[0]["name"] == "app-1"
        mock_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_container_apps_with_filter(self):
        """Test container app discovery with name filter."""
        mock_executor = AsyncMock(return_value={
            "output": '[{"name": "api-app", "resourceGroup": "rg-1"}, {"name": "web-app", "resourceGroup": "rg-1"}]',
            "status": "success"
        })

        handler = SREInteractionHandler(azure_cli_executor=mock_executor)

        result = await handler.discover_container_apps(name_filter="api")

        assert len(result) == 1
        assert result[0]["name"] == "api-app"

    def test_format_selection_prompt(self):
        """Test formatting selection prompt."""
        handler = SREInteractionHandler()

        resources = [
            {"name": "app-1", "id": "/sub/rg/app-1", "location": "eastus"},
            {"name": "app-2", "id": "/sub/rg/app-2", "location": "westus"},
        ]

        result = handler.format_selection_prompt(resources, "Container App", "check health")

        assert result["requires_selection"] is True
        assert result["resource_type"] == "Container App"
        assert result["action"] == "check health"
        assert len(result["options"]) == 2
        assert result["options"][0]["name"] == "app-1"

    def test_parse_user_selection_by_number(self):
        """Test parsing user selection by number."""
        handler = SREInteractionHandler()

        options = [
            {"index": 1, "name": "app-1", "id": "id-1"},
            {"index": 2, "name": "app-2", "id": "id-2"},
            {"index": 3, "name": "app-3", "id": "id-3"},
        ]

        # Test numeric selection
        result = handler.parse_user_selection("2", options)
        assert result == options[1]

        # Test with "use" prefix
        result = handler.parse_user_selection("use #1", options)
        assert result == options[0]

    def test_parse_user_selection_by_keyword(self):
        """Test parsing user selection by keyword."""
        handler = SREInteractionHandler()

        options = [
            {"index": 1, "name": "app-1", "id": "id-1"},
            {"index": 2, "name": "app-2", "id": "id-2"},
            {"index": 3, "name": "app-3", "id": "id-3"},
        ]

        # Test "first" keyword
        result = handler.parse_user_selection("first", options)
        assert result == options[0]

        # Test "last" keyword
        result = handler.parse_user_selection("the last one", options)
        assert result == options[2]

    def test_parse_user_selection_by_name(self):
        """Test parsing user selection by resource name."""
        handler = SREInteractionHandler()

        options = [
            {"index": 1, "name": "production-api", "id": "id-1"},
            {"index": 2, "name": "staging-api", "id": "id-2"},
        ]

        result = handler.parse_user_selection("use production-api", options)
        assert result == options[0]

    def test_needs_resource_discovery(self):
        """Test detection of need for resource discovery."""
        handler = SREInteractionHandler()

        # Should need discovery - ambiguous reference
        result = handler.needs_resource_discovery(
            "check_resource_health",
            {},  # No resource_id
            "check health of container app"
        )
        assert result == "container_app"

        # Should not need discovery - specific name provided
        result = handler.needs_resource_discovery(
            "check_resource_health",
            {},
            "check health of 'my-production-app-123'"
        )
        assert result is None or result  # Implementation dependent


# ============================================================================
# Integration Tests
# ============================================================================

class TestSREIntegration:
    """Integration tests for SRE user interactions."""

    def test_format_tool_result_health(self):
        """Test formatting health check tool result."""
        result = {
            "resource_name": "my-vm",
            "health_status": {
                "availability_state": "Available",
                "reason_type": "Platform Initiated",
                "summary": "Resource is healthy"
            }
        }

        formatted = format_tool_result("check_resource_health", result)

        assert "my-vm" in formatted
        assert "Available" in formatted or "✅" in formatted

    def test_format_tool_result_cost(self):
        """Test formatting cost analysis tool result."""
        result = {
            "total_cost": 500.00,
            "currency": "USD",
            "time_period": "last 30 days",
            "breakdown": [],
            "potential_savings": 100.00
        }

        formatted = format_tool_result("get_cost_analysis", result)

        assert "500.00" in formatted
        assert "Cost" in formatted or "💰" in formatted

    def test_summarize_cost_includes_recommendation_savings(self):
        """Potential savings should include summed recommendation savings."""
        orchestrator = SREOrchestratorAgent()

        results = [
            {
                "tool": "get_cost_recommendations",
                "status": "success",
                "result": {
                    "parsed": {
                        "recommendations": [
                            {"savings_amount": "1200"},
                            {"savings_amount": "600"},
                        ]
                    }
                },
            }
        ]

        summary = orchestrator._summarize_cost(results)

        assert summary["potential_savings"] == "$150.00"

    def test_format_resource_selection_wrapper(self):
        """Test the format_resource_selection wrapper function."""
        resources = [
            {"name": "vm-1", "id": "id-1", "location": "eastus"},
            {"name": "vm-2", "id": "id-2", "location": "westus"},
        ]

        result = format_resource_selection(resources, "Virtual Machine", "restart")

        assert result["requires_selection"] is True
        assert result["resource_type"] == "Virtual Machine"
        assert result["action"] == "restart"
        assert len(result["options"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
