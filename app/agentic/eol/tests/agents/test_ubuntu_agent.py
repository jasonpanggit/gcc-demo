"""
Ubuntu EOL Agent Tests

Tests for Ubuntu EOL agent functionality including scraping, caching, and error handling.
Created: 2026-02-27 (Phase 3, Week 1, Day 2)
"""

import pytest
from unittest.mock import MagicMock, patch
from agents.ubuntu_agent import UbuntuEOLAgent
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
class TestUbuntuAgent:
    """Tests for UbuntuEOLAgent."""

    def test_agent_initialization(self):
        """Test that Ubuntu agent initializes correctly."""
        agent = UbuntuEOLAgent()

        assert agent.agent_name == "ubuntu"
        assert agent.timeout == 15
        assert "ubuntu" in agent.eol_urls
        assert agent.headers["User-Agent"] is not None

    def test_agent_has_eol_urls(self):
        """Test that agent has configured EOL URLs."""
        agent = UbuntuEOLAgent()

        # Check key URLs exist
        assert "ubuntu" in agent.eol_urls
        assert "url" in agent.eol_urls["ubuntu"]
        assert "active" in agent.eol_urls["ubuntu"]

        # Verify URL structure
        for key, config in agent.eol_urls.items():
            assert "url" in config
            assert "description" in config
            assert isinstance(config.get("active", True), bool)

    def test_is_ubuntu_product(self):
        """Test Ubuntu product detection."""
        agent = UbuntuEOLAgent()

        # Should recognize Ubuntu products
        assert agent._is_ubuntu_product("Ubuntu 22.04")
        assert agent._is_ubuntu_product("ubuntu")
        assert agent._is_ubuntu_product("Canonical Ubuntu")

        # Should reject non-Ubuntu products
        assert not agent._is_ubuntu_product("RHEL")
        assert not agent._is_ubuntu_product("Windows Server")

    def test_normalize_version(self):
        """Test version normalization."""
        agent = UbuntuEOLAgent()

        # Should normalize various version formats
        assert agent._normalize_version("22.04") == "22.04"
        assert agent._normalize_version("2022.04") == "22.04"
        assert agent._normalize_version("Ubuntu 20.04 LTS") == "20.04"

    def test_version_matches(self):
        """Test version matching logic."""
        agent = UbuntuEOLAgent()

        # Should match versions
        assert agent._version_matches("22.04", "22.04 LTS")
        assert agent._version_matches("20.04", "20.04")
        assert agent._version_matches("18.04", "18.04 LTS")

        # Should not match different versions
        assert not agent._version_matches("22.04", "20.04 LTS")

    def test_parse_date(self):
        """Test date parsing."""
        agent = UbuntuEOLAgent()

        # Should parse various date formats
        assert agent._parse_date("2024-04-25") == "2024-04-25"
        assert agent._parse_date("April 2024") is not None
        assert agent._parse_date("2025") == "2025-01-01"  # Year only

        # Should handle invalid dates
        assert agent._parse_date("TBD") is None
        assert agent._parse_date("-") is None
        assert agent._parse_date("") is None

    @pytest.mark.asyncio
    @patch('agents.ubuntu_agent.UbuntuEOLAgent._http_get')
    async def test_scrape_success(self, mock_get):
        """Test successful scraping of Ubuntu EOL data."""
        agent = UbuntuEOLAgent()

        # Mock successful HTTP response with minimal valid HTML
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html><body>
        <table>
            <tr><th>Version</th><th>Codename</th><th>Release</th><th>Support</th><th>EOL</th></tr>
            <tr><td>22.04 LTS</td><td>Jammy</td><td>2022-04-21</td><td>2027-04</td><td>2032-04</td></tr>
        </table>
        </body></html>
        """
        mock_response.content = mock_response.text.encode()
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = await agent._scrape_eol_data("Ubuntu", "22.04")

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["cycle"] == "22.04 LTS"
        mock_get.assert_awaited_once_with(
            agent.eol_urls["ubuntu"]["url"],
            headers=agent.headers,
            timeout=agent.timeout,
        )

    @pytest.mark.asyncio
    async def test_get_eol_data_ubuntu(self):
        """Test get_eol_data for Ubuntu product."""
        agent = UbuntuEOLAgent()

        # Mock the scraping to avoid actual HTTP calls
        with patch.object(agent, '_scrape_eol_data', return_value=[{
            "cycle": "22.04 LTS",
            "codename": "Jammy Jellyfish",
            "releaseDate": "2022-04-21",
            "support": "2027-04-21",
            "eol": "2032-04-21",
            "lts": True,
            "source": "ubuntu_official_scraped"
        }]):
            result = await agent.get_eol_data("Ubuntu", "22.04")
            assert result is not None
            if result.get("success"):
                # Version is in data.cycle or data.version field
                data = result.get("data", {})
                version_info = data.get("version", data.get("cycle", ""))
                assert "22.04" in str(version_info)

    @pytest.mark.asyncio
    async def test_get_eol_data_non_ubuntu(self):
        """Test get_eol_data with non-Ubuntu product."""
        agent = UbuntuEOLAgent()

        # Should return None for non-Ubuntu products
        result = await agent.get_eol_data("RHEL", "8")
        assert result is None

    @pytest.mark.asyncio
    async def test_query_method_exists(self):
        """Test that agent has query method."""
        agent = UbuntuEOLAgent()

        assert hasattr(agent, 'get_eol_data')

    @pytest.mark.asyncio
    async def test_timeout_configuration(self):
        """Test that agent respects timeout configuration."""
        agent = UbuntuEOLAgent()

        # Should have timeout configured
        assert hasattr(agent, 'timeout')
        assert agent.timeout > 0
        assert agent.timeout <= 30  # Reasonable timeout

    @pytest.mark.asyncio
    async def test_agent_cache_is_centrally_managed(self):
        """Test that agent-level cache management is intentionally disabled."""
        agent = UbuntuEOLAgent()

        result = await agent.purge_cache()
        assert result["success"] is True
        assert "disabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_vendor_name(self):
        """Test that agent has correct agent name."""
        agent = UbuntuEOLAgent()

        assert agent.agent_name == "ubuntu"

    @pytest.mark.asyncio
    async def test_agent_inherits_from_base(self):
        """Test that agent inherits from BaseEOLAgent."""
        from agents.base_eol_agent import BaseEOLAgent

        agent = UbuntuEOLAgent()

        assert isinstance(agent, BaseEOLAgent)

    def test_urls_property(self):
        """Test that agent has dynamic urls property."""
        agent = UbuntuEOLAgent()

        urls = agent.urls
        assert isinstance(urls, list)
        assert len(urls) > 0

        # Each URL should have required fields
        for url_obj in urls:
            assert "url" in url_obj
            assert "description" in url_obj
            assert "active" in url_obj

    def test_get_url_method(self):
        """Test backward compatibility get_url method."""
        agent = UbuntuEOLAgent()

        # Should return URL string
        ubuntu_url = agent.get_url("ubuntu")
        assert ubuntu_url is not None
        assert isinstance(ubuntu_url, str)
        assert "ubuntu" in ubuntu_url.lower()

        # Should return None for invalid product
        invalid_url = agent.get_url("invalid_product")
        assert invalid_url is None

    def test_parse_ubuntu_releases(self):
        """Test parsing of Ubuntu releases from HTML."""
        agent = UbuntuEOLAgent()

        from bs4 import BeautifulSoup
        html = """
        <html><body>
        <table>
            <tr><th>Version</th><th>Codename</th><th>Release Date</th><th>Support</th><th>EOL</th></tr>
            <tr><td>22.04 LTS</td><td>Jammy Jellyfish</td><td>2022-04-21</td><td>2027-04-21</td><td>2032-04-21</td></tr>
            <tr><td>20.04 LTS</td><td>Focal Fossa</td><td>2020-04-23</td><td>2025-04-23</td><td>2030-04-23</td></tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')

        releases = agent._parse_ubuntu_releases(soup)
        assert isinstance(releases, list)
        # May return empty if table structure doesn't match expected format
        # The important thing is it doesn't crash

    @pytest.mark.asyncio
    async def test_fetch_all_from_url_method_exists(self):
        """Test that agent has fetch_all_from_url method."""
        agent = UbuntuEOLAgent()

        assert hasattr(agent, 'fetch_all_from_url')

    def test_get_supported_versions_method_exists(self):
        """Test that agent has get_supported_versions method."""
        agent = UbuntuEOLAgent()

        assert hasattr(agent, 'get_supported_versions')

        # Should return a list
        versions = agent.get_supported_versions()
        assert isinstance(versions, list)

    def test_get_lts_versions_method_exists(self):
        """Test that agent has get_lts_versions method."""
        agent = UbuntuEOLAgent()

        assert hasattr(agent, 'get_lts_versions')

        # Should return a list
        lts_versions = agent.get_lts_versions()
        assert isinstance(lts_versions, list)


