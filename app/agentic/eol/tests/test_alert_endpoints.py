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
        """Test GET /api/alerts - Get all alerts"""
        response = await client.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    @pytest.mark.asyncio
    async def test_get_alert_config(self, client):
        """Test GET /api/alerts/config - Get alert configuration"""
        response = await client.get("/api/alerts/config")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
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
        """Test POST /api/alerts/test - Send test alert"""
        response = await client.post("/api/alerts/test")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_alert_history(self, client):
        """Test GET /api/alerts/history - Get alert history"""
        response = await client.get("/api/alerts/history")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, client):
        """Test POST /api/alerts/{id}/acknowledge - Acknowledge alert"""
        alert_id = "test-alert-123"
        response = await client.post(f"/api/alerts/{alert_id}/acknowledge")
        # May return 404 if alert doesn't exist
        assert response.status_code in [200, 404]
