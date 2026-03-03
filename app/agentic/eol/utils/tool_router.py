"""ToolRouter — legacy shim.

.. deprecated::
    ToolRouter has been moved to :mod:`utils.legacy.tool_router`.
    This module re-exports it for backward compatibility.
    New code should use :class:`utils.router.Router` instead.
"""
from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "utils.tool_router is deprecated; import from utils.legacy.tool_router instead. "
    "New code should use utils.router.Router.",
    DeprecationWarning,
    stacklevel=2,
)

try:
    from app.agentic.eol.utils.legacy.tool_router import (  # noqa: F401
        ToolRouter,
    )
except ModuleNotFoundError:
    from utils.legacy.tool_router import (  # type: ignore[import-not-found]  # noqa: F401
        ToolRouter,
    )

__all__ = ["ToolRouter"]
