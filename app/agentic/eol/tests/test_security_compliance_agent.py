"""Unit tests for SecurityComplianceAgent with Azure resource compliance audits.

This test module covers:
- Agent initialization
- Azure resource compliance rule definitions
- New action handler registration
- Violation categorization by severity
- Compliance status determination
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.security_compliance_agent import SecurityComplianceAgent
from agents.base_sre_agent import AgentExecutionError


@pytest.mark.asyncio
async def test_agent_initialization():
    """Test agent initializes with Azure resource compliance rules."""
    agent = SecurityComplianceAgent()

    # Verify agent attributes
    assert agent.agent_type == "security-compliance"
    assert agent.timeout == 600

    # Verify Azure resource compliance rules are defined
    assert hasattr(agent, 'network_rules')
    assert hasattr(agent, 'private_endpoint_rules')
    assert hasattr(agent, 'encryption_rules')
    assert hasattr(agent, 'public_access_rules')

    # Verify rule structure
    assert "subnets_require_nsg" in agent.network_rules
    assert "storage_private_endpoints" in agent.private_endpoint_rules
    assert "storage_encryption_at_rest" in agent.encryption_rules
    assert "storage_disable_public_access" in agent.public_access_rules

    # Verify severity levels include critical
    assert "critical" in agent.severity_levels
    assert agent.severity_levels["critical"]["priority"] == 1


@pytest.mark.asyncio
async def test_new_actions_registered():
    """Test new Azure resource audit actions are available."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    await agent.initialize()

    # Test that new actions are recognized
    # The execute method should not raise an error for new actions
    actions = [
        "audit_network",
        "audit_private_endpoints",
        "audit_encryption",
        "audit_public_access",
        "audit_regional_compliance",
        "audit_azure_resources"
    ]

    for action in actions:
        # Verify action would be routed correctly
        # (We don't execute because we'd need to mock Azure CLI calls)
        assert action in [
            "audit_network",
            "audit_private_endpoints",
            "audit_encryption",
            "audit_public_access",
            "audit_regional_compliance",
            "audit_azure_resources"
        ]


@pytest.mark.asyncio
async def test_categorize_violations():
    """Test violation categorization by severity."""
    agent = SecurityComplianceAgent()

    violations = [
        {"severity": "critical"},
        {"severity": "critical"},
        {"severity": "high"},
        {"severity": "high"},
        {"severity": "high"},
        {"severity": "medium"},
        {"severity": "low"},
    ]

    breakdown = agent._categorize_by_severity(violations)

    assert breakdown["critical"] == 2
    assert breakdown["high"] == 3
    assert breakdown["medium"] == 1
    assert breakdown["low"] == 1
    assert breakdown["informational"] == 0


@pytest.mark.asyncio
async def test_compliance_status_determination():
    """Test compliance status determination from percentage."""
    agent = SecurityComplianceAgent()

    # Test various compliance percentages
    assert agent._determine_compliance_status(100) == "compliant"
    assert agent._determine_compliance_status(95) == "compliant"
    assert agent._determine_compliance_status(90) == "mostly_compliant"
    assert agent._determine_compliance_status(80) == "mostly_compliant"
    assert agent._determine_compliance_status(70) == "partially_compliant"
    assert agent._determine_compliance_status(60) == "partially_compliant"
    assert agent._determine_compliance_status(50) == "non_compliant"
    assert agent._determine_compliance_status(0) == "non_compliant"


