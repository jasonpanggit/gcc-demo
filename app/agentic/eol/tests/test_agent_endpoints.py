"""
Test Suite for Agent Management Endpoints
Tests agent status, configuration, and control endpoints
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
class TestAgentEndpoints:
    """Test agent management endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_agents_status(self, client):
        """Test GET /api/agents/status - Get all agents status"""
        response = await client.get("/api/agents/status")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
        # Validate agent status structure
        if data['count'] > 0:
            agent_status = data['data'][0]
            assert isinstance(agent_status, dict)
            
    @pytest.mark.asyncio
    async def test_get_agent_status(self, client):
        """Test GET /api/agents/{name}/status - Get specific agent status"""
        agent_name = "software_inventory"
        response = await client.get(f"/api/agents/{agent_name}/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_reload_agent(self, client):
        """Test POST /api/agents/{name}/reload - Reload specific agent"""
        agent_name = "software_inventory"
        response = await client.post(f"/api/agents/{agent_name}/reload")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_agent_config(self, client):
        """Test GET /api/agents/{name}/config - Get agent configuration"""
        agent_name = "software_inventory"
        response = await client.get(f"/api/agents/{agent_name}/config")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_update_agent_config(self, client):
        """Test POST /api/agents/{name}/config - Update agent configuration"""
        agent_name = "software_inventory"
        config = {
            "enabled": True,
            "timeout": 30
        }
        response = await client.post(f"/api/agents/{agent_name}/config", json=config)
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
