"""Unit tests for the Microsoft Agent Framework-based MCP orchestrator."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from agents.mcp_orchestrator import (
    MCPOrchestratorAgent,
    FunctionCallContent,
)


class SequentialChatStub:
    """Chat client stub that returns a predefined sequence of responses."""

    def __init__(self, responses: List[SimpleNamespace]) -> None:
        self._responses = responses
        self._calls = 0

    async def get_response(self, messages: List[Any], **_: Any) -> SimpleNamespace:
        index = min(self._calls, len(self._responses) - 1)
        self._calls += 1
        return self._responses[index]


class DummyMCPClient:
    """Captures tool invocations and exposes a static tool catalog."""

    def __init__(self, available_tools: List[Dict[str, Any]] | None = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._available_tools = list(available_tools or [])
        self.closed = False

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({"tool": tool_name, "arguments": arguments})
        return {"success": True, "tool_name": tool_name, "content": ["ok"]}

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return list(self._available_tools)

    async def aclose(self) -> None:
        self.closed = True


class AssistantMessageStub:
    """Minimal assistant message representation for orchestrator tests."""

    def __init__(self, *, contents: List[Any] | None = None, text: str = "") -> None:
        self.role = "assistant"
        self.contents = list(contents or [])
        self.text = text


class TextContentStub:
    """Simple content block containing text."""

    def __init__(self, text: str) -> None:
        self.text = text


class ClosableResourceStub:
    """Represents a dependency with an async close method."""

    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class AsyncCatalogMCPClient(DummyMCPClient):
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0)
        return super().get_available_tools()


@pytest.mark.asyncio
async def test_process_message_returns_failure_when_chat_unavailable(monkeypatch):
    orchestrator = MCPOrchestratorAgent(mcp_client=DummyMCPClient())

    async def fake_ensure_chat_client() -> bool:
        return False

    monkeypatch.setattr(orchestrator, "_ensure_chat_client", fake_ensure_chat_client)

    result = await orchestrator.process_message("status")
    assert result["success"] is False
    assert "MCP orchestration service" in result["response"]
    assert result["metadata"]["agent_framework_enabled"] is False


@pytest.mark.asyncio
async def test_process_message_without_tools_returns_text():
    assistant_message = AssistantMessageStub(contents=[TextContentStub("All clear")])
    chat_response = SimpleNamespace(messages=[assistant_message])
    chat_stub = SequentialChatStub([chat_response])
    orchestrator = MCPOrchestratorAgent(chat_client=chat_stub, mcp_client=DummyMCPClient())

    result = await orchestrator.process_message("give me status")
    assert result["success"] is True
    assert result["response"] == "All clear"
    assert result["metadata"]["tool_calls_made"] == 0


@pytest.mark.asyncio
async def test_process_message_invokes_tool_and_summarizes():
    dummy_client = DummyMCPClient(
        available_tools=[{"function": {"name": "azure_resource-groups-list"}}]
    )

    first_response = SimpleNamespace(
        messages=[
            AssistantMessageStub(
                contents=[
                    FunctionCallContent(
                        call_id="call-1",
                        name="azure_resource-groups-list",
                        arguments="{\"subscriptionId\": \"123\"}",
                    )
                ]
            )
        ]
    )
    second_response = SimpleNamespace(
        messages=[AssistantMessageStub(contents=[TextContentStub("Completed analysis")])]
    )
    chat_stub = SequentialChatStub([first_response, second_response])

    orchestrator = MCPOrchestratorAgent(chat_client=chat_stub, mcp_client=dummy_client)

    result = await orchestrator.process_message("List my resource groups")

    assert result["success"] is True
    assert result["response"] == "Completed analysis"
    assert result["metadata"]["tool_calls_made"] == 1
    assert dummy_client.calls == [
        {"tool": "azure_resource-groups-list", "arguments": {"subscriptionId": "123"}}
    ]


@pytest.mark.asyncio
async def test_list_available_tools_supports_async_catalog():
    async_client = AsyncCatalogMCPClient(available_tools=[{"function": {"name": "sample"}}])
    orchestrator = MCPOrchestratorAgent(mcp_client=async_client)

    result = await orchestrator.list_available_tools()

    assert result["success"] is True
    assert result["count"] == 1
    assert result["tools"][0]["function"]["name"] == "sample"


@pytest.mark.asyncio
async def test_aclose_releases_dependencies():
    chat_stub = ClosableResourceStub()
    mcp_stub = DummyMCPClient()
    credential_stub = ClosableResourceStub()
    orchestrator = MCPOrchestratorAgent(chat_client=chat_stub, mcp_client=mcp_stub)
    orchestrator._default_credential = credential_stub  # type: ignore[attr-defined]

    await orchestrator.aclose()

    assert chat_stub.closed is True
    assert mcp_stub.closed is True
    assert credential_stub.closed is True
    assert orchestrator._chat_client is None  # type: ignore[attr-defined]
    assert orchestrator._mcp_client is None  # type: ignore[attr-defined]
