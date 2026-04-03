"""Focused contract regressions for vendor parsing API normalization."""

import sys
from types import ModuleType

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from api.eol import router as eol_router


class FakeVendorAgent:
    def __init__(self):
        self.eol_urls = {
            "lifecycle": {
                "url": "https://learn.microsoft.com/lifecycle/products",
                "description": "Microsoft lifecycle",
                "priority": 1,
                "active": True,
            }
        }

    async def fetch_all_from_url(self, url: str, software_hint: str):
        return [
            {
                "software_name": software_hint,
                "version": "2019",
                "eol": "2029-01-09",
                "support": "2024-01-09",
                "confidence": 0.95,
            }
        ]


class FakeVendorOrchestrator:
    def __init__(self):
        self.vendor_routing = {"microsoft": ["windows-server"]}
        self.agents = {"microsoft": FakeVendorAgent()}


@pytest_asyncio.fixture
async def vendor_contract_client():
    app = FastAPI()
    app.include_router(eol_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_vendors_returns_wrapped_object_payload(vendor_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeVendorOrchestrator())

    response = await vendor_contract_client.get("/api/vendors")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["vendors"] == ["microsoft"]
    assert body["data"]["vendor_routing"]["microsoft"] == ["windows-server"]


@pytest.mark.asyncio
async def test_list_vendors_fallback_uses_vendor_count(vendor_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: (_ for _ in ()).throw(RuntimeError("offline")))

    response = await vendor_contract_client.get("/api/vendors")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert body["metadata"]["warning"] == "Vendor API fallback; orchestrator unavailable"
    assert body["data"]["vendors"] == ["endoflife", "eolstatus"]


@pytest.mark.asyncio
async def test_search_vendor_eol_returns_wrapped_object_payload(vendor_contract_client, monkeypatch):
    helper_module = ModuleType("utils.vendor_parsing_helper")

    async def parse_vendor_urls_generic(**_: object):
        return [
            {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09",
                "agent_used": "microsoft",
                "confidence": 0.95,
                "source_url": "https://learn.microsoft.com/lifecycle/products",
                "success": True,
                "mode": "microsoft_generic_urls",
            }
        ]

    helper_module.parse_vendor_urls_generic = parse_vendor_urls_generic

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeVendorOrchestrator())
    monkeypatch.setattr("api.eol.eol_inventory.upsert", AsyncMock(return_value=True))
    monkeypatch.setattr("api.eol.eol_inventory._has_pool", lambda: False)
    monkeypatch.setattr(
        "api.eol.vendor_url_inventory.upsert_vendor_urls",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(sys.modules, "utils.vendor_parsing_helper", helper_module)

    response = await vendor_contract_client.post(
        "/api/search/eol/vendor",
        json={"vendor": "microsoft", "mode": "agents_only", "ignore_cache": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["vendor"] == "microsoft"
    assert body["data"]["mode"] == "microsoft_generic_urls"
    assert body["data"]["summary"]["successes"] == 1
    assert len(body["data"]["runs"]) == 1
    assert body["data"]["runs"][0]["software_name"] == "Windows Server"
    assert body["data"]["urls_persisted"] is True


@pytest.mark.asyncio
async def test_search_vendor_eol_zero_success_runs_still_report_run_count(vendor_contract_client, monkeypatch):
    helper_module = ModuleType("utils.vendor_parsing_helper")

    async def parse_vendor_urls_generic(**_: object):
        return [
            {
                "software_name": "Windows Server",
                "version": "2019",
                "success": False,
                "error": "parse failed",
                "mode": "microsoft_generic_urls",
            },
            {
                "software_name": "Windows Server",
                "version": "2022",
                "success": False,
                "error": "parse failed",
                "mode": "microsoft_generic_urls",
            },
        ]

    helper_module.parse_vendor_urls_generic = parse_vendor_urls_generic

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeVendorOrchestrator())
    monkeypatch.setattr("api.eol.eol_inventory.upsert", AsyncMock(return_value=True))
    monkeypatch.setattr("api.eol.eol_inventory._has_pool", lambda: False)
    monkeypatch.setattr(
        "api.eol.vendor_url_inventory.upsert_vendor_urls",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(sys.modules, "utils.vendor_parsing_helper", helper_module)

    response = await vendor_contract_client.post(
        "/api/search/eol/vendor",
        json={"vendor": "microsoft", "mode": "agents_only", "ignore_cache": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert body["data"]["summary"]["successes"] == 0
    assert body["data"]["summary"]["requested"] == 1
    assert body["data"]["summary"]["failures"] == 1
    assert len(body["data"]["runs"]) == 2


@pytest.mark.asyncio
async def test_search_vendor_eol_invalid_vendor_returns_error_contract(vendor_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeVendorOrchestrator())

    response = await vendor_contract_client.post(
        "/api/search/eol/vendor",
        json={"vendor": "unknown-vendor"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Vendor 'unknown-vendor' not found"


@pytest.mark.asyncio
async def test_search_vendor_eol_microsoft_branch_persists_success_count(vendor_contract_client, monkeypatch):
    upsert_urls = AsyncMock(return_value=True)

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeVendorOrchestrator())
    monkeypatch.setattr("api.eol.eol_inventory.upsert", AsyncMock(return_value=True))
    monkeypatch.setattr("api.eol.eol_inventory._has_pool", lambda: False)
    monkeypatch.setattr("api.eol.vendor_url_inventory.upsert_vendor_urls", upsert_urls)
    monkeypatch.setitem(sys.modules, "utils.vendor_parsing_helper", ModuleType("utils.vendor_parsing_helper"))

    response = await vendor_contract_client.post(
        "/api/search/eol/vendor",
        json={"vendor": "microsoft", "mode": "agents_only", "ignore_cache": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["summary"]["successes"] == 1
    upsert_urls.assert_awaited_once()
    assert upsert_urls.await_args.kwargs["software_found"] == 1