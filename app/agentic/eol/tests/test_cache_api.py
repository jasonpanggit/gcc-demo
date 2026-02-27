"""
Cache API Router Tests

Tests for cache management endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestCacheRouterUnit:
    """Unit tests for cache router without full app."""

    def test_cache_router_imports(self):
        """Test cache router can be imported."""
        from api.cache import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_cache_router_has_endpoints(self):
        """Test cache router has expected endpoints."""
        from api.cache import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have cache endpoints
        assert any('/cache' in path for path in paths)

    def test_cache_router_tags(self):
        """Test cache router has correct tags."""
        from api.cache import router

        assert hasattr(router, 'tags')
        # Should have Cache-related tag
        tags_str = str(router.tags)
        assert "cache" in tags_str.lower()

    def test_cache_router_endpoint_count(self):
        """Test cache router has expected number of endpoints."""
        from api.cache import router

        # Based on docstring: 17+ endpoints
        assert len(router.routes) >= 10


class TestCacheEndpointSignatures:
    """Tests for cache endpoint signatures."""

    def test_get_cache_status_endpoint(self):
        """Test /api/cache/status endpoint exists."""
        from api.cache import router

        status_routes = [r for r in router.routes if '/api/cache/status' in r.path]
        assert len(status_routes) >= 1

    def test_get_cache_ui_endpoint(self):
        """Test /api/cache/ui endpoint exists."""
        from api.cache import router

        ui_routes = [r for r in router.routes if '/api/cache/ui' in r.path]
        assert len(ui_routes) >= 1

    def test_clear_cache_endpoint(self):
        """Test /api/cache/clear endpoint exists."""
        from api.cache import router

        clear_routes = [r for r in router.routes if '/api/cache/clear' in r.path]
        assert len(clear_routes) >= 1

    def test_purge_cache_endpoint(self):
        """Test /api/cache/purge endpoint exists."""
        from api.cache import router

        purge_routes = [r for r in router.routes if '/api/cache/purge' in r.path]
        assert len(purge_routes) >= 1

    def test_inventory_stats_endpoint(self):
        """Test /api/cache/inventory/stats endpoint exists."""
        from api.cache import router

        inv_stats_routes = [r for r in router.routes if '/api/cache/inventory/stats' in r.path]
        assert len(inv_stats_routes) >= 1

    def test_inventory_details_endpoint(self):
        """Test /api/cache/inventory/details endpoint exists."""
        from api.cache import router

        inv_details_routes = [r for r in router.routes if '/api/cache/inventory/details' in r.path]
        assert len(inv_details_routes) >= 1

    def test_webscraping_details_endpoint(self):
        """Test /api/cache/webscraping/details endpoint exists."""
        from api.cache import router

        webscraping_routes = [r for r in router.routes if '/api/cache/webscraping/details' in r.path]
        assert len(webscraping_routes) >= 1

    def test_cosmos_stats_endpoint(self):
        """Test /api/cache/cosmos/stats endpoint exists."""
        from api.cache import router

        cosmos_stats_routes = [r for r in router.routes if '/api/cache/cosmos/stats' in r.path]
        assert len(cosmos_stats_routes) >= 1

    def test_cosmos_clear_endpoint(self):
        """Test /api/cache/cosmos/clear endpoint exists."""
        from api.cache import router

        cosmos_clear_routes = [r for r in router.routes if '/api/cache/cosmos/clear' in r.path]
        assert len(cosmos_clear_routes) >= 1

    def test_cosmos_initialize_endpoint(self):
        """Test /api/cache/cosmos/initialize endpoint exists."""
        from api.cache import router

        cosmos_init_routes = [r for r in router.routes if '/api/cache/cosmos/initialize' in r.path]
        assert len(cosmos_init_routes) >= 1


class TestCacheRouterConfiguration:
    """Tests for cache router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.cache import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import cache

        assert hasattr(cache, 'StandardResponse')

    def test_decorators_imported(self):
        """Test endpoint decorators are imported."""
        from api import cache

        # Should have decorators imported
        assert hasattr(cache, 'with_timeout_and_stats') or hasattr(cache, 'readonly_endpoint')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import cache

        assert hasattr(cache, 'logger')

    def test_cache_stats_manager_imported(self):
        """Test cache_stats_manager is imported."""
        from api import cache

        assert hasattr(cache, 'cache_stats_manager')


@pytest.mark.asyncio
class TestCacheEndpointLogic:
    """Tests for cache endpoint logic with mocking."""

    @patch('main.get_eol_orchestrator')
    @patch('utils.inventory_cache.inventory_cache')
    async def test_get_cache_status_calls_orchestrator(self, mock_inv_cache, mock_get_orch):
        """Test get_cache_status calls EOL orchestrator."""
        from api.cache import get_cache_status

        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.get_cache_status = AsyncMock(return_value={
            "success": True,
            "data": {
                "agents_with_cache": [
                    {
                        "name": "microsoft_agent",
                        "cache_count": 10
                    }
                ]
            }
        })
        mock_get_orch.return_value = mock_orchestrator

        # Mock inventory cache
        mock_inv_cache.get_cache_stats = MagicMock(return_value={
            "cached": True,
            "items_count": 50
        })

        # Call endpoint
        result = await get_cache_status()

        # Verify orchestrator was called
        mock_orchestrator.get_cache_status.assert_called_once()
        assert result["success"] is True


class TestCacheModuleStructure:
    """Tests for cache module structure."""

    def test_module_has_required_imports(self):
        """Test cache module has required imports."""
        from api import cache

        # Check key imports exist
        assert hasattr(cache, 'APIRouter')
        assert hasattr(cache, 'datetime')

    def test_readonly_endpoint_decorator(self):
        """Test readonly endpoint decorator is available."""
        from api import cache

        assert hasattr(cache, 'readonly_endpoint') or hasattr(cache, 'with_timeout_and_stats')

    def test_write_endpoint_decorator(self):
        """Test write endpoint decorator is available."""
        from api import cache

        assert hasattr(cache, 'write_endpoint') or hasattr(cache, 'with_timeout_and_stats')
