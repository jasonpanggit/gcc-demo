"""
Microsoft EOL Agent Tests

Tests for Microsoft EOL agent functionality including scraping, caching, and error handling.
Created: 2026-02-27 (Phase 3, Week 1, Day 1)
"""

import pytest
from unittest.mock import MagicMock, patch
from agents.microsoft_agent import MicrosoftEOLAgent
from utils.error_aggregator import ErrorAggregator


@pytest.mark.unit
class TestMicrosoftAgent:
    """Tests for MicrosoftEOLAgent."""

    def test_agent_initialization(self):
        """Test that Microsoft agent initializes correctly."""
        agent = MicrosoftEOLAgent()

        assert agent.agent_name == "microsoft"
        assert agent.timeout == 15
        assert "windows-server" in agent.eol_urls
        assert "windows-10" in agent.eol_urls
        assert agent.headers["User-Agent"] is not None

    def test_agent_has_eol_urls(self):
        """Test that agent has configured EOL URLs."""
        agent = MicrosoftEOLAgent()

        # Check key URLs exist
        assert "windows-server" in agent.eol_urls
        assert "url" in agent.eol_urls["windows-server"]
        assert "active" in agent.eol_urls["windows-server"]

        # Verify URL structure
        for key, config in agent.eol_urls.items():
            assert "url" in config
            assert "description" in config
            assert isinstance(config.get("active", True), bool)

    @pytest.mark.asyncio
    @patch('agents.microsoft_agent.MicrosoftEOLAgent._http_get')
    async def test_scrape_success(self, mock_get):
        """Test fetch_from_url returns a standardized success response."""
        agent = MicrosoftEOLAgent()

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Windows Server 2019 EOL: 2029-01-09</body></html>"
        mock_response.content = mock_response.text.encode()
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.object(agent, '_scrape_eol_data', return_value={
            "version": "2019",
            "cycle": "2019",
            "eol": "2029-01-09",
            "support": "2024-01-09",
            "release": "2018-11-13",
            "confidence": 0.8,
            "source": "microsoft_scrape",
        }) as mock_scrape:
            result = await agent.fetch_from_url(
                "https://example.com/windows-server",
                "Windows Server",
                "2019",
            )

        assert result["success"] is True
        assert result["data"]["software_name"] == "Windows Server"
        assert result["data"]["version"] == "2019"
        assert result["data"]["eol_date"] == "2029-01-09"
        mock_get.assert_awaited_once_with(
            "https://example.com/windows-server",
            headers=agent.headers,
            timeout=agent.timeout,
        )
        mock_scrape.assert_awaited_once_with("Windows Server", "2019")

    @pytest.mark.asyncio
    @patch('agents.microsoft_agent.MicrosoftEOLAgent._http_get')
    async def test_scrape_http_error(self, mock_get):
        """Test fetch_from_url returns a standardized failure response."""
        agent = MicrosoftEOLAgent()

        # Mock HTTP error
        mock_get.side_effect = Exception("HTTP 404 Not Found")

        result = await agent.fetch_from_url(
            "https://example.com/windows-server",
            "Windows Server",
            "2019",
        )

        assert result["success"] is False
        assert result["error"]["software_name"] == "Windows Server"
        assert "Failed to parse" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_query_method_exists(self):
        """Test that agent has query method."""
        agent = MicrosoftEOLAgent()

        assert hasattr(agent, 'query') or hasattr(agent, 'get_eol_data')

    @pytest.mark.asyncio
    async def test_timeout_configuration(self):
        """Test that agent respects timeout configuration."""
        agent = MicrosoftEOLAgent()

        # Should have timeout configured
        assert hasattr(agent, 'timeout')
        assert agent.timeout > 0
        assert agent.timeout <= 30  # Reasonable timeout

    @pytest.mark.asyncio
    @patch('agents.microsoft_agent.MicrosoftEOLAgent._http_get')
    async def test_user_agent_header(self, mock_get):
        """Test that agent sends proper User-Agent header."""
        agent = MicrosoftEOLAgent()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html></html>"
        mock_response.content = mock_response.text.encode()
        mock_get.return_value = mock_response

        with patch.object(agent, '_scrape_eol_data', return_value={
            "version": "2019",
            "eol": "2029-01-09",
        }):
            await agent.fetch_from_url("https://example.com", "Windows Server", "2019")

        call_kwargs = mock_get.call_args[1]
        assert 'User-Agent' in call_kwargs['headers']

    @pytest.mark.asyncio
    async def test_agent_cache_is_centrally_managed(self):
        """Test that agent-level cache management is intentionally disabled."""
        agent = MicrosoftEOLAgent()

        result = await agent.purge_cache()
        assert result["success"] is True
        assert "disabled" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_vendor_name(self):
        """Test that agent has correct agent name."""
        agent = MicrosoftEOLAgent()

        assert agent.agent_name == "microsoft"

    @pytest.mark.asyncio
    async def test_agent_inherits_from_base(self):
        """Test that agent inherits from BaseEOLAgent."""
        from agents.base_eol_agent import BaseEOLAgent

        agent = MicrosoftEOLAgent()

        assert isinstance(agent, BaseEOLAgent)


@pytest.mark.integration
@pytest.mark.asyncio
class TestMicrosoftAgentIntegration:
    """Integration tests for Microsoft agent with Phase 2 utilities."""

    async def test_agent_with_error_aggregator(self):
        """Test agent integration with error aggregator."""
        agent = MicrosoftEOLAgent()
        agg = ErrorAggregator()

        with patch.object(agent, '_scrape_eol_data', side_effect=RuntimeError("scrape failed")):
            try:
                await agent.get_eol_data("Windows Server 2019")
            except RuntimeError as e:
                agg.add_error(e, {"agent": "microsoft", "operation": "query"})

        assert agg.has_errors()
        assert agg.get_error_count() == 1

    async def test_agent_with_timeout_config(self):
        """Test agent integration with centralized timeout config."""
        from utils.config import TimeoutConfig

        agent = MicrosoftEOLAgent()
        timeout_config = TimeoutConfig()

        # Agent timeout should align with config
        # (Agent might use its own timeout or config timeout)
        assert agent.timeout <= timeout_config.agent_timeout * 2  # Reasonable range

    async def test_agent_with_circuit_breaker(self):
        """Test agent with circuit breaker pattern."""
        from utils.circuit_breaker import CircuitBreaker

        agent = MicrosoftEOLAgent()
        cb = CircuitBreaker(failure_threshold=2, name="microsoft_agent")

        with patch.object(agent, 'fetch_from_url', side_effect=RuntimeError("Connection failed")):
            for _ in range(2):
                with pytest.raises(RuntimeError, match="Connection failed"):
                    await cb.call(agent.fetch_from_url, "https://example.com", "Windows Server", "2019")

        assert cb.state.value == "OPEN"
