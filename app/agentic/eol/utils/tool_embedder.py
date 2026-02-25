"""Semantic tool index for the MCP orchestrator.

Builds an in-memory embedding index over tool definitions at startup (once).
Each query retrieves the top-k most semantically relevant tools instead of
sending the full catalog (~140 tools) to the LLM on every call.

Token impact:
  Before: ~140 tools × ~100 tok/schema ≈ 14,000 tokens per call
  After:  top-10 tools × ~100 tok/schema ≈ 1,000 tokens per call

Startup cost: ~140 tools × ~30 tok/description ≈ 4,200 tokens (one-time).

Fallback: when AZURE_OPENAI_EMBEDDING_DEPLOYMENT is unset or the embedding
API is unavailable, ToolRouter keyword matching is used transparently.

Usage:
    embedder = ToolEmbedder()
    await embedder.build_index(all_tool_definitions)
    relevant_tools = await embedder.retrieve("check container app health", top_k=10)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

_DEFAULT_TOP_K = 10
_DEFAULT_EMBEDDING_DIM = 1536  # text-embedding-3-small
_MIN_SCORE = 0.0  # cosine similarity threshold (allow any positive match)


class ToolEmbedder:
    """In-memory semantic index for tool definitions.

    Index lifecycle:
      1. build_index(tool_definitions) — called once when tools are loaded
      2. retrieve(query, top_k) — called per ReAct iteration
      3. Rebuild automatically when tool_definitions changes (via rebuild_if_stale)

    Thread safety: the index is rebuilt atomically (numpy array replace).
    """

    def __init__(self) -> None:
        self._tool_definitions: List[Dict[str, Any]] = []
        self._embeddings: Optional[np.ndarray] = None      # shape: (n_tools, dim)
        self._tool_texts: List[str] = []                   # text used for each embedding
        self._index_built: bool = False
        self._embedding_available: bool = True             # flipped False on first failure
        self._client_kwargs: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build_index(self, tool_definitions: List[Dict[str, Any]]) -> bool:
        """Build the embedding index from a list of tool definitions.

        Returns True when the index was built successfully, False when the
        embedding API is unavailable (caller should fall back to ToolRouter).
        """
        if not tool_definitions:
            logger.warning("ToolEmbedder: no tools provided — index not built")
            return False

        if not self._embedding_available:
            return False

        texts = [self._tool_text(t) for t in tool_definitions]

        try:
            embeddings = await self._embed_batch(texts)
        except Exception as exc:
            exc_str = str(exc)
            self._embedding_available = False
            if "DeploymentNotFound" in exc_str or "404" in exc_str:
                logger.warning(
                    "ToolEmbedder: embedding deployment '%s' not found on Azure OpenAI resource. "
                    "Deploy an embedding model (e.g. text-embedding-3-small) and set "
                    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT env var to enable semantic tool ranking. "
                    "Falling back to keyword ranking.",
                    self._get_embedding_deployment(),
                )
            else:
                logger.warning("ToolEmbedder: embedding failed, disabling semantic index: %s", exc)
            return False

        self._tool_definitions = list(tool_definitions)
        self._tool_texts = texts
        self._embeddings = embeddings
        self._index_built = True
        logger.info(
            "✅ ToolEmbedder: index built — %d tools, dim=%d",
            len(tool_definitions),
            embeddings.shape[1] if embeddings.ndim == 2 else 0,
        )
        return True

    async def retrieve(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        """Return the top-k most semantically relevant tool definitions.

        Falls back to returning [] when the index is not built or the
        embedding API is unavailable (caller should use ToolRouter fallback).
        """
        if not self._index_built or self._embeddings is None:
            return []

        if not query:
            return self._tool_definitions[:top_k]

        try:
            q_vec = await self._embed_single(query)
        except Exception as exc:
            logger.warning("ToolEmbedder.retrieve: embedding query failed: %s", exc)
            return []

        scores = self._cosine_similarity_batch(q_vec, self._embeddings)
        top_indices = np.argsort(scores)[::-1][:top_k]

        selected = [self._tool_definitions[i] for i in top_indices if scores[i] > _MIN_SCORE]
        logger.debug(
            "ToolEmbedder.retrieve: query=%r → %d/%d tools (top score=%.3f)",
            query[:60],
            len(selected),
            len(self._tool_definitions),
            float(scores[top_indices[0]]) if len(top_indices) > 0 else 0.0,
        )
        return selected

    async def retrieve_from_pool(
        self,
        query: str,
        pool: List[Dict[str, Any]],
        top_k: int = _DEFAULT_TOP_K,
    ) -> List[Dict[str, Any]]:
        """Return the top-k semantically relevant tools from *pool* (a pre-filtered subset).

        Unlike ``retrieve()``, which ranks against the full index, this method
        builds a temporary in-memory index over *pool* and ranks within that
        subset.  This is the Stage 2 operation for ToolRetriever: Stage 1
        narrows the catalog to a domain pool; Stage 2 picks the best ≤top_k.

        Falls back to returning the first *top_k* entries from *pool* when the
        embedding API is unavailable or *pool* is small enough that ranking adds
        no value (len(pool) <= top_k).

        Args:
            query:  The user's natural-language message.
            pool:   Pre-filtered tool definitions (domain pool from ToolRetriever Stage 1).
            top_k:  Maximum tools to return.

        Returns:
            Ranked subset of *pool* (at most *top_k* entries).
        """
        if not pool:
            return []

        # No benefit ranking when pool is already within budget
        if len(pool) <= top_k:
            return pool

        if not self._embedding_available:
            return pool[:top_k]

        try:
            # Build a temporary index over the pool
            texts = [self._tool_text(t) for t in pool]
            pool_embeddings = await self._embed_batch(texts)
            q_vec = await self._embed_single(query)
            scores = self._cosine_similarity_batch(q_vec, pool_embeddings)
            top_indices = np.argsort(scores)[::-1][:top_k]
            selected = [pool[i] for i in top_indices if scores[i] > _MIN_SCORE]
            logger.debug(
                "ToolEmbedder.retrieve_from_pool: query=%r → %d/%d tools from pool",
                query[:60],
                len(selected),
                len(pool),
            )
            return selected if selected else pool[:top_k]
        except Exception as exc:
            logger.warning("ToolEmbedder.retrieve_from_pool: failed (%s), returning pool[:top_k]", exc)
            return pool[:top_k]

    async def rebuild_if_stale(self, tool_definitions: List[Dict[str, Any]]) -> bool:
        """Rebuild the index only when tool_definitions has changed.

        Compares by count + first/last tool name to detect changes cheaply.
        """
        if not tool_definitions:
            return False

        if (
            len(tool_definitions) == len(self._tool_definitions)
            and self._index_built
            and self._tool_name(tool_definitions[0]) == self._tool_name(self._tool_definitions[0])
            and self._tool_name(tool_definitions[-1]) == self._tool_name(self._tool_definitions[-1])
        ):
            return True  # Index is current

        logger.info(
            "ToolEmbedder: tool catalog changed (%d → %d tools), rebuilding index",
            len(self._tool_definitions),
            len(tool_definitions),
        )
        return await self.build_index(tool_definitions)

    @property
    def is_ready(self) -> bool:
        """True when the index is built and usable."""
        return self._index_built and self._embeddings is not None

    @property
    def tool_count(self) -> int:
        return len(self._tool_definitions)

    # ------------------------------------------------------------------
    # Embedding calls
    # ------------------------------------------------------------------

    def _get_embedding_deployment(self) -> str:
        return os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )

    async def _embed_batch(self, texts: List[str]) -> np.ndarray:
        """Embed a list of texts, returning shape (n, dim) float32 array.

        Auth priority:
          1. AZURE_OPENAI_API_KEY env var (key-based)
          2. DefaultAzureCredential (managed identity / workload identity)
        """
        from openai import AsyncAzureOpenAI  # type: ignore[import-not-found]

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT not set")

        async_credential = None
        if api_key:
            kwargs = {"api_key": api_key, "azure_endpoint": endpoint, "api_version": api_version}
        else:
            # Managed identity / workload identity fallback (container env)
            try:
                from azure.identity.aio import DefaultAzureCredential  # type: ignore[import-not-found]
                async_credential = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                token = await async_credential.get_token("https://cognitiveservices.azure.com/.default")
                kwargs = {"api_key": token.token, "azure_endpoint": endpoint, "api_version": api_version}
            except Exception as exc:
                raise RuntimeError(f"No auth available for ToolEmbedder (no API key, managed identity failed: {exc})")

        deployment = self._get_embedding_deployment()
        client = AsyncAzureOpenAI(**kwargs)
        try:
            # Azure OpenAI supports up to 2048 inputs per call; batch safely
            all_vectors: List[List[float]] = []
            batch_size = 100
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = await client.embeddings.create(model=deployment, input=batch)
                all_vectors.extend(item.embedding for item in resp.data)
        finally:
            await client.close()
            if async_credential is not None:
                try:
                    await async_credential.close()
                except Exception:
                    pass

        arr = np.array(all_vectors, dtype=np.float32)
        # L2 normalise for cosine similarity via dot product
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return arr / norms

    async def _embed_single(self, text: str) -> np.ndarray:
        """Embed a single query string, returning shape (dim,) float32 array."""
        batch = await self._embed_batch([text])
        return batch[0]

    # ------------------------------------------------------------------
    # Similarity
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity_batch(
        query_vec: np.ndarray,
        index: np.ndarray,
    ) -> np.ndarray:
        """Dot product of normalised query_vec against normalised index rows."""
        return index @ query_vec  # shape: (n_tools,)

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_name(tool: Dict[str, Any]) -> str:
        return str(tool.get("function", {}).get("name", ""))

    @staticmethod
    def _tool_text(tool: Dict[str, Any]) -> str:
        """Concatenate name + description for embedding."""
        fn = tool.get("function", {}) if isinstance(tool.get("function"), dict) else {}
        name = str(fn.get("name", ""))
        desc = str(fn.get("description", ""))
        return f"{name} {desc}".strip()


# ---------------------------------------------------------------------------
# Token audit helper (used by tests and monitoring)
# ---------------------------------------------------------------------------

def count_prompt_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in a string using tiktoken.

    Returns 0 when tiktoken is unavailable (non-fatal).
    """
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_embedder_instance: Optional[ToolEmbedder] = None


def get_tool_embedder() -> ToolEmbedder:
    """Return the module-level ToolEmbedder singleton."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = ToolEmbedder()
    return _embedder_instance
