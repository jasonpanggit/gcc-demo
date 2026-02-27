"""
Metrics API Router Tests

Tests for metrics and observability endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestMetricsRouterUnit:
    """Unit tests for metrics router without full app."""

    def test_metrics_router_imports(self):
        """Test metrics router can be imported."""
        from api.metrics import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_metrics_router_has_endpoints(self):
        """Test metrics router has expected endpoints."""
        from api.metrics import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have metrics endpoints
        assert any('/metrics' in path for path in paths)

    def test_metrics_router_tags(self):
        """Test metrics router has correct tags."""
        from api.metrics import router

        assert hasattr(router, 'tags')
        # Should have metrics-related tag
        tags_str = str(router.tags)
        assert "metrics" in tags_str.lower()

    def test_metrics_router_prefix(self):
        """Test metrics router has correct prefix."""
        from api.metrics import router

        # Should have /api prefix
        assert router.prefix == "/api"


class TestMetricsEndpointSignatures:
    """Tests for metrics endpoint signatures."""

    def test_get_metrics_endpoint(self):
        """Test GET /api/metrics endpoint exists."""
        from api.metrics import router

        metrics_routes = [r for r in router.routes if '/metrics' in r.path and 'GET' in r.methods]
        assert len(metrics_routes) >= 1

    def test_reset_metrics_endpoint(self):
        """Test POST /api/metrics/reset endpoint exists."""
        from api.metrics import router

        reset_routes = [r for r in router.routes if '/metrics/reset' in r.path and 'POST' in r.methods]
        assert len(reset_routes) >= 1


class TestMetricsRouterConfiguration:
    """Tests for metrics router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.metrics import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import metrics

        assert hasattr(metrics, 'StandardResponse')

    def test_metrics_collector_imported(self):
        """Test metrics_collector is imported."""
        from api import metrics

        assert hasattr(metrics, 'metrics_collector')


@pytest.mark.asyncio
class TestMetricsEndpointLogic:
    """Tests for metrics endpoint logic with mocking."""

    @patch('api.metrics.metrics_collector')
    async def test_get_metrics_returns_data(self, mock_collector):
        """Test get_metrics returns metrics data."""
        from api.metrics import get_metrics

        # Mock metrics collector
        mock_collector.get_all_metrics = MagicMock(return_value={
            "counters": {
                "requests_total": 100,
                "errors_total": 5
            },
            "histograms": {
                "request_duration_ms": {
                    "count": 100,
                    "mean": 150.5
                }
            }
        })

        # Call endpoint
        result = await get_metrics()

        # Verify response
        assert result.success is True
        assert len(result.data) == 1
        assert "counters" in result.data[0]
        assert "histograms" in result.data[0]
        mock_collector.get_all_metrics.assert_called_once()

    @patch('api.metrics.metrics_collector')
    async def test_get_metrics_handles_error(self, mock_collector):
        """Test get_metrics handles errors gracefully."""
        from api.metrics import get_metrics

        # Mock metrics collector to raise error
        mock_collector.get_all_metrics = MagicMock(side_effect=Exception("Test error"))

        # Call endpoint
        result = await get_metrics()

        # Verify error response
        assert result.success is False
        assert len(result.data) == 0
        assert "Failed to retrieve metrics" in result.error

    @patch('api.metrics.metrics_collector')
    async def test_reset_metrics_resets_data(self, mock_collector):
        """Test reset_metrics resets collector."""
        from api.metrics import reset_metrics

        # Mock metrics collector
        mock_collector.reset = MagicMock()

        # Call endpoint
        result = await reset_metrics()

        # Verify reset was called
        mock_collector.reset.assert_called_once()
        assert result.success is True
        assert result.data[0]["message"] == "Metrics reset successfully"

    @patch('api.metrics.metrics_collector')
    async def test_reset_metrics_handles_error(self, mock_collector):
        """Test reset_metrics handles errors gracefully."""
        from api.metrics import reset_metrics

        # Mock metrics collector to raise error
        mock_collector.reset = MagicMock(side_effect=Exception("Reset failed"))

        # Call endpoint
        result = await reset_metrics()

        # Verify error response
        assert result.success is False
        assert "Failed to reset metrics" in result.error


class TestMetricsModuleStructure:
    """Tests for metrics module structure."""

    def test_module_has_required_imports(self):
        """Test metrics module has required imports."""
        from api import metrics

        # Check key imports exist
        assert hasattr(metrics, 'APIRouter')
        assert hasattr(metrics, 'metrics_collector')

    def test_get_metrics_function_exists(self):
        """Test get_metrics function exists."""
        from api import metrics

        assert hasattr(metrics, 'get_metrics')
        assert callable(metrics.get_metrics)

    def test_reset_metrics_function_exists(self):
        """Test reset_metrics function exists."""
        from api import metrics

        assert hasattr(metrics, 'reset_metrics')
        assert callable(metrics.reset_metrics)
