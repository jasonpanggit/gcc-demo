"""Focused contract regressions for cache API normalization."""

import sys
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.cache import router as cache_router


class FakeEOLOrchestrator:
    def __init__(self) -> None:
        self.eol_cache = {"windows::2019": {"eol_date": "2029-01-09"}}
        self.agents = {
            "microsoft": SimpleNamespace(_cache={"a": 1, "b": 2}),
            "redhat": SimpleNamespace(_cache={}),
        }

    async def get_cache_status(self):
        return {
            "success": True,
            "data": {
                "eol_cache": {"total_items": 1, "cache_ttl_seconds": 3600},
                "agents": {"microsoft": {"status": "available", "type": "MicrosoftEOLAgent"}},
            },
        }


class FakeInventoryCache:
    def get_cache_stats(self):
        return {
            "total_memory_entries": 3,
            "cache_duration_hours": 4,
            "memory_cache_entries": {"software": 2, "os": 1},
            "supported_cache_types": ["software", "os"],
            "initialized": True,
        }

    async def clear_all_cache(self):
        return {"cleared_count": 3, "cache_types": ["software", "os"], "l2_cleared": True}


class FakeEOLCache:
    async def clear_cache(self, software_name=None, agent_name=None):
        return {"success": True, "deleted_count": 2, "software_name": software_name, "agent_name": agent_name}


class FakeEOLInventory:
    async def invalidate(self, software_name, version):
        return 1


@pytest_asyncio.fixture
async def cache_contract_client():
    app = FastAPI()
    app.include_router(cache_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_cache_status_returns_wrapped_object_payload(cache_contract_client, monkeypatch):
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(get_eol_orchestrator=lambda: FakeEOLOrchestrator()))
    monkeypatch.setitem(sys.modules, "utils.inventory_cache", SimpleNamespace(inventory_cache=FakeInventoryCache()))
    monkeypatch.setattr(
        "api.cache.cache_stats_manager.get_all_statistics",
        lambda: {"agent_stats": {"agents": {"microsoft": {"request_count": 4}}}, "performance_summary": {"overall_hit_rate": 75.0}},
    )

    response = await cache_contract_client.get("/api/cache/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["eol_cache"]["total_items"] == 1
    assert body["data"]["inventory_context_cache"]["items_count"] == 3
    assert body["data"]["enhanced_stats"]["performance_summary"]["overall_hit_rate"] == 75.0


@pytest.mark.asyncio
async def test_cache_purge_returns_wrapped_object_payload(cache_contract_client, monkeypatch):
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(get_eol_orchestrator=lambda: FakeEOLOrchestrator()))
    monkeypatch.setitem(sys.modules, "utils.eol_cache", SimpleNamespace(eol_cache=FakeEOLCache()))
    monkeypatch.setitem(sys.modules, "utils.eol_inventory", SimpleNamespace(eol_inventory=FakeEOLInventory()))

    response = await cache_contract_client.post("/api/cache/purge?agent_type=microsoft&software_name=Windows%20Server&version=2019")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["results"]["microsoft"]["deleted_count"] == 2
    assert body["data"]["deleted_count"] == 3
    assert body["data"]["memory_cleared"] == 1


@pytest.mark.asyncio
async def test_webscraping_cache_details_returns_wrapped_object_payload(cache_contract_client, monkeypatch):
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(get_eol_orchestrator=lambda: FakeEOLOrchestrator()))

    response = await cache_contract_client.get("/api/cache/webscraping/details")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["summary"]["total_agents"] >= 1
    assert body["data"]["cache_details"][0]["agent"] == "microsoft"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_key"),
    [
        ("/api/cache/stats/enhanced", "performance_summary"),
        ("/api/cache/stats/agents", "summary"),
        ("/api/cache/stats/performance", "overall_hit_rate"),
        ("/api/cache/stats/reset", "message"),
    ],
)
async def test_cache_stats_endpoints_return_wrapped_object_payload(
    cache_contract_client,
    monkeypatch,
    path,
    expected_key,
):
    monkeypatch.setattr(
        "api.cache.cache_stats_manager.get_all_statistics",
        lambda: {"performance_summary": {"overall_hit_rate": 88.5}, "agent_stats": {"agents": {}}, "inventory_stats": {}},
    )
    monkeypatch.setattr(
        "api.cache.cache_stats_manager.get_agent_statistics",
        lambda: {"agents": {"microsoft": {"request_count": 4}}, "summary": {"total_agents": 1}},
    )
    monkeypatch.setattr(
        "api.cache.cache_stats_manager.get_performance_summary",
        lambda: {"overall_hit_rate": 88.5, "avg_response_time_ms": 42.0},
    )
    monkeypatch.setattr("api.cache.cache_stats_manager.reset_all_stats", lambda: None)

    response = await cache_contract_client.post(path) if path.endswith("reset") else await cache_contract_client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert expected_key in body["data"]