"""
Alerts API Router Tests

Tests for alert management and notification endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestAlertsRouterUnit:
    """Unit tests for alerts router without full app."""

    def test_alerts_router_imports(self):
        """Test alerts router can be imported."""
        from api.alerts import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_alerts_router_has_endpoints(self):
        """Test alerts router has expected endpoints."""
        from api.alerts import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have alerts endpoints
        assert any('/alerts' in path for path in paths)

    def test_alerts_router_tags(self):
        """Test alerts router has correct tags."""
        from api.alerts import router

        assert hasattr(router, 'tags')
        # Should have Alert-related tag
        tags_str = str(router.tags)
        assert "alert" in tags_str.lower()

    def test_get_eol_orchestrator_helper(self):
        """Test _get_eol_orchestrator helper exists."""
        from api import alerts

        assert hasattr(alerts, '_get_eol_orchestrator')
        assert callable(alerts._get_eol_orchestrator)


class TestAlertsEndpointSignatures:
    """Tests for alerts endpoint signatures."""

    def test_get_alert_config_endpoint(self):
        """Test GET /api/alerts/config endpoint exists."""
        from api.alerts import router

        config_routes = [r for r in router.routes if '/api/alerts/config' in r.path and 'GET' in r.methods]
        assert len(config_routes) >= 1

    def test_post_alert_config_endpoint(self):
        """Test POST /api/alerts/config endpoint exists."""
        from api.alerts import router

        config_routes = [r for r in router.routes if '/api/alerts/config' in r.path and 'POST' in r.methods]
        assert len(config_routes) >= 1

    def test_reload_config_endpoint(self):
        """Test POST /api/alerts/config/reload endpoint exists."""
        from api.alerts import router

        reload_routes = [r for r in router.routes if '/api/alerts/config/reload' in r.path]
        assert len(reload_routes) >= 1

    def test_preview_alerts_endpoint(self):
        """Test GET /api/alerts/preview endpoint exists."""
        from api.alerts import router

        preview_routes = [r for r in router.routes if '/api/alerts/preview' in r.path]
        assert len(preview_routes) >= 1

    def test_smtp_test_endpoint(self):
        """Test POST /api/alerts/smtp/test endpoint exists."""
        from api.alerts import router

        smtp_routes = [r for r in router.routes if '/api/alerts/smtp/test' in r.path]
        assert len(smtp_routes) >= 1

    def test_send_alert_endpoint(self):
        """Test POST /api/alerts/send endpoint exists."""
        from api.alerts import router

        send_routes = [r for r in router.routes if '/api/alerts/send' in r.path and '/teams' not in r.path]
        assert len(send_routes) >= 1

    def test_teams_test_endpoint(self):
        """Test POST /api/alerts/send-teams-test endpoint exists."""
        from api.alerts import router

        teams_routes = [r for r in router.routes if '/api/alerts/send-teams-test' in r.path]
        assert len(teams_routes) >= 1

    def test_teams_bot_notification_endpoint(self):
        """Test POST /api/alerts/send-teams-bot-notification endpoint exists."""
        from api.alerts import router

        bot_routes = [r for r in router.routes if '/api/alerts/send-teams-bot-notification' in r.path]
        assert len(bot_routes) >= 1

    def test_teams_conversations_endpoint(self):
        """Test GET /api/alerts/teams-bot-conversations endpoint exists."""
        from api.alerts import router

        conv_routes = [r for r in router.routes if '/api/alerts/teams-bot-conversations' in r.path]
        assert len(conv_routes) >= 1


class TestAlertsRouterConfiguration:
    """Tests for alerts router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.alerts import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_standard_response_imported(self):
        """Test StandardResponse is imported."""
        from api import alerts

        assert hasattr(alerts, 'StandardResponse')

    def test_decorators_imported(self):
        """Test endpoint decorators are imported."""
        from api import alerts

        # Should have decorators imported
        assert hasattr(alerts, 'readonly_endpoint') or hasattr(alerts, 'write_endpoint')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import alerts

        assert hasattr(alerts, 'logger')


@pytest.mark.asyncio
class TestAlertsEndpointLogic:
    """Tests for alerts endpoint logic with mocking."""

    @patch('utils.alert_manager.alert_manager')
    async def test_get_alert_configuration_returns_config(self, mock_alert_mgr):
        """Test get_alert_configuration returns config."""
        from api.alerts import get_alert_configuration

        # Mock alert manager config
        mock_config = MagicMock()
        mock_config.dict = MagicMock(return_value={
            "smtp_settings": {
                "server": "smtp.example.com",
                "port": 587,
                "password": "secret"
            },
            "email_recipients": ["test@example.com"]
        })
        mock_alert_mgr.load_configuration = AsyncMock(return_value=mock_config)

        # Call endpoint
        result = await get_alert_configuration()

        # Verify response (result is a dict with 'success' key)
        assert result["success"] is True
        assert len(result["data"]) > 0
        # Password should be masked
        assert result["data"][0]["configuration"]["smtp_settings"]["password"] == "***"

    @patch('utils.alert_manager.alert_manager')
    async def test_get_alert_configuration_handles_missing_recipients(self, mock_alert_mgr):
        """Test get_alert_configuration handles missing recipients."""
        from api.alerts import get_alert_configuration

        # Mock alert manager with no recipients
        mock_config = MagicMock()
        mock_config.dict = MagicMock(return_value={
            "smtp_settings": {
                "server": "smtp.example.com",
                "port": 587
            }
        })
        mock_alert_mgr.load_configuration = AsyncMock(return_value=mock_config)

        # Call endpoint
        result = await get_alert_configuration()

        # Verify source is "local" when no recipients
        assert result["success"] is True
        assert result["data"][0]["source"] == "local"


class TestAlertsModuleStructure:
    """Tests for alerts module structure."""

    def test_module_has_required_imports(self):
        """Test alerts module has required imports."""
        from api import alerts

        # Check key imports exist
        assert hasattr(alerts, 'APIRouter')
        assert hasattr(alerts, 'HTTPException')
        assert hasattr(alerts, 'datetime')

    def test_readonly_endpoint_decorator(self):
        """Test readonly endpoint decorator is available."""
        from api import alerts

        assert hasattr(alerts, 'readonly_endpoint')

    def test_write_endpoint_decorator(self):
        """Test write endpoint decorator is available."""
        from api import alerts

        assert hasattr(alerts, 'write_endpoint')

    def test_get_alert_configuration_function_exists(self):
        """Test get_alert_configuration function exists."""
        from api import alerts

        assert hasattr(alerts, 'get_alert_configuration')
        assert callable(alerts.get_alert_configuration)
