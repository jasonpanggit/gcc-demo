"""
Inventory API Router Tests

Tests for inventory management endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestInventoryRouterUnit:
    """Unit tests for inventory router without full app."""

    def test_inventory_router_imports(self):
        """Test inventory router can be imported."""
        from api.inventory import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_inventory_router_has_endpoints(self):
        """Test inventory router has expected endpoints."""
        from api.inventory import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have inventory endpoints
        assert any('/inventory' in path for path in paths)
        assert any('/os' in path for path in paths)

    def test_inventory_router_tags(self):
        """Test inventory router has correct tags."""
        from api.inventory import router

        assert hasattr(router, 'tags')
        # Should have Inventory-related tag
        tags_str = str(router.tags)
        assert "inventory" in tags_str.lower()

    def test_get_eol_orchestrator_helper(self):
        """Test _get_eol_orchestrator helper exists."""
        from api import inventory

        assert hasattr(inventory, '_get_eol_orchestrator')
        assert callable(inventory._get_eol_orchestrator)

    def test_inventory_endpoints_count(self):
        """Test inventory router has expected number of endpoints."""
        from api.inventory import router

        # Based on docstring: 8 endpoints total
        assert len(router.routes) >= 8


class TestInventoryEndpointSignatures:
    """Tests for inventory endpoint signatures."""

    def test_get_inventory_endpoint(self):
        """Test /api/inventory endpoint exists."""
        from api.inventory import router

        inventory_routes = [r for r in router.routes if '/api/inventory' in r.path and r.methods == {'GET'}]
        assert len(inventory_routes) >= 1

    def test_get_inventory_status_endpoint(self):
        """Test /api/inventory/status endpoint exists."""
        from api.inventory import router

        status_routes = [r for r in router.routes if '/api/inventory/status' in r.path]
        assert len(status_routes) >= 1

    def test_get_os_endpoint(self):
        """Test /api/os endpoint exists."""
        from api.inventory import router

        os_routes = [r for r in router.routes if '/api/os' in r.path and 'summary' not in r.path]
        assert len(os_routes) >= 1

    def test_get_os_summary_endpoint(self):
        """Test /api/os/summary endpoint exists."""
        from api.inventory import router

        summary_routes = [r for r in router.routes if '/api/os/summary' in r.path]
        assert len(summary_routes) >= 1

    def test_get_raw_software_endpoint(self):
        """Test /api/inventory/raw/software endpoint exists."""
        from api.inventory import router

        raw_sw_routes = [r for r in router.routes if '/api/inventory/raw/software' in r.path]
        assert len(raw_sw_routes) >= 1

    def test_get_raw_os_endpoint(self):
        """Test /api/inventory/raw/os endpoint exists."""
        from api.inventory import router

        raw_os_routes = [r for r in router.routes if '/api/inventory/raw/os' in r.path]
        assert len(raw_os_routes) >= 1

    def test_reload_inventory_endpoint(self):
        """Test /api/inventory/reload endpoint exists."""
        from api.inventory import router

        reload_routes = [r for r in router.routes if '/api/inventory/reload' in r.path]
        assert len(reload_routes) >= 1

    def test_clear_cache_endpoint(self):
        """Test /api/inventory/clear-cache endpoint exists."""
        from api.inventory import router

        clear_routes = [r for r in router.routes if '/api/inventory/clear-cache' in r.path]
        assert len(clear_routes) >= 1


class TestInventoryRouterConfiguration:
    """Tests for inventory router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.inventory import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import inventory

        assert hasattr(inventory, 'StandardResponse')

    def test_decorators_imported(self):
        """Test endpoint decorators are imported."""
        from api import inventory

        # Should have decorators imported
        assert hasattr(inventory, 'with_timeout_and_stats') or hasattr(inventory, 'readonly_endpoint')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import inventory

        assert hasattr(inventory, 'logger')


@pytest.mark.asyncio
class TestInventoryEndpointLogic:
    """Tests for inventory endpoint logic with mocking."""

    @patch('api.inventory._get_eol_orchestrator')
    async def test_get_inventory_calls_orchestrator(self, mock_get_orch):
        """Test get_inventory calls EOL orchestrator."""
        from api.inventory import get_inventory

        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.get_software_inventory = AsyncMock(return_value={
            "success": True,
            "data": [
                {
                    "computer": "TEST-SERVER",
                    "software_name": "Windows Server 2025",
                    "version": "2025",
                    "publisher": "Microsoft",
                    "eol_status": "active"
                }
            ],
            "count": 1
        })
        mock_get_orch.return_value = mock_orchestrator

        # Call endpoint
        result = await get_inventory(limit=100, days=30, use_cache=True)

        # Verify orchestrator was called
        mock_orchestrator.get_software_inventory.assert_called_once()
        assert result["success"] is True
        assert "data" in result

    @patch('api.inventory._get_eol_orchestrator')
    async def test_get_inventory_applies_limit(self, mock_get_orch):
        """Test get_inventory respects limit parameter."""
        from api.inventory import get_inventory

        # Mock orchestrator returning more records than limit
        mock_orchestrator = AsyncMock()
        mock_orchestrator.get_software_inventory = AsyncMock(return_value={
            "success": True,
            "data": [{"id": i} for i in range(1000)],
            "count": 1000
        })
        mock_get_orch.return_value = mock_orchestrator

        # Call with small limit
        result = await get_inventory(limit=5, days=30, use_cache=True)

        # Should apply limit
        assert len(result["data"]) <= 5


class TestInventoryModuleStructure:
    """Tests for inventory module structure."""

    def test_module_has_required_imports(self):
        """Test inventory module has required imports."""
        from api import inventory

        # Check key imports exist
        assert hasattr(inventory, 'APIRouter')
        assert hasattr(inventory, 'HTTPException')
        assert hasattr(inventory, 'config')

    def test_readonly_endpoint_decorator(self):
        """Test readonly endpoint decorator is available."""
        from api import inventory

        assert hasattr(inventory, 'readonly_endpoint') or hasattr(inventory, 'with_timeout_and_stats')

    def test_write_endpoint_decorator(self):
        """Test write endpoint decorator is available."""
        from api import inventory

        assert hasattr(inventory, 'write_endpoint') or hasattr(inventory, 'with_timeout_and_stats')