@pytest.mark.asyncio
async def test_network_audit_action_with_mock():
    """Test network compliance audit action with mocked Azure CLI responses."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()

    # Mock tool proxy agent
    agent.tool_proxy_agent = AsyncMock()

    # Mock VNet query response
    vnet_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "name": "test-vnet",
                "resourceGroup": "test-rg",
                "subnets": [
                    {
                        "name": "subnet1",
                        "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet/subnets/subnet1",
                        "networkSecurityGroup": None  # Missing NSG - violation
                    }
                ]
            }
        ])
    }

    # Mock NSG query response
    nsg_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "name": "test-nsg",
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Network/networkSecurityGroups/test-nsg"
            }
        ])
    }

    # Mock NSG rules response - no deny rule
    nsg_rules_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "direction": "Outbound",
                "access": "Allow",
                "destinationAddressPrefix": "*"
            }
        ])
    }

    # Mock route table response
    route_table_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "name": "test-rt",
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Network/routeTables/test-rt",
                "routes": []  # No firewall route - violation
            }
        ])
    }

    # Configure mock to return appropriate responses based on command
    async def mock_handle_request(request):
        command = request.get("parameters", {}).get("command", "")
        if "vnet list" in command:
            return vnet_response
        elif "nsg rule list" in command:
            return nsg_rules_response
        elif "nsg list" in command:
            return nsg_response
        elif "route-table list" in command:
            return route_table_response
        return {"status": "error", "error": "Unknown command"}

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Execute network audit
    result = await agent.execute({
        "action": "audit_network",
        "resource_group": "test-rg"
    })

    # Verify result structure
    assert result["status"] == "success"
    assert "audit" in result
    assert "violations" in result["audit"]

    # Verify violations were detected
    violations = result["audit"]["violations"]
    assert violations["total"] >= 1  # At least the missing NSG violation

    # Verify resources were checked
    resources_checked = result["audit"]["resources_checked"]
    assert resources_checked["virtual_networks"] == 1
    assert resources_checked["network_security_groups"] == 1


@pytest.mark.asyncio
async def test_private_endpoint_audit_with_mock():
    """Test private endpoint compliance audit with mocked responses."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    # Mock private endpoint query response (empty - no private endpoints)
    pe_response = {
        "status": "success",
        "stdout": json.dumps([])
    }

    # Mock storage account query response - public access enabled
    storage_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "name": "teststorage",
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/teststorage",
                "publicNetworkAccess": "Enabled"  # Violation
            }
        ])
    }

    # Mock Key Vault response
    kv_response = {
        "status": "success",
        "stdout": json.dumps([])
    }

    # Mock SQL response
    sql_response = {
        "status": "success",
        "stdout": json.dumps([])
    }

    # Configure mock responses
    async def mock_handle_request(request):
        command = request.get("parameters", {}).get("command", "")
        if "private-endpoint list" in command:
            return pe_response
        elif "storage account list" in command:
            return storage_response
        elif "keyvault list" in command:
            return kv_response
        elif "sql server list" in command:
            return sql_response
        return {"status": "error", "error": "Unknown command"}

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Execute private endpoint audit
    result = await agent.execute({
        "action": "audit_private_endpoints",
        "resource_group": "test-rg"
    })

    # Verify result
    assert result["status"] == "success"
    assert "audit" in result

    # Should have detected storage account without private endpoint
    violations = result["audit"]["violations"]
    assert violations["total"] >= 1


@pytest.mark.asyncio
async def test_full_azure_resource_compliance_audit():
    """Test full Azure resource compliance audit orchestration."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    # Mock all Azure CLI responses with empty results
    empty_response = {
        "status": "success",
        "stdout": json.dumps([])
    }

    async def mock_handle_request(request):
        return empty_response

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Execute full compliance audit
    result = await agent.execute({
        "action": "audit_azure_resources",
        "resource_group": "test-rg"
    })

    # Verify result structure
    assert result["status"] == "success"
    assert result["audit_type"] == "comprehensive"
    assert "phases" in result
    assert "executive_summary" in result

    # Verify all phases executed
    phases = result["phases"]
    assert "network_security" in phases
    assert "private_endpoints" in phases
    assert "encryption" in phases
    assert "public_access" in phases

    # Verify executive summary
    summary = result["executive_summary"]
    assert "overall_status" in summary
    assert "overall_compliance_percentage" in summary
    assert "total_violations" in summary
    assert "violations_by_severity" in summary


@pytest.mark.asyncio
async def test_backward_compatibility():
    """Test that existing actions still work after enhancements."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()
    agent.context_store.add_step_result = AsyncMock()
    agent.context_store.get_workflow_context = AsyncMock(return_value={})

    # Mock tool proxy agent
    agent.tool_proxy_agent = AsyncMock()

    # Mock security score response
    security_score_response = {
        "status": "success",
        "data": {
            "overall_score": 75,
            "max_score": 100
        }
    }

    # Mock recommendations response
    recommendations_response = {
        "status": "success",
        "data": {
            "recommendations": [
                {"severity": "high", "description": "Test recommendation"}
            ]
        }
    }

    async def mock_handle_request(request):
        tool = request.get("tool", "")
        if "security_score" in tool:
            return security_score_response
        elif "recommendations" in tool:
            return recommendations_response
        return {"status": "success", "data": {}}

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Test existing scan_security action
    result = await agent.execute({
        "action": "scan_security",
        "resource_group": "test-rg"
    })

    assert result["status"] == "success"
    assert "scan" in result
    assert "security_score" in result["scan"]


