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
        """Test GET / - Root endpoint"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] >= 1
        assert 'timestamp' in data
        
        # Validate content
        info = data['data'][0]
        assert info['application'] == "EOL Multi-Agent App"
        assert 'version' in info
        
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test GET /health - Health check"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert data['count'] >= 1
        
        # Validate health status
        health = data['data'][0]
        assert health['status'] == "healthy"
        assert 'timestamp' in health
        
    @pytest.mark.asyncio
    async def test_api_health_endpoint(self, client):
        """Test GET /api/health - API health check"""
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        health = data['data'][0]
        assert health['status'] == "healthy"
        assert 'version' in health
        
    @pytest.mark.asyncio
    async def test_api_status_endpoint(self, client):
        """Test GET /api/status - API status"""
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        status = data['data'][0]
        assert 'uptime_seconds' in status
        assert 'agents_status' in status
        
    @pytest.mark.asyncio
    async def test_api_info_endpoint(self, client):
        """Test GET /api/info - API information"""
        response = await client.get("/api/info")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        info = data['data'][0]
        assert 'application' in info
        assert 'version' in info
        assert 'endpoints' in info
