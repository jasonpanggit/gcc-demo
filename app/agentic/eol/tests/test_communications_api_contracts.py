"""Focused contract regressions for communications API normalization."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.communications import router as communications_router


class FakeEOLCommunicationsOrchestrator:
    def get_recent_communications(self):
        return [
            {
                "timestamp": "2026-03-27T00:00:00",
                "agent_name": "endoflife",
                "message": "hit",
            }
        ]

    def clear_communications(self):
        return {
            "success": True,
            "message": "Cleared 1 communications",
            "details": {"communications_cleared": 1, "cache_items_cleared": 0},
        }


class FakeInventoryAssistantOrchestrator:
    def __init__(self) -> None:
        self.orchestrator_logs = [{"id": 1}]
        self.agent_interaction_logs = [
            {"session_id": "session-1", "sender": "user_proxy", "recipient": "assistant", "content": "hello"},
            {"session_id": "session-2", "sender": "assistant", "recipient": "agent", "content": "world"},
        ]
        self.session_id = "main-session"

    async def get_agent_communications(self):
        return list(self.agent_interaction_logs)

    async def clear_communications(self):
        return {
            "success": True,
            "cleared": len(self.agent_interaction_logs),
            "new_session_id": "session-new",
        }


@pytest_asyncio.fixture
async def communications_contract_client():
    app = FastAPI()
    app.include_router(communications_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_eol_communications_returns_wrapped_object_payload(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.communications._get_eol_orchestrator",
        lambda: FakeEOLCommunicationsOrchestrator(),
    )

    response = await communications_contract_client.get("/api/communications/eol")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["communications"][0]["agent_name"] == "endoflife"
    assert body["data"]["count"] == 1


@pytest.mark.asyncio
async def test_inventory_assistant_communications_returns_wrapped_list_payload(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.communications._get_inventory_asst_orchestrator",
        lambda: FakeInventoryAssistantOrchestrator(),
    )
    monkeypatch.setattr("api.communications._get_inventory_asst_available", lambda: True)

    response = await communications_contract_client.get("/api/communications/inventory-assistant")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["count"] == 2
    assert body["data"]["communications"][0]["session_id"] == "session-1"
    assert body["metadata"]["source"] == "inventory_asst_orchestrator"


@pytest.mark.asyncio
async def test_inventory_assistant_clear_unavailable_returns_error_contract(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr("api.communications._get_inventory_asst_orchestrator", lambda: None)

    response = await communications_contract_client.post("/api/communications/inventory-assistant/clear")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "not available" in body["error"]
    assert body["count"] == 0


@pytest.mark.asyncio
async def test_session_communications_unavailable_returns_error_contract(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr("api.communications._get_inventory_asst_available", lambda: False)

    response = await communications_contract_client.get("/api/agent-communications/session-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "not available" in body["error"]
    assert body["count"] == 0


@pytest.mark.asyncio
async def test_session_communications_returns_wrapped_object_payload(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.communications._get_inventory_asst_orchestrator",
        lambda: FakeInventoryAssistantOrchestrator(),
    )
    monkeypatch.setattr("api.communications._get_inventory_asst_available", lambda: True)

    response = await communications_contract_client.get("/api/agent-communications/session-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["session_id"] == "session-1"
    assert len(body["data"]["communications"]) == 1
    assert body["data"]["all_communications_count"] == 2


@pytest.mark.asyncio
async def test_debug_agent_communications_unavailable_returns_error_contract(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr("api.communications._get_inventory_asst_available", lambda: False)

    response = await communications_contract_client.get("/api/debug/agent-communications")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "not available" in body["error"]
    assert body["count"] == 0


@pytest.mark.asyncio
async def test_debug_agent_communications_returns_collection_count(
    communications_contract_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "api.communications._get_inventory_asst_orchestrator",
        lambda: FakeInventoryAssistantOrchestrator(),
    )
    monkeypatch.setattr("api.communications._get_inventory_asst_available", lambda: True)

    response = await communications_contract_client.get("/api/debug/agent-communications")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["total_communications"] == 2
    assert len(body["data"]["communications"]) == 2