"""Async transport tests for EOLStatusAgent."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.eolstatus_agent import EOLStatusAgent


def _product_html(**overrides) -> str:
    payload = {
        "@type": "Product",
        "name": "Python 3.11",
        "category": "Runtime",
        "brand": {"name": "Python Software Foundation"},
        "additionalProperty": [
            {"name": "version", "value": "3.11"},
            {"name": "end of life date", "value": "2027-10-31"},
            {"name": "end of support life date", "value": "2025-10-31"},
            {"name": "release date", "value": "2022-10-24"},
            {"name": "status", "value": "Supported"},
        ],
    }
    payload.update(overrides)
    return f'<html><script type="application/ld+json">{json.dumps(payload)}</script></html>'


@pytest.mark.unit
@pytest.mark.asyncio
class TestEOLStatusAgent:
    async def test_get_eol_data_uses_async_html_fetch(self):
        agent = EOLStatusAgent()

        with patch.object(agent, "_find_best_slug", new=AsyncMock(return_value=("python-3-11", "name_version"))), \
             patch.object(agent, "_fetch_html", new=AsyncMock(return_value=_product_html())) as mock_fetch, \
             patch.object(agent, "_collect_minor_versions", new=AsyncMock(return_value=[])):
            result = await agent.get_eol_data("python", "3.11")

        mock_fetch.assert_awaited_once_with("https://eolstatus.com/product/python-3-11")
        assert result["success"] is True
        assert result["data"]["eol_date"] == "2027-10-31"
        assert result["data"]["support_end_date"] == "2025-10-31"
        assert result["data"]["source_url"] == "https://eolstatus.com/product/python-3-11"

    async def test_get_product_slugs_uses_async_fetch_and_caches(self):
        agent = EOLStatusAgent()
        agent._products_cache = []
        agent._products_cache_ts = None
        html = '<a href="/product/python"></a><a href="/product/nodejs"></a>'

        with patch.object(agent, "_fetch_html", new=AsyncMock(return_value=html)) as mock_fetch:
            first = await agent._get_product_slugs()
            second = await agent._get_product_slugs()

        mock_fetch.assert_awaited_once_with(agent.products_url)
        assert first == ["nodejs", "python"]
        assert second == first
