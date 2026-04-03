"""Focused contract regressions for inventory API response normalization."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.inventory import router as inventory_router


class FakeInventorySummaryAgent:
    async def get_inventory_summary(self):
        return {
            "total_software": 2,
            "total_os": 1,
            "last_update": "2026-03-27T00:00:00",
        }


class FakeSoftwareInventoryAgent:
    async def clear_cache(self):
        return {"success": True}

    async def get_software_inventory(self, **_: object):
        return {
            "success": True,
            "data": [
                {
                    "computer": "srv-01",
                    "name": "SQL Server",
                    "version": "2019",
                }
            ],
            "count": 1,
            "query_params": {"days": 30, "limit": 1000},
            "cached_at": "2026-03-27T00:00:00",
            "from_cache": True,
            "source": "inventory_cache",
        }


class FakeOSInventoryAgent:
    async def clear_cache(self):
        return {"success": True}

    async def get_os_inventory(self, **_: object):
        return {
            "success": True,
            "data": [
                {
                    "computer_name": "srv-01",
                    "os_name": "Windows Server",
                    "os_version": "2019",
                }
            ],
            "count": 1,
            "query_params": {"days": 30, "limit": 2000},
            "cached_at": "2026-03-27T00:00:00",
            "from_cache": False,
            "source": "law",
        }


class FakeInventoryOrchestrator:
    def __init__(self) -> None:
        self.agents = {
            "inventory": FakeInventorySummaryAgent(),
            "software_inventory": FakeSoftwareInventoryAgent(),
            "os_inventory": FakeOSInventoryAgent(),
        }

    async def reload_inventory_from_law(self, **_: object):
        return {
            "success": True,
            "total_items": 42,
            "processing_time_seconds": 1.5,
        }

    async def get_software_inventory(self, **_: object):
        return {
            "success": True,
            "data": [
                {"computer": "srv-01", "name": "SQL Server", "version": "2019"},
                {"computer": "srv-02", "name": "SQL Server", "version": "2019"},
            ],
            "count": 2,
            "query_params": {"days": 90},
            "cached_at": "2026-03-27T00:00:00",
            "from_cache": True,
            "source": "inventory_cache",
            "full_dataset": True,
        }


class FakeFailingOSInventoryAgent(FakeOSInventoryAgent):
    async def clear_cache(self):
        raise RuntimeError("OS agent unavailable")


class FakePartialClearInventoryOrchestrator(FakeInventoryOrchestrator):
    def __init__(self) -> None:
        super().__init__()
        self.agents["os_inventory"] = FakeFailingOSInventoryAgent()


class FakeInventoryRepo:
    async def get_vm_inventory_with_eol(self, **_: object):
        return [
            {
                "vm_name": "srv-01",
                "resource_id": "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/srv-01",
                "os_name": "Windows Server 2019",
                "eol_date": "2029-01-09",
                "is_eol": False,
                "eol_software_name": "Windows Server 2019",
            }
        ]

    async def count_vm_inventory(self, **_: object):
        return 1


@pytest_asyncio.fixture
async def inventory_contract_client():
    app = FastAPI()
    app.include_router(inventory_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_inventory_returns_standard_response_with_metadata(inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakeInventoryOrchestrator(),
    )

    response = await inventory_contract_client.get("/api/inventory", params={"limit": 1, "days": 90})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert body["count"] == 1
    assert body["cached"] is True
    assert body["metadata"]["query_params"] == {"days": 90}
    assert body["metadata"]["cached_at"] == "2026-03-27T00:00:00"
    assert body["metadata"]["source"] == "inventory_cache"
    assert body["metadata"]["full_dataset"] is True


@pytest.mark.asyncio
async def test_inventory_status_returns_wrapped_object_payload(inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakeInventoryOrchestrator(),
    )

    response = await inventory_contract_client.get("/api/inventory/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["status"] == "ok"
    assert body["data"]["summary"]["total_software"] == 2


@pytest.mark.asyncio
async def test_os_endpoint_returns_paginated_items_payload(inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.inventory.get_or_init_repository",
        lambda *_args, **_kwargs: FakeInventoryRepo(),
    )

    response = await inventory_contract_client.get("/api/os", params={"limit": 50, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert isinstance(body["data"]["items"], list)
    assert body["data"]["total"] == 1
    assert body["data"]["limit"] == 50
    assert body["data"]["offset"] == 0
    assert body["data"]["items"][0]["vm_name"] == "srv-01"


@pytest.mark.asyncio
async def test_os_summary_returns_aggregated_list_payload(inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.inventory.get_or_init_repository",
        lambda *_args, **_kwargs: FakeInventoryRepo(),
    )

    response = await inventory_contract_client.get("/api/os/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["os_name"] == "Windows Server 2019"
    assert body["data"][0]["vm_count"] == 1


@pytest.mark.asyncio
async def test_inventory_reload_returns_wrapped_object_payload(inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakeInventoryOrchestrator(),
    )

    response = await inventory_contract_client.post("/api/inventory/reload?days=30")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["total_items"] == 42
    assert body["data"]["processing_time_seconds"] == 1.5


@pytest.mark.asyncio
async def test_inventory_clear_cache_uses_agent_registry_and_returns_wrapped_payload(
    inventory_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakeInventoryOrchestrator(),
    )

    response = await inventory_contract_client.post("/api/inventory/clear-cache")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["software_cache_cleared"] is True
    assert body["data"]["os_cache_cleared"] is True


@pytest.mark.asyncio
async def test_inventory_clear_cache_partial_failure_returns_error_contract(
    inventory_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakePartialClearInventoryOrchestrator(),
    )

    response = await inventory_contract_client.post("/api/inventory/clear-cache")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Failed to clear all inventory caches"
    assert body["metadata"]["software_cache_cleared"] is True
    assert body["metadata"]["os_cache_cleared"] is False
    assert body["metadata"]["partial_success"] is True
    assert body["metadata"]["error"] == "OS agent unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_cached"),
    [
        ("/api/inventory/raw/software?days=30&limit=1000", True),
        ("/api/inventory/raw/os?days=30&limit=2000", False),
    ],
)
async def test_raw_inventory_endpoints_return_standard_response_with_metadata(
    inventory_contract_client,
    monkeypatch,
    path,
    expected_cached,
):
    monkeypatch.setattr(
        "api.inventory._get_eol_orchestrator",
        lambda: FakeInventoryOrchestrator(),
    )

    response = await inventory_contract_client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert body["count"] == 1
    assert body["cached"] is expected_cached
    assert body["metadata"]["cached_at"] == "2026-03-27T00:00:00"
    assert body["metadata"]["query_params"]["days"] == 30