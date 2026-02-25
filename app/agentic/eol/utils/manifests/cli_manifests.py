"""Tool manifests for Azure CLI executor MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="azure_cli_execute_command",
        source="azure_cli",
        domains=frozenset({"deployment", "azure_management", "sre_remediation"}),
        tags=frozenset({"cli", "containerapp", "avd", "escape_hatch"}),
        affordance=ToolAffordance.WRITE,  # Classification enforced at runtime by _classify_command
        example_queries=(
            "run az containerapp command",
            "execute azure CLI command",
            "deploy saved search via CLI",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "azure_cli_execute_command executes raw 'az' commands. "
            "Use for services without a dedicated MCP tool (Container Apps, AVD, scheduled queries). "
            "Mutating commands require confirmed=true. 'az group delete' and 'az ad' are always blocked."
        ),
        preferred_over=frozenset(),
        requires_confirmation=True,
    ),
]
