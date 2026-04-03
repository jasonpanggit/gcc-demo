"""Async transport tests for EndOfLifeAgent."""

import httpx
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agents.endoflife_agent import EndOfLifeAgent


def _json_response(payload, status_code: int = 200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@pytest.mark.unit
@pytest.mark.asyncio
class TestEndOfLifeAgentAsync:
    async def test_try_direct_api_call_uses_async_http_get(self):
        agent = EndOfLifeAgent()
        response = _json_response(
            [
                {
                    "cycle": "3.11",
                    "eol": "2027-10-31",
                    "support": "2025-10-31",
                    "releaseDate": "2022-10-24",
                    "latest": "3.11.9",
                    "lts": False,
                }
            ]
        )

        with patch.object(agent, "_http_get", new=AsyncMock(return_value=response)) as mock_get:
            result = await agent._try_direct_api_call("python", "3.11")

        mock_get.assert_awaited_once_with("https://endoflife.date/api/python.json", timeout=agent.timeout)
        assert result is not None
        assert result["success"] is True
        assert result["data"]["eol_date"] == "2027-10-31"
        assert result["data"]["source_url"] == "https://endoflife.date/api/python.json"

    async def test_get_all_products_uses_async_http_get(self):
        agent = EndOfLifeAgent()
        response = _json_response(["python", "nodejs", "postgresql"])

        with patch.object(agent, "_http_get", new=AsyncMock(return_value=response)) as mock_get:
            products = await agent._get_all_products()

        mock_get.assert_awaited_once_with("https://endoflife.date/api/all.json", timeout=agent.timeout)
        assert products == ["python", "nodejs", "postgresql"]

    async def test_get_supported_products_uses_async_http_get(self):
        agent = EndOfLifeAgent()
        response = _json_response(["python", "nodejs"])

        with patch.object(agent, "_http_get", new=AsyncMock(return_value=response)) as mock_get:
            products = await agent.get_supported_products()

        mock_get.assert_awaited_once_with("https://endoflife.date/api/all.json", timeout=agent.timeout)
        assert products == {"source": "endoflife.date", "products": ["python", "nodejs"]}

    async def test_agent_context_manager_closes_http_client(self):
        async with EndOfLifeAgent() as agent:
            client = await agent._get_http_client()
            assert client.is_closed is False

        assert client.is_closed is True
        assert agent._http_client is None

    async def test_agent_recreates_http_client_after_close(self):
        agent = EndOfLifeAgent()

        first_client = await agent._get_http_client()
        await agent.aclose()
        second_client = await agent._get_http_client()

        assert first_client.is_closed is True
        assert second_client is not first_client
        assert isinstance(second_client, httpx.AsyncClient)

        await agent.aclose()
