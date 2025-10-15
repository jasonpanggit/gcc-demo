"""
Test Suite for Cache Management Endpoints
Tests cache operations, status, and statistics
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.cache
class TestCacheEndpoints:
    """Test cache management endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_cache_status(self, client):
        """Test GET /api/cache/status - Get cache status"""
        response = await client.get("/api/cache/status")
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        assert data['count'] > 0
        
        # Validate cache status structure (complex nested dict)
        cache_status = data['data'][0]
        assert isinstance(cache_status, dict)
        
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, client):
        """Test GET /api/cache/stats - Get cache statistics"""
        response = await client.get("/api/cache/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_cache_size(self, client):
        """Test GET /api/cache/size - Get cache size"""
        response = await client.get("/api/cache/size")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_clear_cache(self, client):
        """Test POST /api/cache/clear - Clear all cache"""
        response = await client.post("/api/cache/clear")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_clear_cache_by_key(self, client):
        """Test POST /api/cache/clear/{key} - Clear specific cache key"""
        response = await client.post("/api/cache/clear/test_key")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_cache_keys(self, client):
        """Test GET /api/cache/keys - Get all cache keys"""
        response = await client.get("/api/cache/keys")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    @pytest.mark.asyncio
    async def test_get_cache_entry(self, client):
        """Test GET /api/cache/entry/{key} - Get specific cache entry"""
        response = await client.get("/api/cache/entry/test_key")
        # May return 404 if key doesn't exist, which is valid
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data
            
    @pytest.mark.asyncio
    async def test_refresh_cache(self, client):
        """Test POST /api/cache/refresh - Refresh cache"""
        response = await client.post("/api/cache/refresh")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_cache_hit_rate(self, client):
        """Test GET /api/cache/hit-rate - Get cache hit rate"""
        response = await client.get("/api/cache/hit-rate")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_cache_ttl(self, client):
        """Test GET /api/cache/ttl/{key} - Get cache TTL"""
        response = await client.get("/api/cache/ttl/test_key")
        # May return 404 if key doesn't exist
        assert response.status_code in [200, 404]
        
    @pytest.mark.asyncio
    async def test_set_cache_ttl(self, client):
        """Test POST /api/cache/ttl/{key} - Set cache TTL"""
        response = await client.post(
            "/api/cache/ttl/test_key",
            params={"ttl": 300}
        )
        assert response.status_code in [200, 404]
        
    @pytest.mark.asyncio
    async def test_get_cached_items(self, client):
        """Test GET /api/cache/items - Get cached items"""
        response = await client.get("/api/cache/items")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_export_cache(self, client):
        """Test GET /api/cache/export - Export cache data"""
        response = await client.get("/api/cache/export")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_import_cache(self, client):
        """Test POST /api/cache/import - Import cache data"""
        cache_data = {
            "test_key": {
                "value": "test_value",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        response = await client.post("/api/cache/import", json=cache_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_get_cache_health(self, client):
        """Test GET /api/cache/health - Get cache health"""
        response = await client.get("/api/cache/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
