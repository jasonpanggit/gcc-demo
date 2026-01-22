"""Unit tests for dependency injection and cleanup in the EOL orchestrator."""

from __future__ import annotations

from typing import List, Tuple

import pytest

from agents.eol_orchestrator import EOLOrchestratorAgent


class StubPlaywrightAgent:
    """Simple async agent stub used to validate orchestrator injection."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str | None]] = []
        self.close_calls = 0

    async def get_eol_data(self, software_name: str, version: str | None = None):
        self.calls.append((software_name, version))
        return {
            "success": True,
            "data": {
                "confidence": 0.8,
                "status": "Active Support",
                "eol_date": "2030-01-01",
            },
            "source": "stub_playwright",
        }

    async def aclose(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_injected_agent_handles_internet_only_search() -> None:
    stub_agent = StubPlaywrightAgent()
    orchestrator = EOLOrchestratorAgent(
        agents={"playwright": stub_agent},
        close_provided_agents=True,
    )

    result = await orchestrator.get_autonomous_eol_data(
        "Contoso App",
        version="1.0",
        search_internet_only=True,
    )

    assert stub_agent.calls == [("Contoso App", "1.0")]
    assert result["success"] is True
    assert result.get("agent_used") == "playwright"

    await orchestrator.aclose()
    assert stub_agent.close_calls == 1


@pytest.mark.asyncio
async def test_aclose_is_idempotent() -> None:
    stub_agent = StubPlaywrightAgent()
    orchestrator = EOLOrchestratorAgent(
        agents={"playwright": stub_agent},
        close_provided_agents=True,
    )

    await orchestrator.aclose()
    await orchestrator.aclose()

    assert stub_agent.close_calls == 1


@pytest.mark.asyncio
async def test_aclose_does_not_close_unowned_agents() -> None:
    stub_agent = StubPlaywrightAgent()
    orchestrator = EOLOrchestratorAgent(agents={"playwright": stub_agent})

    await orchestrator.aclose()

    assert stub_agent.close_calls == 0


@pytest.mark.asyncio
async def test_missing_software_name_returns_error() -> None:
    orchestrator = EOLOrchestratorAgent(agents={}, close_provided_agents=True)

    result = await orchestrator.get_autonomous_eol_data("", version="1.0")

    assert result["success"] is False
    assert "required" in result.get("error", "").lower()
    assert result.get("agent_used") == "orchestrator"
    assert result.get("elapsed_seconds", 0) >= 0

    await orchestrator.aclose()


def test_track_response_handles_non_dict_data() -> None:
    orchestrator = EOLOrchestratorAgent(agents={}, close_provided_agents=True)

    orchestrator._track_eol_agent_response(  # pylint: disable=protected-access
        agent_name="stub_agent",
        software_name="TestSoft",
        software_version="1.0",
        eol_result={"success": True, "data": "not_a_dict"},
        response_time=0.05,
        query_type="autonomous_search",
    )

    tracked = orchestrator.get_eol_agent_responses()[-1]
    assert tracked["eol_data"] == {}
    assert tracked["success"] is True
    assert tracked["agent_name"] == "stub_agent"
    assert tracked["software_name"] == "TestSoft"


@pytest.mark.asyncio
async def test_cosmos_cache_hit_short_circuits_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubEolTable:
        def __init__(self) -> None:
            self.get_called = 0
            self.upsert_called = 0

        async def get(self, software_name: str, version: str | None):
            self.get_called += 1
            return {
                "success": True,
                "data": {
                    "software_name": software_name,
                    "version": version,
                    "eol_date": "2030-01-01",
                    "status": "Active Support",
                    "agent_used": "cached",
                },
                "cache_source": "cosmos_eol_table",
            }

        async def upsert(self, software_name: str, version: str | None, result):
            self.upsert_called += 1
            return True

        def get_stats(self):
            return {"hits": self.get_called, "misses": 0}

    stub_table = StubEolTable()
    stub_agent = StubPlaywrightAgent()
    orchestrator = EOLOrchestratorAgent(agents={"playwright": stub_agent}, close_provided_agents=True)

    monkeypatch.setattr("agents.eol_orchestrator.eol_inventory", stub_table)

    result = await orchestrator.get_autonomous_eol_data("Contoso App", version="1.0")

    assert result["cache_hit"] is True
    assert result.get("cache_source") == "cosmos_eol_table"
    assert result.get("agent_used") == "cached"
    assert stub_table.get_called == 1
    assert stub_table.upsert_called == 0
    assert stub_agent.calls == []

    await orchestrator.aclose()
