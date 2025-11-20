"""
Test Suite for Alert Management Endpoints
Tests alert configuration and notification endpoints
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.alerts
class TestAlertEndpoints:
    """Test alert management endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_alerts(self, client):
        """Test GET /api/alerts - Get all alerts (endpoint removed)"""
        response = await client.get("/api/alerts")
        # Endpoint doesn't exist in new API structure
        assert response.status_code == 404
        
    @pytest.mark.asyncio
    async def test_get_alert_config(self, client):
        """Test GET /api/alerts/config - Get alert configuration (has validation error)"""
        response = await client.get("/api/alerts/config")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert isinstance(data.get("data"), list)
        assert data.get("count", 0) == len(data.get("data", []))

        config_wrapper = data["data"][0]
        assert "configuration" in config_wrapper
        configuration = config_wrapper["configuration"]
        assert "smtp_settings" in configuration
        assert configuration["smtp_settings"].get("password") == "***"
        
    @pytest.mark.asyncio
    async def test_update_alert_config(self, client, test_alert_config):
        """Test POST /api/alerts/config - Update alert configuration"""
        response = await client.post("/api/alerts/config", json=test_alert_config)
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_send_test_alert(self, client):
        """Test POST /api/alerts/test - Send test alert (endpoint removed)"""
        response = await client.post("/api/alerts/test")
        # Endpoint doesn't exist - actual endpoint is /api/alerts/smtp/test
        assert response.status_code == 404
        
    @pytest.mark.asyncio
    async def test_get_alert_history(self, client):
        """Test GET /api/alerts/history - Get alert history (endpoint removed)"""
        response = await client.get("/api/alerts/history")
        # Endpoint doesn't exist in new API structure
        assert response.status_code == 404
        
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, client):
        """Test POST /api/alerts/{id}/acknowledge - Acknowledge alert (endpoint removed)"""
        alert_id = "test-alert-123"
        response = await client.post(f"/api/alerts/{alert_id}/acknowledge")
        # Endpoint doesn't exist in new API structure
        assert response.status_code == 404
