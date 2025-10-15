"""
Test Suite for Communication Endpoints
Tests email, notifications, and communication endpoints
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
class TestCommunicationEndpoints:
    """Test communication endpoints"""
    
    @pytest.mark.asyncio
    async def test_send_email(self, client):
        """Test POST /api/communications/email - Send email"""
        email_data = {
            "to": "test@example.com",
            "subject": "Test Email",
            "body": "This is a test email"
        }
        response = await client.post("/api/communications/email", json=email_data)
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_email_config(self, client):
        """Test GET /api/communications/email/config - Get email configuration"""
        response = await client.get("/api/communications/email/config")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_update_email_config(self, client):
        """Test POST /api/communications/email/config - Update email config"""
        config_data = {
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "use_tls": True
        }
        response = await client.post("/api/communications/email/config", json=config_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_send_notification(self, client):
        """Test POST /api/communications/notify - Send notification"""
        notification_data = {
            "message": "Test notification",
            "priority": "high"
        }
        response = await client.post("/api/communications/notify", json=notification_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_notifications(self, client):
        """Test GET /api/communications/notifications - Get notifications"""
        response = await client.get("/api/communications/notifications")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_communication_history(self, client):
        """Test GET /api/communications/history - Get communication history"""
        response = await client.get("/api/communications/history")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
