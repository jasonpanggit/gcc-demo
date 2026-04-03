"""Focused API contract regressions for Phase 1 response normalization."""

import sys
from types import SimpleNamespace
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from api.eol import router as eol_router
from api.health import router as health_router
from utils import config
from utils.endpoint_decorators import with_timeout_and_stats
from utils.response_models import ensure_standard_format


class FakeEOLOrchestrator:
    """Minimal orchestrator stub for contract tests."""

    def __init__(self) -> None:
        self.session_id = "session-123"

    async def get_eol_data(self, software_name: str, version: str | None = None):
        return {
            "data": {
                "software_name": software_name,
                "version": version,
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09",
            },
            "primary_source": "endoflife",
            "all_sources": {"endoflife": {"eol_date": "2029-01-09"}},
            "agent_used": "endoflife",
        }

    async def search_software_eol(self, **_: object):
        return {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
            },
            "agent_used": "endoflife",
        }

    async def search_software_eol_internet(self, **_: object):
        return {
            "success": True,
            "data": {
                "software_name": "Windows Server",
                "version": "2019",
                "eol_date": "2029-01-09",
            },
            "agent_used": "playwright",
        }

    async def get_communication_history(self):
        return [{"agent": "endoflife", "message": "hit"}]

    async def get_autonomous_eol_data(self, software_name: str, version: str | None = None, **_: object):
        return {
            "success": True,
            "data": {
                "software_name": software_name,
                "version": version,
                "eol_date": "2029-01-09",
                "support_end_date": "2024-01-09",
                "status": "supported",
                "risk_level": "low",
                "confidence": 0.92,
            },
            "agent_used": "endoflife",
        }

    def clear_eol_agent_responses(self):
        return 3


class FakeInventoryAssistantOrchestrator:
    def clear_eol_agent_responses(self):
        return 2


