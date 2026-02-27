"""
Azure MCP API Router Tests

Tests for Azure MCP integration endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestAzureMCPRouterUnit:
    """Unit tests for Azure MCP router without full app."""

    def test_azure_mcp_router_imports(self):
        """Test Azure MCP router can be imported."""
        from api.azure_mcp import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_azure_mcp_router_has_endpoints(self):
        """Test Azure MCP router has expected endpoints."""
        from api.azure_mcp import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have azure-mcp endpoints
        assert any('/azure-mcp' in path for path in paths)

    def test_azure_mcp_request_models(self):
        """Test Azure MCP request models exist."""
        from api.azure_mcp import ToolCallRequest, ResourceQueryRequest

        # ToolCallRequest
        req1 = ToolCallRequest(tool_name="test_tool", arguments={"param": "value"})
        assert req1.tool_name == "test_tool"
        assert req1.arguments == {"param": "value"}

        # ResourceQueryRequest
        req2 = ResourceQueryRequest(query="Resources | limit 10")
        assert req2.query == "Resources | limit 10"
        assert req2.cluster_uri is None


class TestAzureMCPEndpointSignatures:
    """Tests for Azure MCP endpoint signatures."""

    def test_get_status_endpoint(self):
        """Test GET /api/azure-mcp/status endpoint exists."""
        from api.azure_mcp import router

        status_routes = [r for r in router.routes if '/api/azure-mcp/status' in r.path]
        assert len(status_routes) >= 1

    def test_get_tools_endpoint(self):
        """Test GET /api/azure-mcp/tools endpoint exists."""
        from api.azure_mcp import router

        tools_routes = [r for r in router.routes if '/api/azure-mcp/tools' in r.path and 'search' not in r.path]
        assert len(tools_routes) >= 1

    def test_get_resource_groups_endpoint(self):
        """Test GET /api/azure-mcp/resource-groups endpoint exists."""
        from api.azure_mcp import router

        rg_routes = [r for r in router.routes if '/api/azure-mcp/resource-groups' in r.path]
        assert len(rg_routes) >= 1

    def test_get_storage_accounts_endpoint(self):
        """Test GET /api/azure-mcp/storage-accounts endpoint exists."""
        from api.azure_mcp import router

        storage_routes = [r for r in router.routes if '/api/azure-mcp/storage-accounts' in r.path]
        assert len(storage_routes) >= 1

    def test_get_resources_by_id_endpoint(self):
        """Test GET /api/azure-mcp/resources/{resource_id} endpoint exists."""
        from api.azure_mcp import router

        resource_routes = [r for r in router.routes if '/api/azure-mcp/resources' in r.path and '{resource_id' in r.path]
        assert len(resource_routes) >= 1

    def test_post_query_endpoint(self):
        """Test POST /api/azure-mcp/query endpoint exists."""
        from api.azure_mcp import router

        query_routes = [r for r in router.routes if '/api/azure-mcp/query' in r.path]
        assert len(query_routes) >= 1

    def test_get_tools_search_endpoint(self):
        """Test GET /api/azure-mcp/tools/search endpoint exists."""
        from api.azure_mcp import router

        search_routes = [r for r in router.routes if '/api/azure-mcp/tools/search' in r.path]
        assert len(search_routes) >= 1

    def test_post_call_tool_endpoint(self):
        """Test POST /api/azure-mcp/call-tool endpoint exists."""
        from api.azure_mcp import router

        call_routes = [r for r in router.routes if '/api/azure-mcp/call-tool' in r.path]
        assert len(call_routes) >= 1

    def test_post_inspect_plan_endpoint(self):
        """Test POST /api/azure-mcp/inspect-plan endpoint exists."""
        from api.azure_mcp import router

        plan_routes = [r for r in router.routes if '/api/azure-mcp/inspect-plan' in r.path]
        assert len(plan_routes) >= 1

    def test_post_chat_endpoint(self):
        """Test POST /api/azure-mcp/chat endpoint exists."""
        from api.azure_mcp import router

        chat_routes = [r for r in router.routes if '/api/azure-mcp/chat' in r.path and 'GET' not in str(r.methods)]
        assert len(chat_routes) >= 1

    def test_get_chat_history_endpoint(self):
        """Test GET /api/azure-mcp/chat/history endpoint exists."""
        from api.azure_mcp import router

        history_routes = [r for r in router.routes if '/api/azure-mcp/chat/history' in r.path]
        assert len(history_routes) >= 1

    def test_post_chat_clear_endpoint(self):
        """Test POST /api/azure-mcp/chat/clear endpoint exists."""
        from api.azure_mcp import router

        clear_routes = [r for r in router.routes if '/api/azure-mcp/chat/clear' in r.path]
        assert len(clear_routes) >= 1

    def test_get_agent_stream_endpoint(self):
        """Test GET /api/azure-mcp/agent-stream endpoint exists."""
        from api.azure_mcp import router

        stream_routes = [r for r in router.routes if '/api/azure-mcp/agent-stream' in r.path]
        assert len(stream_routes) >= 1


class TestAzureMCPRouterConfiguration:
    """Tests for Azure MCP router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.azure_mcp import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import azure_mcp

        assert hasattr(azure_mcp, 'StandardResponse')

    def test_decorators_imported(self):
        """Test endpoint decorators are imported."""
        from api import azure_mcp

        # Should have decorators imported
        assert hasattr(azure_mcp, 'readonly_endpoint') or hasattr(azure_mcp, 'write_endpoint')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import azure_mcp

        assert hasattr(azure_mcp, 'logger')

    def test_azure_mcp_client_imported(self):
        """Test get_azure_mcp_client is imported."""
        from api import azure_mcp

        assert hasattr(azure_mcp, 'get_azure_mcp_client')


