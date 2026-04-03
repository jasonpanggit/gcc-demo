"""Focused contract regressions for OS extraction rule API normalization."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from api.eol import router as eol_router


class FakeOSExtractionRuleStore:
    def __init__(self):
        self.rules = [
            {
                "id": "rule-1",
                "name": "Windows Server",
                "pattern": r"Windows Server (?P<version>\d{4})",
                "source_scope": "combined",
                "derived_name_template": "Windows Server",
                "derived_version_template": "{version}",
                "priority": 100,
                "enabled": True,
                "is_default": False,
            }
        ]

    def get_rules(self):
        return list(self.rules)

    async def add_rule(self, payload):
        rule = {"id": "rule-2", **payload}
        self.rules.append(rule)
        return rule

    async def update_rule(self, rule_id, payload):
        for index, rule in enumerate(self.rules):
            if rule["id"] == rule_id:
                updated = {**rule, **payload}
                self.rules[index] = updated
                return updated
        return None

    async def delete_rule(self, rule_id):
        for rule in self.rules:
            if rule["id"] == rule_id:
                self.rules = [item for item in self.rules if item["id"] != rule_id]
                return True
        return False


@pytest_asyncio.fixture
async def os_rule_contract_client():
    app = FastAPI()
    app.include_router(eol_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_os_extraction_rules_returns_wrapped_list_payload(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol.os_extraction_rules_store", FakeOSExtractionRuleStore())

    response = await os_rule_contract_client.get("/api/os-extraction-rules")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["id"] == "rule-1"


@pytest.mark.asyncio
async def test_add_os_extraction_rule_returns_wrapped_list_payload(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol.os_extraction_rules_store", FakeOSExtractionRuleStore())

    response = await os_rule_contract_client.post(
        "/api/os-extraction-rules",
        json={
            "name": "Ubuntu",
            "pattern": r"Ubuntu (?P<version>\d+\.\d+)",
            "source_scope": "combined",
            "derived_name_template": "Ubuntu",
            "derived_version_template": "{version}",
            "priority": 90,
            "enabled": True,
            "flags": "IGNORECASE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["id"] == "rule-2"
    assert body["message"] == "OS extraction rule saved"


@pytest.mark.asyncio
async def test_update_os_extraction_rule_missing_returns_error_contract(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol.os_extraction_rules_store", FakeOSExtractionRuleStore())

    response = await os_rule_contract_client.put(
        "/api/os-extraction-rules/missing-rule",
        json={
            "name": "Ubuntu",
            "pattern": r"Ubuntu (?P<version>\d+\.\d+)",
            "source_scope": "combined",
            "derived_name_template": "Ubuntu",
            "derived_version_template": "{version}",
            "priority": 90,
            "enabled": True,
            "flags": "IGNORECASE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Rule not found"


@pytest.mark.asyncio
async def test_delete_os_extraction_rule_returns_wrapped_empty_list_payload(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr("api.eol.os_extraction_rules_store", FakeOSExtractionRuleStore())

    response = await os_rule_contract_client.delete("/api/os-extraction-rules/rule-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 0
    assert body["data"] == []
    assert body["message"] == "OS extraction rule deleted"


@pytest.mark.asyncio
async def test_test_os_extraction_rule_returns_wrapped_list_payload(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.eol.derive_os_name_version",
        lambda raw_name, raw_version=None: {
            "normalized_name": "Windows Server",
            "normalized_version": "2019",
            "strategy": "rule",
            "rule_name": "Windows Server",
            "raw_name": raw_name,
            "raw_version": raw_version,
        },
    )

    response = await os_rule_contract_client.post(
        "/api/os-extraction-rules/test",
        json={"raw_name": "Windows Server 2019 Datacenter", "raw_version": "2019"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["normalized_name"] == "Windows Server"


@pytest.mark.asyncio
async def test_reapply_os_extraction_rules_returns_wrapped_list_payload_with_metadata(os_rule_contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.eol.eol_inventory.reapply_os_normalization",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "raw_software_name": "Windows Server 2019 Datacenter",
                        "current": {"normalized_software_name": "Windows Server"},
                        "proposed": {"normalized_software_name": "Windows Server", "normalized_version": "2019"},
                        "requires_rekey": True,
                    }
                ],
                "scanned": 4,
                "changed": 1,
                "updated": 0,
                "errors": [],
            }
        ),
    )

    response = await os_rule_contract_client.post(
        "/api/os-extraction-rules/reapply",
        json={"apply_changes": False, "preview_limit": 25},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["metadata"]["scanned"] == 4
    assert body["metadata"]["changed"] == 1
    assert body["metadata"]["apply_changes"] is False
    assert body["message"] == "Cached OS normalization preview generated"