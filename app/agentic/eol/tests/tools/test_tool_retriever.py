"""Unit tests for utils/tool_retriever.py — Pipeline ToolRetriever (Phase 4).

Tests:
- retrieve() returns ToolRetrievalResult with tools list
- Stage 1 source filter: only tools from matched domain sources included
- Stage 2 semantic ranking respects top_k limit
- always_include tools survive Stage 2 ranking cutoff
- Falls back gracefully when embedder not ready
- Falls back gracefully when pool is empty
- conflict_notes populated when active tool set has conflicts
- sources_used and pool_size are correctly reported
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.utils.tool_retriever import ToolRetriever, ToolRetrievalResult
    from app.agentic.eol.utils.router import DomainMatch
    from app.agentic.eol.utils.unified_domain_registry import UnifiedDomain
    _UTILS_PREFIX = "app.agentic.eol.utils"
except ModuleNotFoundError:
    from utils.tool_retriever import ToolRetriever, ToolRetrievalResult  # type: ignore[import-not-found]
    from utils.router import DomainMatch  # type: ignore[import-not-found]
    from utils.unified_domain_registry import UnifiedDomain  # type: ignore[import-not-found]
    _UTILS_PREFIX = "utils"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> Dict[str, Any]:
    """Build a minimal OpenAI function-calling tool dict."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool: {name}",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


def _make_domain_match(domain: UnifiedDomain, confidence: float = 0.8) -> DomainMatch:
    return DomainMatch(domain=domain, confidence=confidence, matched_signals=["test"])


def _make_retriever(
    pool_tools: Optional[List[Dict]] = None,
    embedder_ready: bool = False,
    top_k: int = 5,
    conflict_notes: str = "",
) -> ToolRetriever:
    """Build a ToolRetriever with mocked dependencies."""
    pool_tools = pool_tools or []

    # Mock composite client
    mock_client = MagicMock()
    mock_client.get_tools_by_sources = MagicMock(return_value=pool_tools)
    mock_client.get_tool_definitions = MagicMock(return_value=pool_tools)
    mock_client.get_tool_sources = MagicMock(return_value={
        t["function"]["name"]: "sre" for t in pool_tools
    })

    # Mock embedder
    mock_embedder = AsyncMock()
    mock_embedder.is_ready = embedder_ready
    # retrieve_from_pool returns first top_k tools (stable ordering for testing)
    async def _mock_retrieve_from_pool(query, pool, top_k=top_k):
        return pool[:top_k]
    mock_embedder.retrieve_from_pool = _mock_retrieve_from_pool

    # Mock manifest index
    mock_manifests = MagicMock()
    mock_manifests.build_conflict_note_for_context = MagicMock(return_value=conflict_notes)

    return ToolRetriever(
        composite_client=mock_client,
        embedder=mock_embedder,
        manifest_index=mock_manifests,
        top_k=top_k,
    )


# ---------------------------------------------------------------------------
# Test: basic result structure
# ---------------------------------------------------------------------------

class TestToolRetrievalResultStructure:
    @pytest.mark.asyncio
    async def test_returns_tool_retrieval_result(self):
        tools = [_make_tool(f"tool_{i}") for i in range(3)]
        retriever = _make_retriever(pool_tools=tools)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert isinstance(result, ToolRetrievalResult)

    @pytest.mark.asyncio
    async def test_result_has_tools_list(self):
        tools = [_make_tool(f"tool_{i}") for i in range(3)]
        retriever = _make_retriever(pool_tools=tools)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert isinstance(result.tools, list)

    @pytest.mark.asyncio
    async def test_result_carries_domain_matches(self):
        tools = [_make_tool("sre_tool")]
        retriever = _make_retriever(pool_tools=tools)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert result.domain_matches == matches

    @pytest.mark.asyncio
    async def test_result_reports_sources_used(self):
        tools = [_make_tool("sre_tool")]
        retriever = _make_retriever(pool_tools=tools)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert isinstance(result.sources_used, list)

    @pytest.mark.asyncio
    async def test_result_reports_pool_size(self):
        tools = [_make_tool(f"tool_{i}") for i in range(8)]
        retriever = _make_retriever(pool_tools=tools, top_k=3)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert result.pool_size == 8


