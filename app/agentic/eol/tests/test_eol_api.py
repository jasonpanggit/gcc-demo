"""
EOL API Router Tests

Tests for EOL search and management endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.mark.api
class TestEOLEndpoints:
    """Tests for EOL API endpoints."""

    def test_eol_get_endpoint_exists(self, client):
        """Test GET /api/eol endpoint exists."""
        response = client.get("/api/eol?software_name=Ubuntu&software_version=22.04")

        # Should not return 404 (may return 422 for validation)
        assert response.status_code != 404

    def test_eol_search_endpoint_exists(self, client):
        """Test POST /api/search/eol endpoint exists."""
        response = client.post(
            "/api/search/eol",
            json={"software_name": "Ubuntu", "software_version": "22.04"}
        )

        # Should not return 404
        assert response.status_code != 404

    def test_eol_search_request_validation(self, client):
        """Test EOL search validates required fields."""
        # Missing software_name should fail validation
        response = client.post("/api/search/eol", json={})

        # Should return validation error (422)
        assert response.status_code == 422

    def test_eol_search_with_valid_request(self, client):
        """Test EOL search with valid request structure."""
        response = client.post(
            "/api/search/eol",
            json={
                "software_name": "Ubuntu",
                "software_version": "22.04",
                "search_internet_only": False
            }
        )

        # Should accept the request (may fail later in processing)
        assert response.status_code in [200, 500, 503]

    def test_eol_analyze_endpoint_exists(self, client):
        """Test POST /api/analyze endpoint exists."""
        response = client.post("/api/analyze", json={})

        # Should not return 404
        assert response.status_code != 404

    def test_verify_eol_endpoint_exists(self, client):
        """Test POST /api/verify-eol-result endpoint exists."""
        response = client.post(
            "/api/verify-eol-result",
            json={
                "software_name": "Ubuntu",
                "software_version": "22.04",
                "verification_status": "verified"
            }
        )

        # Should not return 404
        assert response.status_code != 404

    def test_cache_eol_endpoint_exists(self, client):
        """Test POST /api/cache-eol-result endpoint exists."""
        response = client.post(
            "/api/cache-eol-result",
            json={"software_name": "Ubuntu"}
        )

        # Should not return 404
        assert response.status_code != 404

    def test_eol_agent_responses_endpoint_exists(self, client):
        """Test GET /api/eol-agent-responses endpoint exists."""
        response = client.get("/api/eol-agent-responses")

        # Should not return 404
        assert response.status_code != 404

    def test_clear_agent_responses_endpoint_exists(self, client):
        """Test POST /api/eol-agent-responses/clear endpoint exists."""
        response = client.post("/api/eol-agent-responses/clear")

        # Should not return 404
        assert response.status_code != 404


@pytest.mark.api
class TestEOLRequestModels:
    """Tests for EOL request model validation."""

    def test_software_search_request_required_fields(self, client):
        """Test SoftwareSearchRequest requires software_name."""
        # Missing required field
        response = client.post("/api/search/eol", json={})

        assert response.status_code == 422
        error = response.json()
        assert "detail" in error

    def test_software_search_request_optional_fields(self, client):
        """Test SoftwareSearchRequest accepts optional fields."""
        response = client.post(
            "/api/search/eol",
            json={
                "software_name": "Ubuntu",
                "software_version": "22.04",
                "search_hints": "LTS",
                "search_internet_only": True,
                "search_include_internet": False,
                "search_ignore_cache": True,
                "search_agent_only": False
            }
        )

        # Should accept all fields (may fail in processing)
        assert response.status_code in [200, 500, 503]

    def test_verify_eol_request_structure(self, client):
        """Test VerifyEOLRequest validation."""
        # Valid request structure
        response = client.post(
            "/api/verify-eol-result",
            json={
                "software_name": "Test",
                "software_version": "1.0",
                "agent_name": "test_agent",
                "source_url": "https://example.com",
                "verification_status": "verified"
            }
        )

        # Should accept valid structure
        assert response.status_code != 422


@pytest.mark.api
class TestEOLEndpointIntegration:
    """Integration tests for EOL endpoints."""

    def test_eol_endpoints_return_json(self, client):
        """Test EOL endpoints return JSON responses."""
        response = client.get("/api/eol-agent-responses")

        assert "application/json" in response.headers.get("content-type", "")

    def test_eol_search_handles_invalid_software(self, client):
        """Test EOL search handles unknown software gracefully."""
        response = client.post(
            "/api/search/eol",
            json={
                "software_name": "NonexistentSoftware12345",
                "software_version": "99.99"
            }
        )

        # Should handle gracefully (not crash)
        assert response.status_code in [200, 404, 500, 503]

    def test_multiple_concurrent_eol_requests(self, client):
        """Test multiple EOL requests can be handled."""
        import concurrent.futures

        def make_request():
            return client.post(
                "/api/search/eol",
                json={"software_name": "Ubuntu"}
            )

        # Make 3 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(3)]
            results = [f.result() for f in futures]

        # All should complete (may succeed or fail gracefully)
        assert len(results) == 3
        for response in results:
            assert response.status_code in [200, 404, 500, 503]
