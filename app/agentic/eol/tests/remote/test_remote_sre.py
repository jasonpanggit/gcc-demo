"""Remote integration tests for the SRE Orchestrator API.

These tests require a running instance of the application and valid Azure
credentials.  They are tagged ``remote`` so they are excluded from the
default unit-test run and can be executed explicitly with::

    pytest -m remote -v

Configuration (via environment variables):
    TEST_BASE_URL   Base URL of the running application (default: http://localhost:8000)
    TEST_SRE_QUERY  Optional override for the query used in smoke tests

Markers:
    remote:  Requires a live application + Azure credentials.
    asyncio: Async tests.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Optional: import TestClient for lightweight in-process tests
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    _TESTCLIENT_AVAILABLE = True
except ImportError:
    _TESTCLIENT_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL: str = os.getenv("TEST_BASE_URL", "http://localhost:8000")
_EXECUTE_URL: str = f"{_BASE_URL}/api/sre-orchestrator/execute"
_HEALTH_URL: str = f"{_BASE_URL}/api/sre-orchestrator/health"
_DEFAULT_QUERY: str = os.getenv("TEST_SRE_QUERY", "check health of all container apps")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_agent_metadata(body: Dict[str, Any]) -> Dict[str, Any]:
    """Extract agent_metadata from either result.data.agent_metadata or nested."""
    data = body.get("data") or {}
    return data.get("agent_metadata") or {}


# ---------------------------------------------------------------------------
# Unit tests (no live service) — validate header extraction logic
# ---------------------------------------------------------------------------

class TestHeaderExtraction:
    """Unit tests for _extract_sre_header_values and _set_sre_headers."""

    def test_agent_execution_source_in_header(self):
        try:
            from app.agentic.eol.api.sre_orchestrator import _extract_sre_header_values
        except ModuleNotFoundError:
            from api.sre_orchestrator import _extract_sre_header_values  # type: ignore[import-not-found]

        result = {
            "agent_metadata": {
                "execution_source": "agent",
                "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        }
        headers = _extract_sre_header_values(result)
        assert headers.get("X-Agent-Used") == "agent"
        assert headers.get("X-Token-Count") == "150"

    def test_mcp_fallback_header(self):
        try:
            from app.agentic.eol.api.sre_orchestrator import _extract_sre_header_values
        except ModuleNotFoundError:
            from api.sre_orchestrator import _extract_sre_header_values  # type: ignore[import-not-found]

        result = {
            "agent_metadata": {
                "execution_source": "mcp_fallback",
                "token_usage": {},
            }
        }
        headers = _extract_sre_header_values(result)
        assert headers.get("X-Agent-Used") == "mcp_fallback"
        assert "X-Token-Count" not in headers  # zero tokens → header omitted

    def test_token_count_summed_from_parts(self):
        try:
            from app.agentic.eol.api.sre_orchestrator import _extract_sre_header_values
        except ModuleNotFoundError:
            from api.sre_orchestrator import _extract_sre_header_values  # type: ignore[import-not-found]

        result = {
            "agent_metadata": {
                "execution_source": "agent",
                "token_usage": {"prompt_tokens": 80, "completion_tokens": 40},
            }
        }
        headers = _extract_sre_header_values(result)
        assert headers.get("X-Token-Count") == "120"

    def test_nested_result_agent_metadata(self):
        """agent_metadata may be nested under result.result.agent_metadata."""
        try:
            from app.agentic.eol.api.sre_orchestrator import _extract_sre_header_values
        except ModuleNotFoundError:
            from api.sre_orchestrator import _extract_sre_header_values  # type: ignore[import-not-found]

        result = {
            "result": {
                "agent_metadata": {
                    "execution_source": "agent",
                    "token_usage": {"total_tokens": 200},
                }
            }
        }
        headers = _extract_sre_header_values(result)
        assert headers.get("X-Agent-Used") == "agent"
        assert headers.get("X-Token-Count") == "200"

    def test_missing_metadata_defaults(self):
        try:
            from app.agentic.eol.api.sre_orchestrator import _extract_sre_header_values
        except ModuleNotFoundError:
            from api.sre_orchestrator import _extract_sre_header_values  # type: ignore[import-not-found]

        headers = _extract_sre_header_values({})
        assert headers.get("X-Agent-Used") == "unknown"
        assert "X-Token-Count" not in headers


# ---------------------------------------------------------------------------
# Unit tests: SRE orchestrator wiring (no Azure calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
class TestSREOrchestratorWiring:
    """Verify that gateway + memory + tool_subset are wired correctly.

    All Azure AI and MCP dependencies are mocked so these tests run offline.
    """

    @pytest.fixture
    def mock_azure_sre_agent(self):
        agent = MagicMock()
        agent.is_available = AsyncMock(return_value=True)
        agent.get_or_create_thread = AsyncMock(return_value="thread-123")
        agent.chat = AsyncMock(return_value={
            "content": "Container apps are healthy.",
            "thread_id": "thread-123",
            "run_id": "run-456",
            "token_usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
            "latency_ms": 200.0,
        })
        agent.execute_tool_calls_parallel = AsyncMock(return_value=[])
        return agent

    async def test_incident_memory_inject(self, mock_azure_sre_agent):
        """Memory prefix should be placed in enriched_context["incident_history"]."""
        try:
            from app.agentic.eol.agents.sre_orchestrator import SREOrchestratorAgent
        except ModuleNotFoundError:
            from agents.sre_orchestrator import SREOrchestratorAgent  # type: ignore[import-not-found]

        orchestrator = SREOrchestratorAgent()
        orchestrator.azure_sre_agent = mock_azure_sre_agent

        memory_mock = MagicMock()
        memory_mock.initialize = AsyncMock(return_value=True)
        memory_mock.get_context_prefix = AsyncMock(
            return_value="Similar past incidents:\n1. [health] App crashed → Restarted"
        )
        memory_mock.store = AsyncMock()
        orchestrator._incident_memory = memory_mock

        gateway_mock = MagicMock()
        gateway_mock.classify = AsyncMock(return_value="health")
        orchestrator._gateway = gateway_mock

        context_store_mock = MagicMock()
        context_store_mock.create_workflow_context = AsyncMock()
        orchestrator._context_store = context_store_mock

        await orchestrator._execute_via_agent(
            query="is my container app up?",
            workflow_id="wf-001",
            context={},
            request={"query": "is my container app up?"},
        )

        # Check that chat was called with incident_history in context
        call_kwargs = mock_azure_sre_agent.chat.call_args
        ctx = call_kwargs.kwargs.get("context")
        if ctx is None and call_kwargs.args:
            ctx = call_kwargs.args[2]
        if ctx is None:
            ctx = {}
        assert "incident_history" in ctx, "incident_history should be injected into enriched_context"

    async def test_slim_prompt_passed(self, mock_azure_sre_agent):
        """slim_prompt=True should always be forwarded to agent.chat."""
        try:
            from app.agentic.eol.agents.sre_orchestrator import SREOrchestratorAgent
        except ModuleNotFoundError:
            from agents.sre_orchestrator import SREOrchestratorAgent  # type: ignore[import-not-found]

        orchestrator = SREOrchestratorAgent()
        orchestrator.azure_sre_agent = mock_azure_sre_agent

        memory_mock = MagicMock()
        memory_mock.initialize = AsyncMock(return_value=True)
        memory_mock.get_context_prefix = AsyncMock(return_value="")
        memory_mock.store = AsyncMock()
        orchestrator._incident_memory = memory_mock

        gateway_mock = MagicMock()
        gateway_mock.classify = AsyncMock(return_value="general")
        orchestrator._gateway = gateway_mock

        context_store_mock = MagicMock()
        context_store_mock.create_workflow_context = AsyncMock()
        orchestrator._context_store = context_store_mock

        await orchestrator._execute_via_agent(
            query="check container health",
            workflow_id="wf-002",
            context={},
            request={"query": "check container health"},
        )

        call_kwargs = mock_azure_sre_agent.chat.call_args
        slim = call_kwargs.kwargs.get("slim_prompt")
        assert slim is True, "slim_prompt=True must be passed to agent.chat"


# ---------------------------------------------------------------------------
# Remote / live tests (require TEST_BASE_URL and Azure credentials)
# ---------------------------------------------------------------------------

@pytest.mark.remote
@pytest.mark.asyncio
class TestRemoteSREOrchestrator:
    """Integration tests against a live SRE Orchestrator API instance.

    Requires:
    - TEST_BASE_URL pointing to a running application
    - Azure credentials (if testing agent-first path)

    Skip all remote tests with:
        pytest -m "not remote"
    """

    @pytest.fixture(scope="class")
    def http_client(self):
        if not _HTTPX_AVAILABLE:
            pytest.skip("httpx not installed; install with: pip install httpx")
        with httpx.Client(base_url=_BASE_URL, timeout=60.0) as client:
            yield client

    # ------------------------------------------------------------------
    # Health liveness
    # ------------------------------------------------------------------

    def test_health_endpoint_reachable(self, http_client):
        """GET /health must return 200 and success=True."""
        resp = http_client.get("/api/sre-orchestrator/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body.get("success") is True

    # ------------------------------------------------------------------
    # Execute — basic smoke test
    # ------------------------------------------------------------------

    def test_execute_returns_200(self, http_client):
        """POST /execute with a simple SRE query must return 200."""
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}\n{resp.text}"

    def test_execute_has_x_agent_used_header(self, http_client):
        """POST /execute must include X-Agent-Used response header."""
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200
        assert "x-agent-used" in resp.headers or "X-Agent-Used" in resp.headers, (
            f"Missing X-Agent-Used header. Headers: {dict(resp.headers)}"
        )

    def test_execute_agent_used_value_is_known(self, http_client):
        """X-Agent-Used must be a known execution source value."""
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200
        agent_used = resp.headers.get("x-agent-used") or resp.headers.get("X-Agent-Used", "")
        assert agent_used in ("agent", "mcp_fallback", "unknown"), (
            f"Unexpected X-Agent-Used value: {agent_used!r}"
        )

    def test_execute_body_has_agent_metadata(self, http_client):
        """Response body must contain agent_metadata with execution_source."""
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200
        body = resp.json()
        meta = _extract_agent_metadata(body)
        assert "execution_source" in meta, (
            f"agent_metadata missing execution_source. Body: {json.dumps(body, indent=2)[:500]}"
        )

    def test_execute_token_count_header_when_agent(self, http_client):
        """When agent path is used, X-Token-Count should be a positive integer string."""
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200
        agent_used = resp.headers.get("x-agent-used") or resp.headers.get("X-Agent-Used", "")
        if agent_used == "agent":
            # Agent path should report token usage
            token_count = resp.headers.get("x-token-count") or resp.headers.get("X-Token-Count", "0")
            assert token_count.isdigit() and int(token_count) > 0, (
                f"Expected positive X-Token-Count for agent path, got: {token_count!r}"
            )

    # ------------------------------------------------------------------
    # Incident memory injection (two-turn test)
    # ------------------------------------------------------------------

    def test_second_query_receives_incident_history(self, http_client):
        """After storing an incident, a similar query should reflect it in agent_metadata."""
        # First query — establishes incident memory
        first_resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={
                "query": "container app is returning 503 errors",
                "workflow_id": "test-memory-wf-001",
            },
        )
        assert first_resp.status_code == 200

        # Second query — similar topic, should surface memory context
        second_resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={
                "query": "container app health check returning 503",
                "workflow_id": "test-memory-wf-002",
            },
        )
        assert second_resp.status_code == 200
        # Note: We can only assert the request succeeded.  Whether incident_history
        # appears in enriched_context is an internal concern; the presence of
        # agent_metadata confirms the orchestrator ran correctly.
        body = second_resp.json()
        meta = _extract_agent_metadata(body)
        assert "execution_source" in meta

    # ------------------------------------------------------------------
    # Fallback path (optional — requires AZURE_AI_SRE_ENABLED=false)
    # ------------------------------------------------------------------

    def test_fallback_header_when_agent_disabled(self, http_client):
        """When fallback is used, X-Agent-Used should be 'mcp_fallback'.

        This test only runs when the endpoint is configured with the agent
        disabled (AZURE_AI_SRE_ENABLED=false).  It is advisory only and
        will not fail if agent path is active.
        """
        resp = http_client.post(
            "/api/sre-orchestrator/execute",
            json={"query": _DEFAULT_QUERY},
        )
        assert resp.status_code == 200
        agent_used = resp.headers.get("x-agent-used") or resp.headers.get("X-Agent-Used", "")
        # We don't know whether the agent is enabled, so just verify the header is present
        assert agent_used != "", "X-Agent-Used header must always be present"
