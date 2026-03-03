"""Tests for ToolEmbedder — semantic tool index + token audit.

Markers:
    unit: No Azure dependencies — uses mock embeddings.
    asyncio: Async tests.
    azure: Tests that require the live Azure OpenAI embedding API.
"""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from app.agentic.eol.utils.legacy.tool_embedder import (
        ToolEmbedder,
        count_prompt_tokens,
        get_tool_embedder,
    )
    from app.agentic.eol.agents.mcp_orchestrator import MCPOrchestratorAgent
except ModuleNotFoundError:
    from utils.legacy.tool_embedder import (  # type: ignore[import-not-found]
        ToolEmbedder,
        count_prompt_tokens,
        get_tool_embedder,
    )
    from agents.mcp_orchestrator import MCPOrchestratorAgent  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Mock embedding helpers
# ---------------------------------------------------------------------------

_DIM = 1536

def _unit_vec(direction: np.ndarray) -> np.ndarray:
    """Return a unit vector in the given direction."""
    return direction / np.linalg.norm(direction)

def _make_tool(name: str, description: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": description}}


MOCK_TOOLS = [
    _make_tool("check_container_app_health", "Check health status of Azure Container Apps"),
    _make_tool("check_aks_cluster_health",   "Check health of AKS Kubernetes cluster"),
    _make_tool("get_cost_analysis",          "Get Azure cost analysis and billing breakdown"),
    _make_tool("triage_incident",            "Triage and analyse a production incident"),
    _make_tool("get_performance_metrics",    "Get CPU memory performance metrics for Azure resources"),
]

# Deterministic "fake" embeddings: each tool gets a unit vector biased along
# a unique axis so cosine similarity is predictable in tests.
_MOCK_EMBEDDINGS: dict[str, np.ndarray] = {}
rng = np.random.default_rng(seed=42)
for _tool in MOCK_TOOLS:
    _name = _tool["function"]["name"]
    _vec = rng.random(_DIM).astype(np.float32)
    _MOCK_EMBEDDINGS[_name] = _unit_vec(_vec)

# health query → biased toward container_app_health and aks_cluster_health
_HEALTH_QUERY_VEC = _unit_vec(
    0.9 * _MOCK_EMBEDDINGS["check_container_app_health"]
    + 0.1 * _MOCK_EMBEDDINGS["check_aks_cluster_health"]
)


def _make_embedder_with_mock_index(tools=None) -> ToolEmbedder:
    """Create a ToolEmbedder with a pre-built mock index (no API calls)."""
    if tools is None:
        tools = MOCK_TOOLS
    embedder = ToolEmbedder()
    embedder._tool_definitions = list(tools)
    embedder._tool_texts = [embedder._tool_text(t) for t in tools]
    matrix = np.stack([_MOCK_EMBEDDINGS[t["function"]["name"]] for t in tools])
    embedder._embeddings = matrix
    embedder._index_built = True
    return embedder


# ---------------------------------------------------------------------------
# build_index() tests
# ---------------------------------------------------------------------------

class TestToolEmbedderBuildIndex:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_build_index_sets_ready(self):
        """build_index with mocked API should set is_ready=True."""
        embedder = ToolEmbedder()

        mock_matrix = np.random.default_rng(0).random((len(MOCK_TOOLS), _DIM)).astype(np.float32)

        async def mock_embed_batch(texts):
            assert len(texts) == len(MOCK_TOOLS)
            return mock_matrix / np.linalg.norm(mock_matrix, axis=1, keepdims=True)

        with patch.object(embedder, "_embed_batch", side_effect=mock_embed_batch):
            result = await embedder.build_index(MOCK_TOOLS)

        assert result is True
        assert embedder.is_ready
        assert embedder.tool_count == len(MOCK_TOOLS)
        assert embedder._embeddings.shape == (len(MOCK_TOOLS), _DIM)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_build_index_empty_tools_returns_false(self):
        embedder = ToolEmbedder()
        result = await embedder.build_index([])
        assert result is False
        assert not embedder.is_ready

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_build_index_api_failure_disables_embedder(self):
        """When embedding API raises, embedder should disable itself cleanly."""
        embedder = ToolEmbedder()

        async def failing_embed(_):
            raise RuntimeError("API unavailable")

        with patch.object(embedder, "_embed_batch", side_effect=failing_embed):
            result = await embedder.build_index(MOCK_TOOLS)

        assert result is False
        assert not embedder.is_ready
        assert not embedder._embedding_available

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_build_index_second_call_after_failure_is_noop(self):
        """After API failure, subsequent build_index calls return False immediately."""
        embedder = ToolEmbedder()
        embedder._embedding_available = False
        result = await embedder.build_index(MOCK_TOOLS)
        assert result is False


# ---------------------------------------------------------------------------
# retrieve() tests
# ---------------------------------------------------------------------------

class TestToolEmbedderRetrieve:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_returns_correct_count(self):
        embedder = _make_embedder_with_mock_index()

        async def mock_embed_single(_):
            return _HEALTH_QUERY_VEC

        with patch.object(embedder, "_embed_single", side_effect=mock_embed_single):
            results = await embedder.retrieve("check container app health", top_k=2)

        assert len(results) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_top_result_is_most_similar(self):
        """The tool most similar to the query vector should rank first."""
        embedder = _make_embedder_with_mock_index()

        async def mock_embed_single(_):
            return _HEALTH_QUERY_VEC

        with patch.object(embedder, "_embed_single", side_effect=mock_embed_single):
            results = await embedder.retrieve("container app health check", top_k=3)

        top_name = results[0]["function"]["name"]
        assert top_name == "check_container_app_health", (
            f"Expected check_container_app_health first, got {top_name}"
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_not_ready_returns_empty(self):
        embedder = ToolEmbedder()
        # Not initialised
        results = await embedder.retrieve("any query")
        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_empty_query_returns_first_k(self):
        embedder = _make_embedder_with_mock_index()
        results = await embedder.retrieve("", top_k=3)
        assert len(results) == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_capped_at_top_k(self):
        embedder = _make_embedder_with_mock_index()

        async def mock_embed_single(_):
            return _HEALTH_QUERY_VEC

        with patch.object(embedder, "_embed_single", side_effect=mock_embed_single):
            results = await embedder.retrieve("health check", top_k=2)

        assert len(results) <= 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieve_embed_failure_returns_empty(self):
        embedder = _make_embedder_with_mock_index()

        async def failing(_):
            raise RuntimeError("embedding API down")

        with patch.object(embedder, "_embed_single", side_effect=failing):
            results = await embedder.retrieve("health check", top_k=5)

        assert results == []


# ---------------------------------------------------------------------------
# rebuild_if_stale() tests
# ---------------------------------------------------------------------------

class TestToolEmbedderRebuildIfStale:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_rebuild_when_same_tools(self):
        embedder = _make_embedder_with_mock_index()
        original_embeddings = embedder._embeddings.copy()

        # Same tool list → should NOT rebuild
        result = await embedder.rebuild_if_stale(MOCK_TOOLS)
        assert result is True
        assert np.array_equal(embedder._embeddings, original_embeddings)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rebuilds_when_tools_change(self):
        embedder = _make_embedder_with_mock_index()
        new_tool = _make_tool("new_tool_xyz", "A completely new tool")
        new_tools = MOCK_TOOLS + [new_tool]

        call_count = [0]
        original_matrix = np.random.default_rng(1).random((len(new_tools), _DIM)).astype(np.float32)
        original_matrix = original_matrix / np.linalg.norm(original_matrix, axis=1, keepdims=True)

        async def mock_embed_batch(texts):
            call_count[0] += 1
            return original_matrix

        with patch.object(embedder, "_embed_batch", side_effect=mock_embed_batch):
            result = await embedder.rebuild_if_stale(new_tools)

        assert call_count[0] == 1
        assert embedder.tool_count == len(new_tools)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:

    @pytest.mark.unit
    def test_identical_vectors_score_1(self):
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = v.reshape(1, 3)
        scores = ToolEmbedder._cosine_similarity_batch(v, matrix)
        assert abs(scores[0] - 1.0) < 1e-6

    @pytest.mark.unit
    def test_orthogonal_vectors_score_0(self):
        v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        scores = ToolEmbedder._cosine_similarity_batch(v1, v2.reshape(1, 3))
        assert abs(scores[0]) < 1e-6


# ---------------------------------------------------------------------------
# Token audit — slim system prompt ≤ 1,500 tokens
# ---------------------------------------------------------------------------

class TestTokenAudit:

    @pytest.mark.unit
    def test_slim_system_prompt_under_1500_tokens(self):
        """_SYSTEM_PROMPT after revamp must be ≤ 1,500 tokens."""
        prompt = MCPOrchestratorAgent._SYSTEM_PROMPT
        token_count = count_prompt_tokens(prompt)
        assert token_count <= 1_500, (
            f"_SYSTEM_PROMPT is {token_count} tokens — must be ≤ 1,500 after revamp. "
            f"Current prompt preview:\n{prompt[:300]}..."
        )

    @pytest.mark.unit
    def test_dynamic_prompt_without_tools_under_1500_tokens(self):
        """_build_dynamic_system_prompt with empty tools should stay ≤ 1,500 tokens."""
        agent = MCPOrchestratorAgent.__new__(MCPOrchestratorAgent)
        prompt = agent._build_dynamic_system_prompt([], {})
        token_count = count_prompt_tokens(prompt)
        assert token_count <= 1_500, (
            f"Dynamic prompt (no tools) is {token_count} tokens — must be ≤ 1,500"
        )

    @pytest.mark.unit
    def test_count_prompt_tokens_basic(self):
        """count_prompt_tokens should return a positive integer for non-empty text."""
        n = count_prompt_tokens("Hello, world!")
        assert n > 0

    @pytest.mark.unit
    def test_count_prompt_tokens_empty(self):
        assert count_prompt_tokens("") == 0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetToolEmbedderSingleton:

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        e1 = get_tool_embedder()
        e2 = get_tool_embedder()
        assert e1 is e2

    @pytest.mark.unit
    def test_singleton_is_tool_embedder(self):
        assert isinstance(get_tool_embedder(), ToolEmbedder)
