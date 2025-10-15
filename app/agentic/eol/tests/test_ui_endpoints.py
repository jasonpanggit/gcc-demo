"""
Test Suite for UI/HTML Endpoints
Tests HTML page rendering endpoints
"""
import pytest


@pytest.mark.ui
@pytest.mark.integration
class TestUIEndpoints:
    """Test UI/HTML rendering endpoints"""
    
    @pytest.mark.asyncio
    async def test_dashboard_page(self, client):
        """Test GET /dashboard - Main dashboard page"""
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_inventory_page(self, client):
        """Test GET /inventory - Inventory page"""
        response = await client.get("/inventory")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_eol_search_page(self, client):
        """Test GET /eol-search - EOL search page"""
        response = await client.get("/eol-search")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_alerts_page(self, client):
        """Test GET /alerts - Alerts page"""
        response = await client.get("/alerts")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_settings_page(self, client):
        """Test GET /settings - Settings page"""
        response = await client.get("/settings")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_reports_page(self, client):
        """Test GET /reports - Reports page"""
        response = await client.get("/reports")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        
    @pytest.mark.asyncio
    async def test_admin_page(self, client):
        """Test GET /admin - Admin page"""
        response = await client.get("/admin")
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
