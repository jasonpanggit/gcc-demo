"""
Base EOL Agent Tests

Tests for BaseEOLAgent base class functionality.
Created: 2026-02-27 (Phase 3, Week 1, Day 5)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from agents.base_eol_agent import BaseEOLAgent


# Concrete implementation for testing
class TestEOLAgent(BaseEOLAgent):
    """Test implementation of BaseEOLAgent."""

    async def get_eol_data(self, software_name: str, version=None, **kwargs):
        """Test implementation."""
        return self.create_success_response(
            software_name=software_name,
            version=version,
            eol_date="2025-12-31"
        )


@pytest.mark.unit
class TestBaseEOLAgent:
    """Tests for BaseEOLAgent base class."""

    def test_agent_initialization_with_name(self):
        """Test agent initialization with explicit name."""
        agent = TestEOLAgent(agent_name="test_agent")

        assert agent.agent_name == "test_agent"

    def test_agent_initialization_without_name(self):
        """Test agent initialization derives name from class."""
        agent = TestEOLAgent()

        # Should derive from class name (TestEOLAgent -> test)
        assert agent.agent_name == "test"

    def test_create_success_response_structure(self):
        """Test success response has correct structure."""
        agent = TestEOLAgent(agent_name="test")

        response = agent.create_success_response(
            software_name="Ubuntu",
            version="22.04",
            eol_date="2027-04-21",
            confidence=0.95
        )

        assert response["success"] is True
        assert response["source"] == "test"
        assert "timestamp" in response
        assert "data" in response
        assert response["data"]["software_name"] == "Ubuntu"
        assert response["data"]["version"] == "22.04"
        assert response["data"]["eol_date"] == "2027-04-21"
        assert response["data"]["confidence"] == 0.95

    def test_create_success_response_with_additional_data(self):
        """Test success response includes additional data."""
        agent = TestEOLAgent(agent_name="test")

        response = agent.create_success_response(
            software_name="RHEL",
            version="8",
            eol_date="2029-05-31",
            additional_data={"cycle": "8", "lts": True}
        )

        assert response["data"]["cycle"] == "8"
        assert response["data"]["lts"] is True

    def test_create_failure_response_structure(self):
        """Test failure response has correct structure."""
        agent = TestEOLAgent(agent_name="test")

        response = agent.create_failure_response(
            software_name="Unknown",
            version="1.0",
            error_message="Not found",
            error_code="NOT_FOUND"
        )

        assert response["success"] is False
        assert response["source"] == "test"
        assert "timestamp" in response
        assert "error" in response
        assert response["error"]["message"] == "Not found"
        assert response["error"]["code"] == "NOT_FOUND"
        assert response["data"] is None

    def test_determine_status_active(self):
        """Test status determination for active software."""
        agent = TestEOLAgent()

        # Date 5 years in future
        future_date = (datetime.utcnow() + timedelta(days=1825)).date().isoformat()
        status = agent._determine_status(future_date)

        assert status == "Active Support"

    def test_determine_status_critical(self):
        """Test status determination for critical EOL."""
        agent = TestEOLAgent()

        # Date 30 days in future
        near_date = (datetime.utcnow() + timedelta(days=30)).date().isoformat()
        status = agent._determine_status(near_date)

        assert status == "Critical - EOL Soon"

    def test_determine_status_past_eol(self):
        """Test status determination for past EOL."""
        agent = TestEOLAgent()

        # Date in past
        past_date = (datetime.utcnow() - timedelta(days=365)).date().isoformat()
        status = agent._determine_status(past_date)

        assert status == "End of Life"

    def test_determine_risk_level_low(self):
        """Test risk level determination for low risk."""
        agent = TestEOLAgent()

        # Date 3 years in future
        future_date = (datetime.utcnow() + timedelta(days=1095)).date().isoformat()
        risk = agent._determine_risk_level(future_date)

        assert risk == "low"

    def test_determine_risk_level_critical(self):
        """Test risk level determination for critical risk."""
        agent = TestEOLAgent()

        # Date 30 days in future
        near_date = (datetime.utcnow() + timedelta(days=30)).date().isoformat()
        risk = agent._determine_risk_level(near_date)

        assert risk == "critical"

    def test_calculate_days_until_eol(self):
        """Test days until EOL calculation."""
        agent = TestEOLAgent()

        # Date 100 days in future
        future_date = (datetime.utcnow() + timedelta(days=100)).date().isoformat()
        days = agent._calculate_days_until_eol(future_date)

        assert days is not None
        assert 95 <= days <= 105  # Allow some variance for test execution time

    def test_calculate_days_until_eol_none(self):
        """Test days until EOL with no date."""
        agent = TestEOLAgent()

        days = agent._calculate_days_until_eol(None)

        assert days is None

    @pytest.mark.asyncio
    async def test_get_eol_data_abstract_method(self):
        """Test get_eol_data is abstract and must be implemented."""
        # Cannot instantiate ABC without implementing abstract methods
        # Our TestEOLAgent implements it, so we test that it works
        agent = TestEOLAgent()

        result = await agent.get_eol_data("Ubuntu", "22.04")

        assert result["success"] is True
        assert result["data"]["software_name"] == "Ubuntu"

    def test_agent_name_field_exists(self):
        """Test agent_name attribute exists."""
        agent = TestEOLAgent(agent_name="custom")

        assert hasattr(agent, 'agent_name')
        assert agent.agent_name == "custom"

    def test_response_includes_agent_used(self):
        """Test response includes agent_used field for frontend."""
        agent = TestEOLAgent(agent_name="test")

        response = agent.create_success_response(
            software_name="Test",
            version="1.0",
            eol_date="2025-12-31"
        )

        assert response["data"]["agent_used"] == "test"

    def test_failure_response_includes_agent_used(self):
        """Test failure response includes agent_used field."""
        agent = TestEOLAgent(agent_name="test")

        response = agent.create_failure_response(
            software_name="Test",
            error_message="Not found"
        )

        assert response["error"]["agent_used"] == "test"
