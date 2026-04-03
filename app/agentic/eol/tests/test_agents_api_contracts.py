"""Focused contract regressions for agent management API normalization."""

from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.agents import router as agents_router


class FakeAgent:
    def __init__(self, urls=None, active=True):
        self.urls = list(urls or [])
        self.active = active


class FakeOrchestrator:
    def __init__(self):
        self.agents = {
            "microsoft": FakeAgent(
                urls=[{"url": "https://learn.microsoft.com/lifecycle", "description": "Microsoft lifecycle"}],
                active=True,
            ),
            "redhat": FakeAgent(urls=[], active=False),
        }

    async def get_agents_status(self):
        return {
            "success": True,
            "data": {
                "agents": {
                    "microsoft": {"status": "healthy", "initialized": True},
                    "redhat": {"status": "inactive", "initialized": True},
                },
                "total_agents": 2,
                "healthy_agents": 1,
            },
        }


@pytest_asyncio.fixture
async def agents_contract_client():
    app = FastAPI()
    app.include_router(agents_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_agents_status_returns_wrapped_object_payload(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: FakeOrchestrator())

    response = await agents_contract_client.get("/api/agents/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)
    assert body["data"]["total_agents"] == 2
    assert body["data"]["healthy_agents"] == 1


@pytest.mark.asyncio
async def test_list_agents_returns_wrapped_object_payload(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: FakeOrchestrator())

    response = await agents_contract_client.get("/api/agents/list")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert "microsoft" in body["data"]["agents"]
    assert body["data"]["agents"]["microsoft"]["active"] is True
    assert body["data"]["agents"]["redhat"]["active"] is False


@pytest.mark.asyncio
async def test_list_agents_uninitialized_orchestrator_returns_zero_count(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: None)

    response = await agents_contract_client.get("/api/agents/list")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 0
    assert body["data"]["agents"] == {}
    assert body["message"] == "EOL orchestrator is not initialized"


@pytest.mark.asyncio
async def test_add_agent_url_returns_wrapped_object_payload(agents_contract_client, monkeypatch):
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: orchestrator)

    response = await agents_contract_client.post(
        "/api/agents/add-url",
        json={
            "agent_name": "microsoft",
            "url": "https://learn.microsoft.com/lifecycle/products",
            "description": "Products",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["agent_name"] == "microsoft"
    assert body["data"]["url"] == "https://learn.microsoft.com/lifecycle/products"
    assert body["data"]["description"] == "Products"


@pytest.mark.asyncio
async def test_add_agent_url_without_description_keeps_dict_url_shape(agents_contract_client, monkeypatch):
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: orchestrator)

    response = await agents_contract_client.post(
        "/api/agents/add-url",
        json={
            "agent_name": "microsoft",
            "url": "https://example.test/eol-feed",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["description"] == ""
    assert isinstance(orchestrator.agents["microsoft"].urls[-1], dict)
    assert orchestrator.agents["microsoft"].urls[-1]["url"] == "https://example.test/eol-feed"


@pytest.mark.asyncio
async def test_remove_agent_url_returns_wrapped_object_payload(agents_contract_client, monkeypatch):
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: orchestrator)

    response = await agents_contract_client.post(
        "/api/agents/remove-url",
        json={
            "agent_name": "microsoft",
            "url": "https://learn.microsoft.com/lifecycle",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["agent_name"] == "microsoft"
    assert body["data"]["removed_url"] == "https://learn.microsoft.com/lifecycle"
    assert body["data"]["remaining_urls"] == 0


@pytest.mark.asyncio
async def test_toggle_agent_returns_wrapped_object_payload(agents_contract_client, monkeypatch):
    orchestrator = FakeOrchestrator()
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: orchestrator)

    response = await agents_contract_client.post(
        "/api/agents/toggle",
        json={
            "agent_name": "redhat",
            "active": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["agent_name"] == "redhat"
    assert body["data"]["active"] is True
    assert body["data"]["status"] == "enabled"


@pytest.mark.asyncio
async def test_add_agent_url_missing_agent_returns_error_contract(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: FakeOrchestrator())

    response = await agents_contract_client.post(
        "/api/agents/add-url",
        json={
            "agent_name": "missing-agent",
            "url": "https://example.test/eol",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Agent 'missing-agent' not found"


@pytest.mark.asyncio
async def test_remove_agent_url_missing_agent_returns_error_contract(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: FakeOrchestrator())

    response = await agents_contract_client.post(
        "/api/agents/remove-url",
        json={
            "agent_name": "missing-agent",
            "url": "https://example.test/eol",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Agent 'missing-agent' not found"


@pytest.mark.asyncio
async def test_toggle_agent_missing_agent_returns_error_contract(agents_contract_client, monkeypatch):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: FakeOrchestrator())

    response = await agents_contract_client.post(
        "/api/agents/toggle",
        json={
            "agent_name": "missing-agent",
            "active": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Agent 'missing-agent' not found"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/agents/add-url", {"agent_name": "microsoft", "url": "https://example.test/eol"}),
        ("/api/agents/remove-url", {"agent_name": "microsoft", "url": "https://example.test/eol"}),
        ("/api/agents/toggle", {"agent_name": "microsoft", "active": False}),
    ],
)
async def test_agent_write_endpoints_handle_missing_orchestrator(agents_contract_client, monkeypatch, path, payload):
    monkeypatch.setattr("api.agents._get_eol_orchestrator", lambda: None)

    response = await agents_contract_client.post(path, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "EOL orchestrator is not initialized"