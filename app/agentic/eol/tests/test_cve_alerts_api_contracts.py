"""Focused contract regressions for CVE alert rule API normalization."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.cve_alerts import router as cve_alerts_router


class FakeAlertRepo:
    def __init__(self):
        self.rules = {
            "rule-1": {
                "id": "rule-1",
                "name": "Critical CVEs",
                "enabled": True,
                "severity_levels": ["CRITICAL", "HIGH"],
                "email_recipients": ["admin@example.com"],
                "teams_enabled": True,
            }
        }

    async def list_rules(self, enabled_only=False):
        rules = list(self.rules.values())
        if enabled_only:
            rules = [rule for rule in rules if rule.get("enabled")]
        return rules

    async def create_rule(self, rule_data):
        created = {"id": "rule-2", **rule_data}
        self.rules[created["id"]] = created
        return created

    async def get_rule(self, rule_id):
        return self.rules.get(rule_id)

    async def update_rule(self, rule_data):
        self.rules[rule_data["id"]] = rule_data
        return rule_data

    async def delete_rule(self, rule_id):
        return self.rules.pop(rule_id, None) is not None


class FakeDispatcher:
    async def send_cve_alerts(self, **_kwargs):
        return {"sent": True, "email_count": 1, "teams_sent": True}


@pytest_asyncio.fixture
async def cve_alerts_contract_client(monkeypatch):
    app = FastAPI()
    app.include_router(cve_alerts_router, prefix="/api/cve")
    app.state.alert_repo = FakeAlertRepo()

    monkeypatch.setattr("api.cve_alerts.get_cve_alert_dispatcher", lambda: FakeDispatcher())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_alert_rules_returns_wrapped_object_payload(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.get("/api/cve/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["count"] == 1
    assert body["data"]["rules"][0]["id"] == "rule-1"


@pytest.mark.asyncio
async def test_create_alert_rule_returns_wrapped_object_payload(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.post(
        "/api/cve/alerts",
        json={
            "name": "New Rule",
            "severity_levels": ["CRITICAL"],
            "enabled": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["rule"]["id"]
    assert body["data"]["rule"]["name"] == "New Rule"


@pytest.mark.asyncio
async def test_delete_alert_rule_returns_wrapped_message_payload(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.delete("/api/cve/alerts/rule-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["deleted"] is True
    assert body["message"] == "Alert rule deleted"


@pytest.mark.asyncio
async def test_test_alert_rule_returns_wrapped_result_payload(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.post("/api/cve/alerts/rule-1/test")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["result"]["sent"] is True
    assert body["data"]["result"]["teams_sent"] is True


@pytest.mark.asyncio
async def test_missing_rule_returns_error_contract(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.get("/api/cve/alerts/missing-rule")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Alert rule missing-rule not found"


@pytest.mark.asyncio
async def test_create_alert_rule_missing_name_returns_error_contract(cve_alerts_contract_client):
    response = await cve_alerts_contract_client.post(
        "/api/cve/alerts",
        json={
            "severity_levels": ["CRITICAL"],
            "enabled": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Rule name is required"