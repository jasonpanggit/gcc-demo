"""
Test Suite for Health and Status Endpoints
Tests basic health check and application status endpoints
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
class TestHealthEndpoints:
    """Test health and status endpoints"""
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Test GET / - Root endpoint (returns HTML dashboard)"""
        response = await client.get("/")
        assert response.status_code == 200
        # Root endpoint returns HTML, not JSON
        assert 'text/html' in response.headers.get('content-type', '')
        
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test GET /health - Health check"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        # Validate simple health response format (not StandardResponse)
        assert data['status'] == "ok"
        assert 'timestamp' in data
        assert 'version' in data
        assert isinstance(data['autogen_available'], bool)
        
    @pytest.mark.asyncio
    async def test_api_health_endpoint(self, client):
        """Test GET /api/health - API health check (endpoint does not exist)"""
        response = await client.get("/api/health")
        # This endpoint doesn't exist in the new API structure
        # Health check is at /health instead
        assert response.status_code == 404
        
    @pytest.mark.asyncio
    async def test_api_status_endpoint(self, client):
        """Test GET /api/status - API status"""
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] >= 1
        
        status = data['data'][0]
        assert status['status'] == "running"
        assert 'version' in status
        assert status['message'] == "EOL Multi-Agent App"
        
    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client):
        """Test GET /api/info - API information (endpoint does not exist)"""
        response = await client.get("/api/info")
        # This endpoint doesn't exist in the new API structure
        assert response.status_code == 404
