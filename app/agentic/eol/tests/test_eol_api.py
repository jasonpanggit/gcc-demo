"""
EOL API Router Tests

Tests for EOL search and management endpoints.
Created: 2026-02-27 (Phase 3, Week 2, Day 1)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestEOLRouterUnit:
    """Unit tests for EOL router without full app."""

    def test_eol_router_imports(self):
        """Test EOL router can be imported."""
        from api.eol import router

        assert router is not None
        assert hasattr(router, 'routes')

    def test_eol_router_has_endpoints(self):
        """Test EOL router has expected endpoints."""
        from api.eol import router

        # Get all route paths
        paths = [route.path for route in router.routes]

        # Should have EOL endpoints
        assert any('eol' in path.lower() for path in paths)

    def test_eol_router_tags(self):
        """Test EOL router has correct tags."""
        from api.eol import router

        assert hasattr(router, 'tags')
        # Should have EOL-related tag
        tags_str = str(router.tags)
        assert "eol" in tags_str.lower() or "search" in tags_str.lower()

    def test_software_search_request_model(self):
        """Test SoftwareSearchRequest model exists and validates."""
        from api.eol import SoftwareSearchRequest

        # Should create with required field
        request = SoftwareSearchRequest(software_name="Ubuntu")
        assert request.software_name == "Ubuntu"
        assert request.software_version is None

        # Should accept optional fields
        request = SoftwareSearchRequest(
            software_name="Ubuntu",
            software_version="22.04",
            search_hints="LTS",
            search_internet_only=True
        )
        assert request.software_version == "22.04"
        assert request.search_hints == "LTS"
        assert request.search_internet_only is True

    def test_software_search_request_requires_name(self):
        """Test SoftwareSearchRequest requires software_name."""
        from api.eol import SoftwareSearchRequest
        from pydantic import ValidationError

        # Should raise validation error without software_name
        with pytest.raises(ValidationError):
            SoftwareSearchRequest()

    def test_verify_eol_request_model(self):
        """Test VerifyEOLRequest model exists."""
        from api.eol import VerifyEOLRequest

        request = VerifyEOLRequest(
            software_name="Test",
            software_version="1.0",
            verification_status="verified"
        )
        assert request.software_name == "Test"
        assert request.verification_status == "verified"

    def test_cache_eol_request_model(self):
        """Test CacheEOLRequest model exists."""
        from api.eol import CacheEOLRequest

        request = CacheEOLRequest(software_name="Ubuntu")
        assert request.software_name == "Ubuntu"


class TestEOLEndpointFunctions:
    """Tests for EOL endpoint function logic."""

    def test_get_eol_orchestrator_function(self):
        """Test _get_eol_orchestrator helper exists."""
        from api import eol

        assert hasattr(eol, '_get_eol_orchestrator')
        assert callable(eol._get_eol_orchestrator)

    def test_get_inventory_asst_orchestrator_function(self):
        """Test _get_inventory_asst_orchestrator helper exists."""
        from api import eol

        assert hasattr(eol, '_get_inventory_asst_orchestrator')
        assert callable(eol._get_inventory_asst_orchestrator)

    def test_eol_module_has_standard_response(self):
        """Test EOL module imports StandardResponse."""
        from api import eol

        # Should have StandardResponse imported
        assert hasattr(eol, 'StandardResponse')

    def test_eol_module_has_decorators(self):
        """Test EOL module imports endpoint decorators."""
        from api import eol

        # Should have endpoint decorators
        assert hasattr(eol, 'standard_endpoint') or hasattr(eol, 'readonly_endpoint')


class TestEOLRequestValidation:
    """Tests for EOL request model validation."""

    def test_software_search_default_values(self):
        """Test SoftwareSearchRequest default values."""
        from api.eol import SoftwareSearchRequest

        request = SoftwareSearchRequest(software_name="Test")

        # Check default values
        assert request.search_internet_only is False
        assert request.search_include_internet is False
        assert request.search_ignore_cache is False
        assert request.search_agent_only is False

    def test_verify_eol_default_status(self):
        """Test VerifyEOLRequest default verification status."""
        from api.eol import VerifyEOLRequest

        request = VerifyEOLRequest(software_name="Test")

        # Should have default verification status
        assert request.verification_status == "verified"

    def test_vendor_parsing_request_model(self):
        """Test VendorParsingRequest model exists."""
        from api.eol import VendorParsingRequest

        request = VendorParsingRequest(vendor="microsoft")
        assert request.vendor == "microsoft"
        assert request.mode == "agents_plus_internet"  # default
        assert request.ignore_cache is False


class TestEOLRouterConfiguration:
    """Tests for EOL router configuration."""

    def test_router_is_fastapi_router(self):
        """Test router is a FastAPI APIRouter."""
        from api.eol import router
        from fastapi import APIRouter

        assert isinstance(router, APIRouter)

    def test_eol_inventory_imported(self):
        """Test eol_inventory is imported."""
        from api import eol

        assert hasattr(eol, 'eol_inventory')

    def test_vendor_url_inventory_imported(self):
        """Test vendor_url_inventory is imported."""
        from api import eol

        assert hasattr(eol, 'vendor_url_inventory')

    def test_default_vendor_routing_imported(self):
        """Test DEFAULT_VENDOR_ROUTING is imported."""
        from api import eol

        assert hasattr(eol, 'DEFAULT_VENDOR_ROUTING')

    def test_logger_initialized(self):
        """Test logger is initialized."""
        from api import eol

        assert hasattr(eol, 'logger')

