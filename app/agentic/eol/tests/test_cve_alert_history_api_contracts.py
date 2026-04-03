"""Focused contract regressions for CVE alert history API normalization."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.cve_alert_history import router as cve_alert_history_router


class FakeAlertHistoryRepo:
    def __init__(self):
        self.records = {
            "record-1": {
                "id": "record-1",
                "timestamp": "2026-03-27T08:00:00Z",
                "alert_type": "critical",
                "cve_count": 2,
                "affected_vm_count": 1,
                "affected_vm_names": ["vm-01"],
                "cve_ids": ["CVE-2026-0001", "CVE-2026-0002"],
                "acknowledged": False,
                "dismissed": False,
                "escalated": False,
                "channels_sent": ["email"],
            }
        }

    async def query_history(self, filters, limit, offset):
        records = list(self.records.values())
        if filters.get("alert_type"):
            records = [record for record in records if record["alert_type"] == filters["alert_type"]]
        return records[offset: offset + limit]

    async def get_record(self, record_id):
        return self.records.get(record_id)

    async def acknowledge(self, record_id, user, note):
        record = self.records.get(record_id)
        if not record or record.get("acknowledged"):
            return False
        record["acknowledged"] = True
        record["acknowledged_by"] = user
        record["acknowledged_note"] = note
        return True

    async def dismiss(self, record_id, reason):
        record = self.records.get(record_id)
        if not record or record.get("dismissed"):
            return False
        record["dismissed"] = True
        record["dismissed_reason"] = reason
        return True


@pytest_asyncio.fixture
async def cve_alert_history_contract_client():
    app = FastAPI()
    app.include_router(cve_alert_history_router, prefix="/api/cve")
    app.state.alert_repo = FakeAlertHistoryRepo()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_query_alert_history_returns_wrapped_object_payload(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.get("/api/cve/alerts/history", params={"alert_type": "critical"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["count"] == 1
    assert body["data"]["records"][0]["id"] == "record-1"
    assert body["data"]["filters"]["alert_type"] == "critical"


@pytest.mark.asyncio
async def test_get_alert_details_returns_wrapped_object_payload(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.get("/api/cve/alerts/history/record-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["record"]["id"] == "record-1"


@pytest.mark.asyncio
async def test_acknowledge_alert_returns_wrapped_object_payload(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.post(
        "/api/cve/alerts/history/record-1/acknowledge",
        json={"user": "jason", "note": "Patch scheduled"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["record_id"] == "record-1"
    assert body["data"]["acknowledged_by"] == "jason"


@pytest.mark.asyncio
async def test_dismiss_alert_returns_wrapped_object_payload(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.post(
        "/api/cve/alerts/history/record-1/dismiss",
        json={"reason": "False positive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["record_id"] == "record-1"
    assert body["data"]["reason"] == "False positive"


@pytest.mark.asyncio
async def test_missing_alert_history_record_returns_error_contract(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.get("/api/cve/alerts/history/missing-record")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Alert missing-record not found"


@pytest.mark.asyncio
async def test_acknowledge_alert_missing_user_returns_error_contract(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.post(
        "/api/cve/alerts/history/record-1/acknowledge",
        json={"note": "Patch scheduled"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "User is required for acknowledgment"


@pytest.mark.asyncio
async def test_dismiss_alert_missing_reason_returns_error_contract(cve_alert_history_contract_client):
    response = await cve_alert_history_contract_client.post(
        "/api/cve/alerts/history/record-1/dismiss",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Dismissal reason is required"