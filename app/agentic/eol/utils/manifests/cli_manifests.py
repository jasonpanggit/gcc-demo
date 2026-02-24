"""Tool manifests for Azure CLI executor MCP server tools."""
from __future__ import annotations

try:
    from utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]
except ImportError:
    from app.agentic.eol.utils.tool_manifest_index import ToolAffordance, ToolManifest  # type: ignore[import-not-found]

MANIFESTS: list[ToolManifest] = [
    ToolManifest(
        tool_name="azmcp_extension_cli_generate",
        source="azure_mcp",
        domains=frozenset({"deployment", "azure_management", "sre_remediation", "networking"}),
        tags=frozenset({"cli", "generate_command", "az", "escape_hatch"}),
        affordance=ToolAffordance.READ,
        example_queries=(
            "get IP address of private endpoint",
            "generate azure CLI command",
            "az network query",
        ),
        conflicts_with=frozenset(),
        conflict_note=(
            "azmcp_extension_cli_generate uses Azure's CLI Copilot API to generate a CORRECT az command "
            "from natural language intent. ALWAYS use this as step 1 before azure_cli_execute_command. "
            "Required params: intent (string, natural language goal), cliType (string, use 'az'). "
            "The result contains a '_generated_command' field with the ready-to-run az command."
        ),
        preferred_over=frozenset(),
        requires_confirmation=False,
    ),
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
            "When azmcp_extension_cli_generate is available, use it as step 1 to generate the correct command, "
            "then pass '$step_1._generated_command' as the command param here (step 2). "
            "Use azure_cli_execute_command alone only when azmcp_extension_cli_generate is not available. "
            "Mutating commands require confirmed=true. 'az group delete' and 'az ad' are always blocked."
        ),
        preferred_over=frozenset(),
        requires_confirmation=True,
    ),
]
