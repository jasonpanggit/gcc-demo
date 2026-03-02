"""Backward compatibility wrapper for mcp_host.

This module provides backward compatibility by re-exporting MCPHost as
CompositeMCPClient. New code should import from mcp_host directly.

DEPRECATED: This module is deprecated. Use 'from utils.mcp_host import MCPHost' instead.
"""
from __future__ import annotations

import warnings
from .mcp_host import MCPHost, ClientEntry, ToolDefinition

# Emit deprecation warning when this module is imported
warnings.warn(
    "utils.mcp_composite_client is deprecated. Use 'from utils.mcp_host import MCPHost' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Backward compatibility alias
CompositeMCPClient = MCPHost

__all__ = ['CompositeMCPClient', 'MCPHost', 'ClientEntry', 'ToolDefinition']
