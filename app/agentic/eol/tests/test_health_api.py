"""
Health API Router Tests

Tests for health check and status endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.mark.api
class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check_returns_ok(self, client):
        """Test basic health check returns OK."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "version" in data

    def test_health_check_has_inventory_asst_status(self, client):
        """Test health check includes inventory assistant status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "inventory_asst_available" in data
        assert isinstance(data["inventory_asst_available"], bool)

    def test_health_check_response_format(self, client):
        """Test health check response has correct format."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Should have required fields
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data

        # Timestamp should be valid ISO format
        timestamp = data["timestamp"]
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

    def test_health_check_fast_response(self, client):
        """Test health check responds quickly."""
        import time

        start = time.time()
        response = client.get("/health")
        duration = time.time() - start

        assert response.status_code == 200
        # Should respond in under 1 second
        assert duration < 1.0

    def test_detailed_health_endpoint_exists(self, client):
        """Test detailed health endpoint exists."""
        response = client.get("/api/health/detailed")

        # Should not return 404
        assert response.status_code != 404

    def test_status_endpoint_exists(self, client):
        """Test status endpoint exists."""
        response = client.get("/api/status")

        # Should not return 404
        assert response.status_code != 404


@pytest.mark.api
class TestHealthEndpointIntegration:
    """Integration tests for health endpoints."""

    def test_health_check_available_without_auth(self, client):
        """Test health check works without authentication."""
        # Health checks should be publicly accessible
        response = client.get("/health")

        assert response.status_code == 200
        # Should not require auth (no 401/403)
        assert response.status_code not in [401, 403]

    def test_health_check_content_type(self, client):
        """Test health check returns JSON."""
        response = client.get("/health")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    @patch('api.health._get_inventory_asst_available')
    def test_health_check_with_inventory_unavailable(self, mock_get_asst, client):
        """Test health check when inventory assistant unavailable."""
        mock_get_asst.return_value = False

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        # App should still be healthy
        assert data["status"] == "ok"