@pytest.mark.asyncio
class TestAzureMCPHelperFunctions:
    """Tests for Azure MCP helper functions."""

    def test_orchestrator_disabled_function(self):
        """Test _orchestrator_disabled function exists."""
        from api import azure_mcp

        assert hasattr(azure_mcp, '_orchestrator_disabled')
        assert callable(azure_mcp._orchestrator_disabled)

    @patch.dict('os.environ', {'PYTEST_CURRENT_TEST': 'test'})
    def test_orchestrator_disabled_in_pytest(self):
        """Test orchestrator is disabled during pytest."""
        from api.azure_mcp import _orchestrator_disabled

        assert _orchestrator_disabled() is True

    @patch.dict('os.environ', {'DISABLE_MCP_ORCHESTRATOR': 'true'}, clear=True)
    def test_orchestrator_disabled_when_env_set(self):
        """Test orchestrator is disabled when env var set."""
        from api.azure_mcp import _orchestrator_disabled

        assert _orchestrator_disabled() is True

    @patch('api.azure_mcp.get_azure_mcp_client')
    async def test_load_composite_tool_catalog_fallback(self, mock_client):
        """Test _load_composite_tool_catalog uses fallback when orchestrator unavailable."""
        from api.azure_mcp import _load_composite_tool_catalog

        # Mock Azure MCP client
        mock_client_instance = AsyncMock()
        mock_client_instance.get_available_tools = MagicMock(return_value=[
            {
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {}
                }
            }
        ])
        mock_client.return_value = mock_client_instance

        # Call function
        result = await _load_composite_tool_catalog()

        # Verify fallback was used
        assert len(result) > 0
        assert result[0]["name"] == "test_tool"
        assert result[0]["source"] == "azure"


class TestAzureMCPModuleStructure:
    """Tests for Azure MCP module structure."""

    def test_module_has_required_imports(self):
        """Test Azure MCP module has required imports."""
        from api import azure_mcp

        # Check key imports exist
        assert hasattr(azure_mcp, 'APIRouter')
        assert hasattr(azure_mcp, 'HTTPException')
        assert hasattr(azure_mcp, 'BaseModel')

    def test_tool_call_request_model(self):
        """Test ToolCallRequest model exists."""
        from api.azure_mcp import ToolCallRequest

        # Create instance
        req = ToolCallRequest(tool_name="get_resource_groups")
        assert req.tool_name == "get_resource_groups"
        assert req.arguments == {}

    def test_resource_query_request_model(self):
        """Test ResourceQueryRequest model exists."""
        from api.azure_mcp import ResourceQueryRequest

        # Create instance
        req = ResourceQueryRequest(query="Resources | where type == 'Microsoft.Compute/virtualMachines'")
        assert "virtualMachines" in req.query
        assert req.cluster_uri is None
        assert req.database is None
