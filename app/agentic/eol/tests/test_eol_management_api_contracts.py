"""Focused contract regressions for the EOL management endpoint."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.eol import router as eol_router


class FakeManagementRepo:
    def __init__(self, vms):
        self.vms = vms

    async def get_vm_eol_management(self, subscription_id=None, limit=50, offset=0):
        return list(self.vms)


@pytest_asyncio.fixture
async def eol_management_client():
    app = FastAPI()
    app.include_router(eol_router)
    app.state.eol_repo = FakeManagementRepo(
        [
            {
                "vm_name": "vm-001",
                "os_name": "Windows Server",
                "os_version": "2019",
                "eol_status": "supported",
            },
            {
                "vm_name": "vm-002",
                "os_name": "Ubuntu",
                "os_version": "22.04",
                "eol_status": "supported",
            },
        ]
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_eol_management_returns_wrapped_object_payload(eol_management_client):
    response = await eol_management_client.get(
        "/api/eol-management",
        params={"subscription_id": "sub-123", "limit": 10, "offset": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["total"] == 2
    assert body["data"]["offset"] == 5
    assert body["data"]["limit"] == 10
    assert len(body["data"]["items"]) == 2
    assert body["data"]["items"][0]["vm_name"] == "vm-001"


@pytest.mark.asyncio
async def test_get_eol_management_empty_returns_zero_count_with_object_payload():
    app = FastAPI()
    app.include_router(eol_router)
    app.state.eol_repo = FakeManagementRepo([])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/eol-management")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 0
    assert isinstance(body["data"], dict)
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0
    assert body["message"] == "No VM EOL management data available"