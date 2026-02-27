"""
Azure AI SRE API Router Tests

Tests for Azure AI SRE agent integration endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestAzureAISRERouterUnit:
    """Unit tests for Azure AI SRE router without full app."""

    def test_azure_ai_sre_router_imports(self):
        """Test Azure AI SRE router can be imported."""
        from api.azure_ai_sre import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_azure_ai_sre_router_has_endpoints(self):
        """Test Azure AI SRE router has expected endpoints."""
        from api.azure_ai_sre import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have azure-ai-sre endpoints
        assert any('/azure-ai-sre' in path for path in paths)

    def test_azure_ai_sre_request_models(self):
        """Test Azure AI SRE request models exist."""
        from api.azure_ai_sre import SREQueryRequest, SRECapability

        # SREQueryRequest
        req = SREQueryRequest(query="Check VM health", thread_id="thread-123")
        assert req.query == "Check VM health"
        assert req.thread_id == "thread-123"

        # SRECapability
        cap = SRECapability(
            name="vm_diagnostics",
            description="VM health checks",
            category="monitoring"
        )
        assert cap.name == "vm_diagnostics"
        assert cap.category == "monitoring"


class TestAzureAISREEndpointSignatures:
    """Tests for Azure AI SRE endpoint signatures."""

    def test_get_status_endpoint(self):
        """Test GET /api/azure-ai-sre/status endpoint exists."""
        from api.azure_ai_sre import router

        status_routes = [r for r in router.routes if '/api/azure-ai-sre/status' in r.path]
        assert len(status_routes) >= 1

    def test_get_capabilities_endpoint(self):
        """Test GET /api/azure-ai-sre/capabilities endpoint exists."""
        from api.azure_ai_sre import router

        cap_routes = [r for r in router.routes if '/api/azure-ai-sre/capabilities' in r.path]
        assert len(cap_routes) >= 1

    def test_post_query_endpoint(self):
        """Test POST /api/azure-ai-sre/query endpoint exists."""
        from api.azure_ai_sre import router

        query_routes = [r for r in router.routes if '/api/azure-ai-sre/query' in r.path]
        assert len(query_routes) >= 1


class TestAzureAISRERouterConfiguration:
    """Tests for Azure AI SRE router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.azure_ai_sre import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import azure_ai_sre

        assert hasattr(azure_ai_sre, 'StandardResponse')

    def test_decorators_imported(self):
        """Test endpoint decorators are imported."""
        from api import azure_ai_sre

        # Should have decorators imported
        assert hasattr(azure_ai_sre, 'readonly_endpoint') or hasattr(azure_ai_sre, 'write_endpoint')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import azure_ai_sre

        assert hasattr(azure_ai_sre, 'logger')

    def test_config_imported(self):
        """Test config is imported."""
        from api import azure_ai_sre

        assert hasattr(azure_ai_sre, 'config')


@pytest.mark.asyncio
class TestAzureAISREEndpointLogic:
    """Tests for Azure AI SRE endpoint logic with mocking."""

    @patch('utils.config.config')
    async def test_get_sre_agent_status_disabled(self, mock_config):
        """Test get_sre_agent_status when agent is disabled."""
        from api.azure_ai_sre import get_sre_agent_status

        # Mock config to show SRE disabled
        mock_sre_config = MagicMock()
        mock_sre_config.enabled = False
        mock_sre_config.agent_name = "gccsreagent"
        mock_config.azure_ai_sre = mock_sre_config

        # Call endpoint
        result = await get_sre_agent_status()

        # Verify response shows disabled
        assert result.success is True
        assert result.data["enabled"] is False
        assert "disabled" in result.message.lower()

    @patch('agents.azure_ai_sre_agent.AzureAISREAgent')
    @patch('utils.config.config')
    async def test_get_sre_agent_status_enabled(self, mock_config, mock_agent_class):
        """Test get_sre_agent_status when agent is enabled and available."""
        from api.azure_ai_sre import get_sre_agent_status

        # Mock config to show SRE enabled
        mock_sre_config = MagicMock()
        mock_sre_config.enabled = True
        mock_sre_config.agent_name = "gccsreagent"
        mock_sre_config.project_endpoint = "https://test.endpoint"
        mock_config.azure_ai_sre = mock_sre_config

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.is_available = MagicMock(return_value=True)
        mock_agent.get_agent_info = MagicMock(return_value={
            "name": "gccsreagent",
            "capabilities": ["vm_diagnostics"]
        })
        mock_agent_class.return_value = mock_agent

        # Call endpoint
        result = await get_sre_agent_status()

        # Verify response shows available
        assert result.success is True
        assert result.data["enabled"] is True


class TestAzureAISREModuleStructure:
    """Tests for Azure AI SRE module structure."""

    def test_module_has_required_imports(self):
        """Test Azure AI SRE module has required imports."""
        from api import azure_ai_sre

        # Check key imports exist
        assert hasattr(azure_ai_sre, 'APIRouter')
        assert hasattr(azure_ai_sre, 'HTTPException')
        assert hasattr(azure_ai_sre, 'BaseModel')
        assert hasattr(azure_ai_sre, 'StreamingResponse')

    def test_sre_query_request_model(self):
        """Test SREQueryRequest model exists and validates."""
        from api.azure_ai_sre import SREQueryRequest

        # Create instance
        req = SREQueryRequest(query="Check VM performance")
        assert req.query == "Check VM performance"
        assert req.thread_id is None

        # With thread ID
        req2 = SREQueryRequest(query="Continue diagnostics", thread_id="thread-456")
        assert req2.thread_id == "thread-456"

    def test_sre_capability_model(self):
        """Test SRECapability model exists and validates."""
        from api.azure_ai_sre import SRECapability

        # Create instance
        cap = SRECapability(
            name="incident_management",
            description="Create and manage incidents",
            category="operations"
        )
        assert cap.name == "incident_management"
        assert cap.description == "Create and manage incidents"
        assert cap.category == "operations"

    def test_get_sre_agent_status_function_exists(self):
        """Test get_sre_agent_status function exists."""
        from api import azure_ai_sre

        assert hasattr(azure_ai_sre, 'get_sre_agent_status')
        assert callable(azure_ai_sre.get_sre_agent_status)
