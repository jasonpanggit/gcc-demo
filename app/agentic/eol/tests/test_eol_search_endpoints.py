"""
Test Suite for EOL Search and Analysis Endpoints
Tests EOL date lookups and analysis functionality
"""
import pytest
from datetime import datetime
import os


# Skip EOL search tests if running locally (may need Azure OpenAI)
pytestmark = pytest.mark.skipif(
    os.getenv('USE_MOCK_DATA', 'true').lower() == 'true',
    reason="EOL search endpoints may require Azure OpenAI and external APIs"
)


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.eol
@pytest.mark.azure
class TestEOLSearchEndpoints:
    """Test EOL search and analysis endpoints (may require Azure services)"""
    
    @pytest.mark.asyncio
    async def test_search_eol_simple(self, client, test_software_name):
        """Test GET /api/eol/search - Simple EOL search"""
        response = await client.get(
            f"/api/eol/search",
            params={"product": test_software_name}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate StandardResponse format
        assert data['success'] is True
        assert 'data' in data
        assert isinstance(data['data'], list)
        
    @pytest.mark.asyncio
    async def test_search_eol_with_version(self, client, test_software_name, test_software_version):
        """Test GET /api/eol/search - EOL search with version"""
        response = await client.get(
            f"/api/eol/search",
            params={
                "product": test_software_name,
                "version": test_software_version
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_get_eol_status(self, client, test_software_name):
        """Test GET /api/eol/status - Get EOL status"""
        response = await client.get(
            f"/api/eol/status",
            params={"product": test_software_name}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
    @pytest.mark.asyncio
    async def test_analyze_eol_inventory(self, client):
        """Test GET /api/eol/analyze - Analyze inventory for EOL"""
        response = await client.get("/api/eol/analyze")
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'data' in data
        
        # Should return EOL analysis results
        if data['count'] > 0:
            result = data['data'][0]
            assert 'analysis' in result or 'eol_items' in result or 'summary' in result