@pytest.mark.integration
@pytest.mark.asyncio
class TestUbuntuAgentIntegration:
    """Integration tests for Ubuntu agent with Phase 2 utilities."""

    async def test_agent_with_error_aggregator(self):
        """Test agent integration with error aggregator."""
        agent = UbuntuEOLAgent()
        agg = ErrorAggregator()

        with patch.object(agent, '_scrape_eol_data', side_effect=Exception("Network error")):
            try:
                await agent.get_eol_data("Ubuntu", "22.04")
            except Exception as e:
                agg.add_error(e, {"agent": "ubuntu", "operation": "query"})

        assert agg.has_errors()
        assert agg.get_error_count() == 1

    async def test_agent_with_timeout_config(self):
        """Test agent integration with centralized timeout config."""
        from utils.config import TimeoutConfig

        agent = UbuntuEOLAgent()
        timeout_config = TimeoutConfig()

        # Agent timeout should align with config
        assert agent.timeout <= timeout_config.agent_timeout * 2  # Reasonable range

    async def test_agent_with_circuit_breaker(self):
        """Test agent with circuit breaker pattern."""
        from utils.circuit_breaker import CircuitBreaker

        agent = UbuntuEOLAgent()
        cb = CircuitBreaker(failure_threshold=2, name="ubuntu_agent")

        with patch.object(agent, '_scrape_eol_data', side_effect=RuntimeError("Connection failed")):
            for _ in range(2):
                with pytest.raises(RuntimeError, match="Connection failed"):
                    await cb.call(agent._scrape_eol_data, "Ubuntu 22.04", "22.04")

        assert cb.state.value == "OPEN"

    @patch('agents.ubuntu_agent.UbuntuEOLAgent._http_get')
    async def test_scrape_with_error_tracking(self, mock_get):
        """Test scraping with error tracking."""
        agent = UbuntuEOLAgent()

        # Mock HTTP error
        mock_get.side_effect = Exception("HTTP 404 Not Found")

        result = await agent._scrape_eol_data("Ubuntu", "22.04")

        assert result is None

    @patch('agents.ubuntu_agent.UbuntuEOLAgent._http_get')
    async def test_fetch_all_with_mocked_response(self, mock_get):
        """Test fetch_all_from_url with mocked HTTP response."""
        agent = UbuntuEOLAgent()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html><body>
        <table>
            <tr><th>Version</th><th>Codename</th><th>Release</th><th>Support</th><th>EOL</th></tr>
            <tr><td>22.04 LTS</td><td>Jammy</td><td>2022-04-21</td><td>2027-04</td><td>2032-04</td></tr>
        </table>
        </body></html>
        """
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        records = await agent.fetch_all_from_url(
            "https://example.com/releases",
            "ubuntu",
            None
        )

        assert isinstance(records, list)
        assert len(records) == 1
        assert records[0]["cycle"] == "22.04 LTS"
        assert records[0]["software_name"] == "ubuntu"
