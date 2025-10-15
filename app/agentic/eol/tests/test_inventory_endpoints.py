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
        """Test GET /api/inventory/software - Get software inventory"""
        response = await client.get("/api/inventory/software")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] > 0
        assert 'timestamp' in data
        assert 'metadata' in data
        
        # Validate software item structure
        if data['count'] > 0:
            item = data['data'][0]
            assert 'software_name' in item
            assert 'version' in item
            assert 'device_name' in item
            
    @pytest.mark.asyncio
    async def test_get_os_inventory(self, client):
        """Test GET /api/inventory/os - Get OS inventory"""
        response = await client.get("/api/inventory/os")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] > 0
        
        # Validate OS item structure
        if data['count'] > 0:
            item = data['data'][0]
            assert 'os_name' in item or 'device_name' in item
            
    @pytest.mark.asyncio
    async def test_get_software_summary(self, client):
        """Test GET /api/inventory/software/summary - Get software summary"""
        response = await client.get("/api/inventory/software/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        summary = data['data'][0]
        assert 'total_software' in summary or 'summary' in summary
        
    @pytest.mark.asyncio
    async def test_get_os_summary(self, client):
        """Test GET /api/inventory/os/summary - Get OS summary"""
        response = await client.get("/api/inventory/os/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_software_by_name(self, client, test_software_name):
        """Test GET /api/inventory/software/{name} - Get software by name"""
        response = await client.get(f"/api/inventory/software/{test_software_name}")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_os_by_name(self, client):
        """Test GET /api/inventory/os/{name} - Get OS by name"""
        os_name = "Windows"
        response = await client.get(f"/api/inventory/os/{os_name}")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_inventory_stats(self, client):
        """Test GET /api/inventory/stats - Get inventory statistics"""
        response = await client.get("/api/inventory/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        stats = data['data'][0]
        assert 'software_count' in stats or 'os_count' in stats or 'stats' in stats
        
    @pytest.mark.asyncio
    async def test_get_combined_inventory(self, client):
        """Test GET /api/inventory/combined - Get combined inventory"""
        response = await client.get("/api/inventory/combined")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
