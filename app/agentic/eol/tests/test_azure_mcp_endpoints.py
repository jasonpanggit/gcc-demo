"""Test suite for Azure MCP Server API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest


class DummyMCPClient:
    """Lightweight stub that mimics the Azure MCP client contract."""

    def __init__(
        self,
        *,
        initialized: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
        call_tool_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._initialized = initialized
        self._tools = tools or []
        self._call_tool_result = call_tool_result or {
            "success": True,
            "tool_name": "dummy",
            "content": ["ok"],
        }
        self.resource_groups_result: Dict[str, Any] = {"success": True, "groups": []}
        self.storage_accounts_result: Dict[str, Any] = {"success": True, "accounts": []}
        self.query_result: Dict[str, Any] = {"success": True, "rows": []}

    def is_initialized(self) -> bool:
        return self._initialized

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return list(self._tools)

    def get_auth_mode(self) -> str:
        """Return mock authentication mode."""
        return "DefaultAzureCredential"

    async def list_resource_groups(self) -> Dict[str, Any]:
        return self.resource_groups_result

    async def list_storage_accounts(self, resource_group: Optional[str] = None) -> Dict[str, Any]:
        return self.storage_accounts_result

    async def get_resource_by_id(self, resource_id: str) -> Dict[str, Any]:
        return {"success": True, "resource_id": resource_id}

    async def query_resources(
        self,
        *,
        query: str,
        cluster_uri: Optional[str] = None,
        database: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = dict(self.query_result)
        payload.setdefault("query", query)
        if cluster_uri:
            payload.setdefault("cluster_uri", cluster_uri)
        if database:
            payload.setdefault("database", database)
        return payload

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if callable(self._call_tool_result):
            return self._call_tool_result(tool_name, arguments)
        payload = dict(self._call_tool_result)
        payload.setdefault("tool_name", tool_name)
        payload.setdefault("arguments", arguments)
        return payload


class DummyOrchestrator:
    """Stub orchestrator used to isolate FastAPI routes from dependencies."""

    def __init__(self, *, success: bool = True, response_text: str = "Stub response") -> None:
        self.success = success
        self.response_text = response_text
        self.history: List[Dict[str, Any]] = [
            {"role": "assistant", "content": "previous", "timestamp": "2024-01-01T00:00:00Z"}
        ]
        self.cleared = False

    async def process_message(self, message: str) -> Dict[str, Any]:
        if not self.success:
            return {"success": False, "error": "orchestration_failed"}
        return {
            "success": True,
            "response": self.response_text,
            "conversation_history": self.history,
            "metadata": {"session_id": "maf-test-session", "reasoning_trace": []},
        }

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def clear_conversation(self) -> None:
        self.cleared = True


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_azure_mcp_status_success(client, monkeypatch):
    dummy_client = DummyMCPClient(tools=[{"function": {"name": "azure_resource-groups-list"}}])

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    response = await client.get("/api/azure-mcp/status")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    status = payload["data"][0]
    assert status["initialized"] is True
    assert status["available_tools_count"] == 1
    assert payload["metadata"]["agent"] == "azure_mcp"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_azure_mcp_tools_formats_response(client, monkeypatch):
    tools = [
        {
            "function": {
                "name": "azure_storage-accounts-list",
                "description": "List storage accounts",
                "parameters": {"type": "object"},
            }
        }
    ]
    dummy_client = DummyMCPClient(tools=tools)

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    response = await client.get("/api/azure-mcp/tools")
    assert response.status_code == 200

    payload = response.json()
    tool_payload = payload["data"][0]
    assert tool_payload["name"] == "azure_storage-accounts-list"
    assert tool_payload["description"] == "List storage accounts"
    assert "parameters" in tool_payload


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_azure_mcp_tools_filters_matches(client, monkeypatch):
    tools = [
        {"function": {"name": "azure_vm-list", "description": "List virtual machines"}},
        {"function": {"name": "azure_storage-accounts-list", "description": "Storage overview"}},
    ]
    dummy_client = DummyMCPClient(tools=tools)

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    response = await client.get("/api/azure-mcp/tools/search", params={"pattern": "storage"})
    assert response.status_code == 200

    payload = response.json()
    assert len(payload["data"]) == 1
    assert payload["data"][0]["name"] == "azure_storage-accounts-list"
    assert payload["metadata"]["matches_found"] == 1


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_azure_resources_wraps_client_response(client, monkeypatch):
    dummy_client = DummyMCPClient()
    dummy_client.query_result = {"success": True, "rows": [{"name": "rg-demo"}]}

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    request_payload = {"query": "Resources | take 1", "cluster_uri": None, "database": None}
    response = await client.post("/api/azure-mcp/query", json=request_payload)
    assert response.status_code == 200

    payload = response.json()
    assert payload["data"][0]["rows"] == [{"name": "rg-demo"}]
    assert payload["metadata"]["operation"] == "query_azure_monitor"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_azure_mcp_tool_success(client, monkeypatch):
    dummy_client = DummyMCPClient(
        call_tool_result={"success": True, "content": ["done"], "tool_name": "azure_vm-get"}
    )

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    response = await client.post(
        "/api/azure-mcp/call-tool",
        json={"tool_name": "azure_vm-get", "arguments": {"name": "vm01"}},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["data"][0]["tool_name"] == "azure_vm-get"
    assert payload["metadata"]["tool_name"] == "azure_vm-get"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_call_azure_mcp_tool_failure_returns_500(client, monkeypatch):
    dummy_client = DummyMCPClient(call_tool_result={"success": False, "error": "boom"})

    async def fake_get_client():
        return dummy_client

    monkeypatch.setattr("api.azure_mcp.get_azure_mcp_client", fake_get_client)

    response = await client.post(
        "/api/azure-mcp/call-tool",
        json={"tool_name": "azure_vm-get", "arguments": {"name": "vm01"}},
    )
    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"] == "Tool call failed: boom"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_chat_success(client, monkeypatch):
    orchestrator = DummyOrchestrator(response_text="Here is the summary")

    async def fake_get_orchestrator():
        return orchestrator

    monkeypatch.setattr("agents.mcp_orchestrator.get_mcp_orchestrator", fake_get_orchestrator)

    response = await client.post("/api/azure-mcp/chat", json={"message": "summarize"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["data"][0]["response"] == "Here is the summary"
    assert payload["metadata"]["session_id"] == "maf-test-session"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_chat_failure_returns_500(client, monkeypatch):
    orchestrator = DummyOrchestrator(success=False)

    async def fake_get_orchestrator():
        return orchestrator

    monkeypatch.setattr("agents.mcp_orchestrator.get_mcp_orchestrator", fake_get_orchestrator)

    response = await client.post("/api/azure-mcp/chat", json={"message": "run"})
    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"] == "orchestration_failed"


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_chat_history_uses_stub(client, monkeypatch):
    orchestrator = DummyOrchestrator()

    async def fake_get_orchestrator():
        return orchestrator

    monkeypatch.setattr("agents.mcp_orchestrator.get_mcp_orchestrator", fake_get_orchestrator)

    response = await client.get("/api/azure-mcp/chat/history")
    assert response.status_code == 200

    payload = response.json()
    history = payload["data"][0]["history"]
    assert history[0]["content"] == "previous"
    assert payload["metadata"]["message_count"] == len(history)


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_chat_confirms_operation(client, monkeypatch):
    orchestrator = DummyOrchestrator()

    async def fake_get_orchestrator():
        return orchestrator

    monkeypatch.setattr("agents.mcp_orchestrator.get_mcp_orchestrator", fake_get_orchestrator)

    response = await client.post("/api/azure-mcp/chat/clear")
    assert response.status_code == 200

    payload = response.json()
    assert payload["data"][0]["message"] == "Conversation cleared successfully"
    assert orchestrator.cleared is True
