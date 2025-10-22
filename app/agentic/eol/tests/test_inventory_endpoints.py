"""
Test Suite for Inventory Endpoints
Tests software and OS inventory retrieval endpoints
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.inventory
class TestInventoryEndpoints:
    """Test inventory management endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_software_inventory(self, client):
        """Test GET /api/inventory - Get software inventory"""
        response = await client.get("/api/inventory?days=7")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] > 0
        assert 'timestamp' in data
        
        # Validate software item structure
        if data['count'] > 0:
            item = data['data'][0]
            assert 'name' in item or 'software_name' in item
            assert 'version' in item
            assert 'computer' in item or 'device_name' in item
            
    @pytest.mark.asyncio
    async def test_get_os_inventory(self, client):
        """Test GET /api/os - Get OS inventory"""
        response = await client.get("/api/os?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] > 0
        
        # Validate OS item structure
        if data['count'] > 0:
            item = data['data'][0]
            assert 'OSName' in item or 'os_name' in item or 'name' in item
            
    @pytest.mark.asyncio
    async def test_get_software_summary(self, client):
        """Test GET /api/inventory/status - Get inventory status/summary"""
        response = await client.get("/api/inventory/status?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        # Summary contains summary information
        summary = data['data'][0] if isinstance(data['data'], list) else data['data']
        assert 'summary' in summary or 'total' in str(summary).lower()
        
    @pytest.mark.asyncio
    async def test_get_os_summary(self, client):
        """Test GET /api/os/summary - Get OS summary"""
        response = await client.get("/api/os/summary?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_software_by_name(self, client, test_software_name):
        """Test GET /api/inventory/raw/software - Get raw software inventory"""
        response = await client.get("/api/inventory/raw/software?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_os_by_name(self, client):
        """Test GET /api/inventory/raw/os - Get raw OS inventory"""
        response = await client.get("/api/inventory/raw/os?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_inventory_stats(self, client):
        """Test GET /api/inventory/status - Get inventory statistics/status"""
        response = await client.get("/api/inventory/status?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_combined_inventory(self, client):
        """Test GET /api/inventory - Get inventory (combined)"""
        response = await client.get("/api/inventory?days=7")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert data['count'] > 0
