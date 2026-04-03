"""Focused contract regressions for EOL verification and manual cache endpoints."""

import sys
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.eol import router as eol_router


class FakeEolOrchestrator:
    def __init__(self, success=True):
        self.success = success

    async def get_autonomous_eol_data(self, software_name: str, version: str | None = None):
        if not self.success:
            return {"success": False, "error": "not found"}
        return {
            "success": True,
            "data": {
                "software_name": software_name,
                "version": version,
                "eol_date": "2029-01-09",
            },
            "agent_used": "endoflife",
        }


class FakeEolCache:
    def __init__(self):
        self.deleted = []
        self.cached = []

    async def delete_failed_cache_entry(self, **kwargs):
        self.deleted.append(dict(kwargs))

    async def cache_response(self, **kwargs):
        self.cached.append(dict(kwargs))


@pytest_asyncio.fixture
async def eol_verification_contract_client():
    app = FastAPI()
    app.include_router(eol_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_verify_eol_result_returns_wrapped_object_payload(eol_verification_contract_client, monkeypatch):
    fake_cache = FakeEolCache()
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEolOrchestrator(success=True))
    monkeypatch.setitem(sys.modules, "utils.eol_cache", SimpleNamespace(eol_cache=fake_cache))

    response = await eol_verification_contract_client.post(
        "/api/verify-eol-result",
        json={
            "software_name": "Windows Server",
            "software_version": "2019",
            "agent_name": "endoflife",
            "verification_status": "verified",
            "source_url": "https://endoflife.date/windows-server",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["verification_status"] == "verified"
    assert body["data"]["software_name"] == "Windows Server"
    assert body["data"]["cache_updated"] is True
    assert fake_cache.cached[0]["priority"] == 2


@pytest.mark.asyncio
async def test_verify_eol_result_failed_verification_returns_wrapped_object_payload(eol_verification_contract_client, monkeypatch):
    fake_cache = FakeEolCache()
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEolOrchestrator(success=True))
    monkeypatch.setitem(sys.modules, "utils.eol_cache", SimpleNamespace(eol_cache=fake_cache))

    response = await eol_verification_contract_client.post(
        "/api/verify-eol-result",
        json={
            "software_name": "Windows Server",
            "software_version": "2019",
            "agent_name": "endoflife",
            "verification_status": "failed",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["verification_status"] == "failed"
    assert body["data"]["cache_cleared"] is True
    assert fake_cache.deleted[0]["software_name"] == "Windows Server"


@pytest.mark.asyncio
async def test_verify_eol_result_missing_data_returns_error_contract(eol_verification_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEolOrchestrator(success=False))

    response = await eol_verification_contract_client.post(
        "/api/verify-eol-result",
        json={
            "software_name": "Missing Product",
            "software_version": "1.0",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "No EOL data found to verify"


@pytest.mark.asyncio
async def test_cache_eol_result_returns_wrapped_object_payload(eol_verification_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEolOrchestrator(success=True))

    response = await eol_verification_contract_client.post(
        "/api/cache-eol-result",
        json={
            "software_name": "MySQL",
            "software_version": "5.7",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["software_name"] == "MySQL"
    assert body["data"]["software_version"] == "5.7"
    assert body["data"]["agent_used"] == "endoflife"


@pytest.mark.asyncio
async def test_cache_eol_result_missing_data_returns_error_contract(eol_verification_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEolOrchestrator(success=False))

    response = await eol_verification_contract_client.post(
        "/api/cache-eol-result",
        json={
            "software_name": "Unknown Product",
            "software_version": "0.1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "No EOL data found to cache"