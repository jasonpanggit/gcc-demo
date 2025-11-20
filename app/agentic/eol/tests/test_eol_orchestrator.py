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