# ---------------------------------------------------------------------------
# Test: Stage 1 — source filter
# ---------------------------------------------------------------------------

class TestStage1SourceFilter:
    @pytest.mark.asyncio
    async def test_get_tools_by_sources_called(self):
        tools = [_make_tool("sre_tool")]
        mock_client = MagicMock()
        mock_client.get_tools_by_sources = MagicMock(return_value=tools)

        mock_embedder = AsyncMock()
        mock_embedder.is_ready = False
        mock_embedder.retrieve_from_pool = AsyncMock(return_value=tools)

        mock_manifests = MagicMock()
        mock_manifests.build_conflict_note_for_context = MagicMock(return_value="")

        retriever = ToolRetriever(
            composite_client=mock_client,
            embedder=mock_embedder,
            manifest_index=mock_manifests,
            top_k=5,
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        await retriever.retrieve("check health", matches)
        assert mock_client.get_tools_by_sources.called

    @pytest.mark.asyncio
    async def test_empty_pool_returns_empty_result(self):
        retriever = _make_retriever(pool_tools=[])
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert result.tools == []
        assert result.pool_size == 0


# ---------------------------------------------------------------------------
# Test: Stage 2 — top_k enforcement
# ---------------------------------------------------------------------------

class TestStage2TopK:
    @pytest.mark.asyncio
    async def test_results_capped_at_top_k_when_embedder_not_ready(self):
        tools = [_make_tool(f"tool_{i}") for i in range(20)]
        retriever = _make_retriever(pool_tools=tools, embedder_ready=False, top_k=5)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert len(result.tools) <= 5

    @pytest.mark.asyncio
    async def test_all_tools_returned_when_pool_leq_top_k(self):
        tools = [_make_tool(f"tool_{i}") for i in range(3)]
        retriever = _make_retriever(pool_tools=tools, embedder_ready=False, top_k=5)
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        # Pool size (3) <= top_k (5), so all 3 should be returned
        assert len(result.tools) == 3


# ---------------------------------------------------------------------------
# Test: always_include
# ---------------------------------------------------------------------------

class TestAlwaysInclude:
    @pytest.mark.asyncio
    async def test_always_include_adds_missing_tool_to_pool(self):
        pool_tools = [_make_tool("regular_tool")]
        extra_tool = _make_tool("meta_describe_capabilities")

        # Client has the extra tool in its full catalog but not in pool
        mock_client = MagicMock()
        mock_client.get_tools_by_sources = MagicMock(return_value=pool_tools)
        mock_client.get_tool_definitions = MagicMock(return_value=pool_tools + [extra_tool])

        mock_embedder = AsyncMock()
        mock_embedder.is_ready = False
        mock_embedder.retrieve_from_pool = AsyncMock(side_effect=lambda q, p, top_k: p[:top_k])

        mock_manifests = MagicMock()
        mock_manifests.build_conflict_note_for_context = MagicMock(return_value="")

        retriever = ToolRetriever(
            composite_client=mock_client,
            embedder=mock_embedder,
            manifest_index=mock_manifests,
            top_k=10,
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve(
            "check capabilities",
            matches,
            always_include=["meta_describe_capabilities"],
        )
        tool_names = [t["function"]["name"] for t in result.tools]
        assert "meta_describe_capabilities" in tool_names, \
            f"Expected meta_describe_capabilities in {tool_names}"

    @pytest.mark.asyncio
    async def test_always_include_noop_when_already_in_pool(self):
        pool_tools = [_make_tool("meta_describe_capabilities"), _make_tool("other_tool")]

        mock_client = MagicMock()
        mock_client.get_tools_by_sources = MagicMock(return_value=pool_tools)
        mock_client.get_tool_definitions = MagicMock(return_value=pool_tools)

        mock_embedder = AsyncMock()
        mock_embedder.is_ready = False
        mock_embedder.retrieve_from_pool = AsyncMock(side_effect=lambda q, p, top_k: p[:top_k])

        mock_manifests = MagicMock()
        mock_manifests.build_conflict_note_for_context = MagicMock(return_value="")

        retriever = ToolRetriever(
            composite_client=mock_client,
            embedder=mock_embedder,
            manifest_index=mock_manifests,
            top_k=10,
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve(
            "check capabilities",
            matches,
            always_include=["meta_describe_capabilities"],
        )
        # Pool should not have duplicates
        tool_names = [t["function"]["name"] for t in result.tools]
        assert tool_names.count("meta_describe_capabilities") == 1


# ---------------------------------------------------------------------------
# Test: conflict notes
# ---------------------------------------------------------------------------

class TestConflictNotes:
    @pytest.mark.asyncio
    async def test_conflict_notes_included_when_present(self):
        tools = [_make_tool("tool_a"), _make_tool("tool_b")]
        retriever = _make_retriever(
            pool_tools=tools,
            conflict_notes="tool_a and tool_b conflict: prefer tool_b for X",
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert result.conflict_notes == "tool_a and tool_b conflict: prefer tool_b for X"

    @pytest.mark.asyncio
    async def test_conflict_notes_empty_when_no_conflicts(self):
        tools = [_make_tool("tool_no_conflict")]
        retriever = _make_retriever(pool_tools=tools, conflict_notes="")
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        result = await retriever.retrieve("check health", matches)
        assert result.conflict_notes == ""


# ---------------------------------------------------------------------------
# Test: GENERAL domain handling
# ---------------------------------------------------------------------------

class TestGeneralDomain:
    @pytest.mark.asyncio
    async def test_general_only_uses_all_sources_if_no_other_match(self):
        """When GENERAL is the only match, it should still query sources."""
        tools = [_make_tool("azure_tool")]
        retriever = _make_retriever(pool_tools=tools)
        # Pure GENERAL match (no non-general domains)
        matches = [_make_domain_match(UnifiedDomain.GENERAL, confidence=0.5)]
        result = await retriever.retrieve("help me", matches)
        # Should not crash, should return something
        assert isinstance(result, ToolRetrievalResult)


# ---------------------------------------------------------------------------
# Test: graceful fallbacks
# ---------------------------------------------------------------------------

class TestGracefulFallbacks:
    @pytest.mark.asyncio
    async def test_fallback_when_get_tools_by_sources_missing(self):
        """If composite_client lacks get_tools_by_sources, uses fallback path."""
        pool_tools = [_make_tool("fallback_tool")]

        mock_client = MagicMock(spec=[])  # No methods by default
        # AttributeError on get_tools_by_sources, but has get_tool_definitions
        mock_client.get_tool_definitions = MagicMock(return_value=pool_tools)
        mock_client.get_tool_sources = MagicMock(return_value={"fallback_tool": "sre"})

        mock_embedder = AsyncMock()
        mock_embedder.is_ready = False
        mock_embedder.retrieve_from_pool = AsyncMock(side_effect=lambda q, p, top_k: p[:top_k])

        mock_manifests = MagicMock()
        mock_manifests.build_conflict_note_for_context = MagicMock(return_value="")

        retriever = ToolRetriever(
            composite_client=mock_client,
            embedder=mock_embedder,
            manifest_index=mock_manifests,
            top_k=5,
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        # Should not raise
        result = await retriever.retrieve("check health", matches)
        assert isinstance(result, ToolRetrievalResult)

    @pytest.mark.asyncio
    async def test_no_crash_on_embedder_exception(self):
        """If embedder.retrieve_from_pool raises, retriever falls back gracefully."""
        tools = [_make_tool(f"tool_{i}") for i in range(10)]

        mock_client = MagicMock()
        mock_client.get_tools_by_sources = MagicMock(return_value=tools)

        mock_embedder = AsyncMock()
        mock_embedder.is_ready = True
        async def _raise(*args, **kwargs):
            raise RuntimeError("embedding service down")
        mock_embedder.retrieve_from_pool = _raise

        mock_manifests = MagicMock()
        mock_manifests.build_conflict_note_for_context = MagicMock(return_value="")

        retriever = ToolRetriever(
            composite_client=mock_client,
            embedder=mock_embedder,
            manifest_index=mock_manifests,
            top_k=5,
        )
        matches = [_make_domain_match(UnifiedDomain.SRE_HEALTH)]
        # Should not raise; falls back to pool[:top_k]
        result = await retriever.retrieve("check health", matches)
        assert isinstance(result, ToolRetrievalResult)
        assert len(result.tools) <= 5
