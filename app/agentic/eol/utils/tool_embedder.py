"""ToolEmbedder — legacy shim.

.. deprecated::
    ToolEmbedder has been moved to :mod:`utils.legacy.tool_embedder`.
    This module re-exports it for backward compatibility.
    New code should use :class:`utils.tool_retriever.ToolRetriever` instead.
"""
from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "utils.tool_embedder is deprecated; import from utils.legacy.tool_embedder instead. "
    "New code should use utils.tool_retriever.ToolRetriever.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from app.agentic.eol.utils.legacy.tool_embedder import (  # noqa: F401
        ToolEmbedder,
        count_prompt_tokens,
        get_tool_embedder,
    )
except ModuleNotFoundError:
    from utils.legacy.tool_embedder import (  # type: ignore[import-not-found]  # noqa: F401
        ToolEmbedder,
        count_prompt_tokens,
        get_tool_embedder,
    )

__all__ = ["ToolEmbedder", "count_prompt_tokens", "get_tool_embedder"]
