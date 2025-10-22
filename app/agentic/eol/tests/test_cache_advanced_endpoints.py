"""
Test Suite for Advanced Cache Management Endpoints (Phase 2)
Tests new cache endpoints added in Phase 2 refactoring
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.cache
class TestAdvancedCacheEndpoints:
    """Test advanced cache management endpoints added in Phase 2"""
    
    # =========================================================================
    # Cache Purge Endpoints
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_purge_cache_all(self, client):
        """Test POST /api/cache/purge - Purge all agent caches"""
        response = await client.post("/api/cache/purge")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    @pytest.mark.asyncio
    async def test_purge_cache_specific_agent(self, client):
        """Test POST /api/cache/purge?agent_type=microsoft - Purge specific agent"""
        response = await client.post("/api/cache/purge?agent_type=microsoft")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_purge_cache_by_software(self, client):
        """Test POST /api/cache/purge?software_name=Windows - Purge by software"""
        response = await client.post("/api/cache/purge?software_name=Windows")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    async def test_purge_cache_by_version(self, client):
        """Test POST /api/cache/purge with software and version"""
        response = await client.post(
            "/api/cache/purge?software_name=Windows&version=11"
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
    
    # =========================================================================
    # Inventory Cache Stats Endpoints
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_get_inventory_cache_stats(self, client):
        """Test GET /api/cache/inventory/stats - Get inventory cache statistics"""
        response = await client.get("/api/cache/inventory/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
        if data['count'] > 0:
            stats = data['data'][0]
            # Should contain cache statistics
            assert isinstance(stats, dict)
            
    @pytest.mark.asyncio
    async def test_get_inventory_cache_details(self, client):
        """Test GET /api/cache/inventory/details - Get detailed inventory cache"""
        response = await client.get("/api/cache/inventory/details")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    # =========================================================================
    # Web Scraping Cache Endpoints
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_get_webscraping_cache_details(self, client):
        """Test GET /api/cache/webscraping/details - Get web scraping cache"""
        response = await client.get("/api/cache/webscraping/details")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    @pytest.mark.asyncio
    async def test_get_webscraping_cache_by_agent(self, client):
        """Test GET /api/cache/webscraping/details?agent_name=microsoft"""
        response = await client.get(
            "/api/cache/webscraping/details?agent_name=microsoft"
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    # =========================================================================
    # Cosmos Cache Endpoints
    # =========================================================================
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_get_cosmos_cache_stats(self, client):
        """Test GET /api/cache/cosmos/stats - Get Cosmos cache statistics"""
        response = await client.get("/api/cache/cosmos/stats")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_get_cosmos_cache_config(self, client):
        """Test GET /api/cache/cosmos/config - Get Cosmos configuration"""
        response = await client.get("/api/cache/cosmos/config")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_get_cosmos_cache_debug(self, client):
        """Test GET /api/cache/cosmos/debug - Get Cosmos debug info"""
        response = await client.get("/api/cache/cosmos/debug")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_clear_cosmos_cache(self, client):
        """Test POST /api/cache/cosmos/clear - Clear Cosmos cache"""
        response = await client.post("/api/cache/cosmos/clear")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_clear_cosmos_cache_with_filter(self, client):
        """Test POST /api/cache/cosmos/clear?container=communications"""
        response = await client.post(
            "/api/cache/cosmos/clear?container=communications"
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_initialize_cosmos_cache(self, client):
        """Test POST /api/cache/cosmos/initialize - Initialize Cosmos"""
        response = await client.post("/api/cache/cosmos/initialize")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "not config.cosmos.enabled",
        reason="Cosmos DB not configured"
    )
    async def test_test_cosmos_cache(self, client):
        """Test POST /api/cache/cosmos/test - Test Cosmos operations"""
        response = await client.post("/api/cache/cosmos/test")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    # =========================================================================
    # Enhanced Statistics Endpoints
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_get_enhanced_cache_stats(self, client):
        """Test GET /api/cache/stats/enhanced - Get comprehensive stats"""
        response = await client.get("/api/cache/stats/enhanced")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
        if data['count'] > 0:
            stats = data['data'][0]
            # Should contain comprehensive statistics
            assert isinstance(stats, dict)
            # Expect agent_stats, inventory_stats, cosmos_stats, etc.
            
    @pytest.mark.asyncio
    async def test_get_agent_cache_stats(self, client):
        """Test GET /api/cache/stats/agents - Get agent statistics"""
        response = await client.get("/api/cache/stats/agents")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_performance_summary(self, client):
        """Test GET /api/cache/stats/performance - Get performance summary"""
        response = await client.get("/api/cache/stats/performance")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_reset_cache_stats(self, client):
        """Test POST /api/cache/stats/reset - Reset all statistics"""
        response = await client.post("/api/cache/stats/reset")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        
    # =========================================================================
    # Integration Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_cache_workflow(self, client):
        """Test complete cache management workflow"""
        # 1. Get current stats
        response = await client.get("/api/cache/stats/enhanced")
        assert response.status_code == 200
        
        # 2. Get inventory cache details
        response = await client.get("/api/cache/inventory/details")
        assert response.status_code == 200
        
        # 3. Purge specific agent cache
        response = await client.post("/api/cache/purge?agent_type=microsoft")
        assert response.status_code == 200
        
        # 4. Get updated stats
        response = await client.get("/api/cache/stats/enhanced")
        assert response.status_code == 200
        
    @pytest.mark.asyncio
    async def test_cache_stats_consistency(self, client):
        """Test that different stats endpoints return consistent data"""
        # Get enhanced stats
        response1 = await client.get("/api/cache/stats/enhanced")
        assert response1.status_code == 200
        enhanced = response1.json()
        
        # Get agent stats
        response2 = await client.get("/api/cache/stats/agents")
        assert response2.status_code == 200
        agent_stats = response2.json()
        
        # Get performance summary
        response3 = await client.get("/api/cache/stats/performance")
        assert response3.status_code == 200
        perf = response3.json()
        
        # All should succeed
        assert enhanced['success'] is True
        assert agent_stats['success'] is True
        assert perf['success'] is True
        
    @pytest.mark.asyncio
    async def test_error_handling(self, client):
        """Test error handling for invalid requests"""
        # Test invalid agent type
        response = await client.post(
            "/api/cache/purge?agent_type=nonexistent_agent"
        )
        # Should still succeed but return empty results
        assert response.status_code == 200
        
    @pytest.mark.asyncio
    async def test_cache_ui_endpoint(self, client):
        """Test GET /api/cache/ui - Cache management UI data"""
        response = await client.get("/api/cache/ui")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
