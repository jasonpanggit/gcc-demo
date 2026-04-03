"""Focused contract regressions for EOL response history endpoints."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.eol import router as eol_router


class FakeHistoryRepo:
    def __init__(self):
        self.responses = [
            {
                "session_id": "session-1",
                "software_name": "Windows Server",
                "agent_name": "endoflife_agent",
                "success": True,
            },
            {
                "session_id": "session-2",
                "software_name": "Python",
                "agent_name": "eolstatus_agent",
                "success": False,
            },
        ]

    async def list_recent_responses(self, limit=1000, offset=0):
        return self.responses[offset:offset + limit]

    async def get_responses_by_session(self, session_id):
        return [response for response in self.responses if response["session_id"] == session_id]


@pytest_asyncio.fixture
async def eol_history_contract_client():
    app = FastAPI()
    app.include_router(eol_router)
    app.state.eol_repo = FakeHistoryRepo()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def eol_history_uninitialized_client():
    app = FastAPI()
    app.include_router(eol_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_eol_agent_responses_returns_standard_list_payload(eol_history_contract_client):
    response = await eol_history_contract_client.get("/api/eol-agent-responses")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], list)
    assert body["data"][0]["software_name"] == "Windows Server"


@pytest.mark.asyncio
async def test_get_eol_agent_responses_without_repo_returns_error_contract(eol_history_uninitialized_client):
    response = await eol_history_uninitialized_client.get("/api/eol-agent-responses")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Repository not initialized - please try again in a moment"


@pytest.mark.asyncio
async def test_get_session_responses_returns_standard_list_payload(eol_history_contract_client):
    response = await eol_history_contract_client.get("/api/eol-agent-responses/session/session-1")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], list)
    assert body["data"][0]["session_id"] == "session-1"