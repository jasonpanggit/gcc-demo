"""Tool manifests for the Storage MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="storage_account_list",
        source="storage",
        domains=frozenset({"azure_management"}),
        tags=frozenset({"storage", "account", "blob", "iaas"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "list my storage accounts",
            "show all storage accounts",
            "show my storage accounts",
            "what storage accounts do I have",
            "list storage resources",
        ),
        conflicts_with=frozenset({"storage", "fileshares"}),
        conflict_note=(
            "storage_account_list is the PRIMARY tool for listing Azure Storage Accounts. "
            "It returns structured per-account data (SKU, kind, HTTPS flag). "
            "Do NOT use 'storage' (Azure MCP namespace group) or 'fileshares' for a general listing."
        ),
        preferred_over=frozenset({"storage", "fileshares"}),
    ),
]
