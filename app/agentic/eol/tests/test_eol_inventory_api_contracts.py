"""Focused contract regressions for EOL inventory maintenance endpoints."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
import sys

from api.eol import router as eol_router


class FakeEolRepo:
    def __init__(self):
        self.record = {
            "id": "record-1",
            "software_key": "windows-server:2019",
            "software_name": "Windows Server",
            "version": "2019",
            "eol_date": "2029-01-09",
            "status": "supported",
        }
        self.upsert_error = None

    async def get_by_key(self, software_key):
        if software_key == self.record["software_key"]:
            return dict(self.record)
        return None

    async def upsert_eol_record(self, **kwargs):
        if self.upsert_error:
            raise self.upsert_error
        self.record = {
            **self.record,
            "software_key": kwargs.get("software_key", self.record["software_key"]),
            "software_name": kwargs.get("software_name") or self.record["software_name"],
            "version": kwargs.get("version_key") or self.record["version"],
            "status": kwargs.get("status") or self.record["status"],
            "eol_date": kwargs.get("eol_date") or self.record["eol_date"],
            "risk_level": kwargs.get("risk_level"),
        }

    async def list_by_vendor(self, vendor, limit=100, offset=0):
        records = [
            dict(self.record),
            {
                **self.record,
                "id": "record-2",
                "software_key": f"{vendor}:3.11",
                "software_name": vendor.title(),
                "version": "3.11",
            },
        ]
        return records[offset:offset + limit], len(records)


@pytest_asyncio.fixture
async def eol_inventory_contract_client():
    app = FastAPI()
    app.include_router(eol_router)
    app.state.eol_repo = FakeEolRepo()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_eol_inventory_record_returns_wrapped_object_payload(eol_inventory_contract_client):
    response = await eol_inventory_contract_client.get("/api/eol-inventory/windows-server:2019")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["software_key"] == "windows-server:2019"


@pytest.mark.asyncio
async def test_get_eol_inventory_record_missing_returns_error_contract(eol_inventory_contract_client):
    response = await eol_inventory_contract_client.get("/api/eol-inventory/missing-key")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "EOL record not found: missing-key"


@pytest.mark.asyncio
async def test_update_eol_inventory_record_returns_wrapped_object_payload(eol_inventory_contract_client):
    response = await eol_inventory_contract_client.put(
        "/api/eol-inventory/record-1",
        params={"software_key": "windows-server:2019"},
        json={"software_name": "Windows Server", "version": "2022", "eol_date": "2031-10-14", "status": "supported"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["record_id"] == "record-1"
    assert body["data"]["software_key"] == "windows-server:2019"
    assert body["data"]["updates"]["version"] == "2022"


@pytest.mark.asyncio
async def test_update_eol_inventory_record_without_fields_returns_error_contract(eol_inventory_contract_client):
    response = await eol_inventory_contract_client.put(
        "/api/eol-inventory/record-1",
        params={"software_key": "windows-server:2019"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "No update fields provided"


@pytest.mark.asyncio
async def test_delete_eol_inventory_record_returns_wrapped_object_payload(eol_inventory_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol.eol_inventory.delete_record", AsyncMock(return_value=True))

    response = await eol_inventory_contract_client.delete(
        "/api/eol-inventory/record-1",
        params={"software_key": "windows-server:2019"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["deleted"] is True
    assert body["data"]["record_id"] == "record-1"


@pytest.mark.asyncio
async def test_bulk_delete_eol_inventory_records_returns_wrapped_object_payload(eol_inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.eol.eol_inventory.delete_records",
        AsyncMock(side_effect=lambda items: {"deleted": 2, "failed": [], "requested": len(items)}),
    )

    response = await eol_inventory_contract_client.post(
        "/api/eol-inventory/bulk-delete",
        json={
            "items": [
                {"record_id": "record-1", "software_key": "windows-server:2019"},
                {"record_id": "record-2", "software_key": "python:3.11"},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["deleted"] == 2
    assert body["data"]["requested"] == 2
    assert body["data"]["failed"] == []


@pytest.mark.asyncio
async def test_bulk_delete_eol_inventory_records_failure_returns_error_contract(eol_inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.eol.eol_inventory.delete_records",
        AsyncMock(return_value={"deleted": 0, "failed": [{"record_id": "record-1", "error": "not found"}]}),
    )

    response = await eol_inventory_contract_client.post(
        "/api/eol-inventory/bulk-delete",
        json={"items": [{"record_id": "record-1", "software_key": "windows-server:2019"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Bulk delete failed"
    assert body["metadata"]["failed"][0]["record_id"] == "record-1"


@pytest.mark.asyncio
async def test_purge_all_eol_inventory_records_returns_wrapped_object_payload(eol_inventory_contract_client, monkeypatch):
    class FakeOrchestrator:
        def __init__(self):
            self.eol_cache = {"key-1": {"eol_date": "2029-01-09"}, "key-2": {"eol_date": "2031-10-14"}}

    class FakeMainModule:
        @staticmethod
        def get_eol_orchestrator():
            return FakeOrchestrator()

    monkeypatch.setitem(sys.modules, "main", FakeMainModule)
    monkeypatch.setattr("api.eol.eol_inventory.purge_all", AsyncMock(return_value=7))

    response = await eol_inventory_contract_client.post("/api/eol-inventory/purge-all")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["deleted"] == 7
    assert body["data"]["memory_cleared"] == 2


@pytest.mark.asyncio
async def test_list_eol_by_vendor_returns_item_count_for_collection_payload(eol_inventory_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.eol.eol_inventory.list_by_vendor",
        AsyncMock(return_value=(
            [
                {"software_key": "python:3.10", "software_name": "Python", "version": "3.10"},
                {"software_key": "python:3.11", "software_name": "Python", "version": "3.11"},
            ],
            2,
        )),
    )

    response = await eol_inventory_contract_client.get("/api/eol-inventory/vendor/python")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 2