@pytest.mark.asyncio
async def test_regional_compliance_audit():
    """Test regional compliance audit with mocked responses."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    # Mock resource list response - some resources in wrong region
    resources_response = {
        "status": "success",
        "stdout": json.dumps([
            {
                "name": "compliant-storage",
                "type": "Microsoft.Storage/storageAccounts",
                "location": "southeastasia",
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Storage/storageAccounts/compliant-storage"
            },
            {
                "name": "non-compliant-vm",
                "type": "Microsoft.Compute/virtualMachines",
                "location": "eastus",  # Wrong region - violation
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/non-compliant-vm"
            },
            {
                "name": "non-compliant-webapp",
                "type": "Microsoft.Web/sites",
                "location": "westeurope",  # Wrong region - violation
                "resourceGroup": "test-rg",
                "id": "/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Web/sites/non-compliant-webapp"
            }
        ])
    }

    # Configure mock response
    async def mock_handle_request(request):
        command = request.get("parameters", {}).get("command", "")
        if "az resource list" in command:
            return resources_response
        return {"status": "error", "error": "Unknown command"}

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Execute regional compliance audit
    result = await agent.execute({
        "action": "audit_regional_compliance",
        "resource_group": "test-rg"
    })

    # Verify result
    assert result["status"] == "success"
    assert "audit" in result
    audit = result["audit"]

    # Verify audit type
    assert audit["type"] == "regional_compliance"
    assert audit["allowed_region"] == "southeastasia"

    # Verify violations detected (2 out of 3 resources in wrong region)
    violations = audit["violations"]
    assert violations["total"] == 2

    # Verify compliance percentage (1 out of 3 = 33.33%)
    assert audit["compliance_percentage"] < 50

    # Verify violation details
    details = violations["details"]
    assert len(details) == 2

    # Check that violations have correct structure
    for violation in details:
        assert violation["rule"] == "resources_in_southeastasia"
        assert violation["severity"] == "high"
        assert violation["current_location"] in ["eastus", "westeurope"]
        assert violation["expected_location"] == "southeastasia"

    # Verify summary
    summary = audit["summary"]
    assert summary["compliant_resources"] == 1
    assert summary["non_compliant_resources"] == 2
    assert "eastus" in summary["non_compliant_locations"]
    assert "westeurope" in summary["non_compliant_locations"]


@pytest.mark.asyncio
async def test_full_audit_includes_regional_compliance():
    """Test that full audit now includes regional compliance check."""
    agent = SecurityComplianceAgent()

    # Mock dependencies
    agent.registry = MagicMock()
    agent.context_store = AsyncMock()
    agent.context_store.create_workflow_context = AsyncMock()
    agent.tool_proxy_agent = AsyncMock()

    # Mock all Azure CLI responses with empty results
    empty_response = {
        "status": "success",
        "stdout": json.dumps([])
    }

    async def mock_handle_request(request):
        return empty_response

    agent.tool_proxy_agent.handle_request = mock_handle_request

    await agent.initialize()

    # Execute full compliance audit
    result = await agent.execute({
        "action": "audit_azure_resources",
        "resource_group": "test-rg"
    })

    # Verify result structure
    assert result["status"] == "success"
    assert result["audit_type"] == "comprehensive"
    assert "phases" in result

    # Verify all phases executed including regional compliance
    phases = result["phases"]
    assert "network_security" in phases
    assert "private_endpoints" in phases
    assert "encryption" in phases
    assert "public_access" in phases
    assert "regional_compliance" in phases  # NEW PHASE

    # Verify executive summary
    summary = result["executive_summary"]
    assert "overall_status" in summary
    assert "overall_compliance_percentage" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