@pytest_asyncio.fixture
async def contract_client():
    app = FastAPI()
    app.include_router(eol_router)
    app.include_router(health_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_eol_returns_standard_response_with_object_payload(contract_client, monkeypatch):
    fake = FakeEOLOrchestrator()

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: fake)

    response = await contract_client.get("/api/eol", params={"name": "Windows Server", "version": "2019"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["software_name"] == "Windows Server"
    assert body["data"]["primary_source"] == "endoflife"
    assert body["data"]["eol_data"]["eol_date"] == "2029-01-09"


@pytest.mark.asyncio
async def test_get_eol_without_name_returns_standard_error_contract(contract_client):
    response = await contract_client.get("/api/eol")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Either 'name' or 'software' parameter is required"


@pytest.mark.asyncio
async def test_get_eol_not_found_returns_standard_error_contract(contract_client, monkeypatch):
    fake = FakeEOLOrchestrator()
    fake.get_eol_data = AsyncMock(return_value={"data": None})

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: fake)

    response = await contract_client.get("/api/eol", params={"name": "MissingOS"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "No EOL data found for MissingOS"


@pytest.mark.asyncio
async def test_search_eol_returns_standard_response_with_search_metadata(contract_client, monkeypatch):
    fake = FakeEOLOrchestrator()

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: fake)

    response = await contract_client.post(
        "/api/search/eol",
        json={"software_name": "Windows Server", "software_version": "2019"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["session_id"] == "session-123"
    assert body["data"]["search_mode"] == "multi_agent"
    assert body["data"]["result"]["data"]["software_name"] == "Windows Server"
    assert body["data"]["communications"] == [{"agent": "endoflife", "message": "hit"}]


@pytest.mark.asyncio
async def test_clear_eol_agent_responses_returns_wrapped_object_payload(contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEOLOrchestrator())
    monkeypatch.setattr(
        "api.eol._get_inventory_asst_orchestrator",
        lambda: FakeInventoryAssistantOrchestrator(),
    )

    response = await contract_client.post("/api/eol-agent-responses/clear")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["cleared_counts"]["inventory_asst_orchestrator"] == 2
    assert body["data"]["cleared_counts"]["eol_orchestrator"] == 3
    assert body["data"]["total_cleared"] == 5


@pytest.mark.asyncio
async def test_batch_enrich_empty_request_returns_wrapped_payload(contract_client):
    response = await contract_client.post(
        "/api/eol/batch-enrich",
        json={"items": [], "max_concurrent": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 0
    assert isinstance(body["data"], dict)
    assert body["data"]["items"] == []
    assert body["data"]["total_items"] == 0
    assert body["message"] == "No items to enrich"


@pytest.mark.asyncio
async def test_batch_enrich_returns_items_with_summary_metadata(contract_client, monkeypatch):
    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: FakeEOLOrchestrator())
    monkeypatch.setattr("api.eol.eol_inventory.get", AsyncMock(return_value=None))

    response = await contract_client.post(
        "/api/eol/batch-enrich",
        json={
            "items": [
                {"name": "Windows Server", "version": "2019"},
                {"name": "Python", "version": "3.11"},
            ],
            "max_concurrent": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["total_items"] == 2
    assert len(body["data"]["items"]) == 2
    assert body["data"]["items"][0]["software_name"] == "Windows Server"
    assert body["data"]["items"][0]["source"] == "endoflife"
    assert "timestamp" in body["data"]


@pytest.mark.asyncio
async def test_batch_enrich_too_many_items_returns_standard_error_contract(contract_client):
    response = await contract_client.post(
        "/api/eol/batch-enrich",
        json={
            "items": [{"name": f"item-{index}", "version": "1.0"} for index in range(101)],
            "max_concurrent": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Maximum 100 items per batch request"


@pytest.mark.asyncio
async def test_batch_enrich_counts_all_items_when_some_lookups_fail(contract_client, monkeypatch):
    class MixedResultOrchestrator(FakeEOLOrchestrator):
        async def get_autonomous_eol_data(self, software_name: str, version: str | None = None, **kwargs: object):
            if software_name == "MissingOS":
                raise RuntimeError("lookup failed")
            return await super().get_autonomous_eol_data(software_name, version, **kwargs)

    monkeypatch.setattr("api.eol._get_eol_orchestrator", lambda: MixedResultOrchestrator())
    monkeypatch.setattr("api.eol.eol_inventory.get", AsyncMock(return_value=None))

    response = await contract_client.post(
        "/api/eol/batch-enrich",
        json={
            "items": [
                {"name": "Windows Server", "version": "2019"},
                {"name": "MissingOS", "version": "1.0"},
                {"name": "Python", "version": "3.11"},
            ],
            "max_concurrent": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 3
    assert len(body["data"]["items"]) == 3
    assert body["data"]["items"][1]["software_name"] == "MissingOS"
    assert body["data"]["items"][1]["error"] == "EOL data not available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/api/health/detailed", "ok"),
        ("/api/status", "running"),
    ],
)
async def test_health_endpoints_return_standard_response_with_object_payload(
    contract_client,
    monkeypatch,
    path,
    expected_status,
):
    monkeypatch.setattr(
        "api.health._get_inventory_asst_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.health.config.validate_config",
        lambda: {
            "valid": True,
            "services": {"postgres": "available"},
            "errors": [],
            "warnings": [],
        },
    )

    response = await contract_client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["status"] == expected_status


@pytest.mark.asyncio
async def test_health_endpoint_returns_unwrapped_monitoring_payload(contract_client, monkeypatch):
    monkeypatch.setattr(
        "api.health._get_inventory_asst_available",
        lambda: False,
    )
    monkeypatch.setattr("api.health.config.app.version", "9.9.9")

    response = await contract_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "9.9.9"
    assert body["inventory_asst_available"] is False
    assert "success" not in body


@pytest.mark.asyncio
async def test_inventory_health_endpoint_returns_unwrapped_payload_with_migration_stub(
    contract_client,
    monkeypatch,
):
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(
            _inventory_discovery_status={
                "enabled": True,
                "status": "completed",
                "subscriptions": {"sub-123": {"status": "completed", "resource_count": 12}},
                "error_count": 0,
            }
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "utils.resource_inventory_cache",
        SimpleNamespace(
            get_resource_inventory_cache=lambda: SimpleNamespace(
                get_statistics=lambda: {"l1_entries": 4, "hit_rate_percent": 88.0}
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "utils.inventory_scheduler",
        SimpleNamespace(get_inventory_scheduler=lambda: SimpleNamespace(running=True)),
    )

    response = await contract_client.get("/health/inventory")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["status"] == "completed"
    assert body["cache_statistics"]["l1_entries"] == 4
    assert body["scheduler"]["running"] is True
    assert body["cosmos_status"]["status"] == "removed"
    assert body["config"]["enable_inventory"] == config.inventory.enable_inventory
    assert "success" not in body


@pytest.mark.asyncio
async def test_cve_sync_health_returns_raw_fallback_payload_on_scheduler_error(contract_client, monkeypatch):
    def raise_scheduler_error():
        raise RuntimeError("scheduler offline")

    monkeypatch.setitem(
        sys.modules,
        "utils.cve_scheduler",
        SimpleNamespace(get_cve_scheduler=raise_scheduler_error),
    )

    response = await contract_client.get("/healthz/cve-sync")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["scheduler_running"] is False
    assert body["apscheduler_available"] is False
    assert body["error"] == "CVE sync scheduler unavailable"


@pytest.mark.asyncio
async def test_cve_scanner_health_returns_raw_fallback_payload_on_scanner_error(contract_client, monkeypatch):
    monkeypatch.setattr("api.health.config.cve_scanner.enable_scanner", True)
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(get_cve_scanner=AsyncMock(side_effect=RuntimeError("boom"))),
    )

    response = await contract_client.get("/healthz/cve-scanner")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["resource_graph_accessible"] is False
    assert body["scan_container_exists"] is False
    assert body["error"] == "boom"


def test_ensure_standard_format_preserves_success_dict_payload_fields():
    normalized = ensure_standard_format(
        {
            "success": True,
            "result": {"value": 1},
            "search_mode": "multi_agent",
        }
    )

    assert normalized["success"] is True
    assert normalized["count"] == 1
    assert normalized["data"] == {
        "result": {"value": 1},
        "search_mode": "multi_agent",
    }


def test_ensure_standard_format_infers_count_from_wrapped_collection_payload():
    normalized = ensure_standard_format(
        {
            "success": True,
            "vendors": ["endoflife", "eolstatus"],
            "vendor_routing": {
                "endoflife": ["endoflife_agent"],
                "eolstatus": ["eolstatus_agent"],
            },
        }
    )

    assert normalized["success"] is True
    assert normalized["count"] == 2
    assert normalized["data"]["vendors"] == ["endoflife", "eolstatus"]


def test_success_response_with_empty_dict_counts_as_single_object():
    response = ensure_standard_format({"success": True, "data": {}})

    assert response["success"] is True
    assert response["count"] == 1
    assert response["data"] == {}


def test_ensure_standard_format_infers_count_from_records_collection_key():
    normalized = ensure_standard_format(
        {
            "success": True,
            "records": [
                {"id": "record-1"},
                {"id": "record-2"},
                {"id": "record-3"},
            ],
        }
    )

    assert normalized["success"] is True
    assert normalized["count"] == 3
    assert len(normalized["data"]["records"]) == 3


@pytest.mark.asyncio
async def test_decorator_error_path_returns_standard_response_dict():
    app = FastAPI()

    @app.get("/failing")
    @with_timeout_and_stats(agent_name="contract_test", auto_wrap_response=True)
    async def failing_endpoint():
        raise ValueError("boom")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/failing")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "contract_test: boom"
    assert body["metadata"]["error_type"] == "ValueError"