"""CVE Management domain sub-agent — wraps CVE management tools behind cve_agent meta-tool.

Inherits from DomainSubAgent and provides CVE-specific system prompt covering
search, scanning, patch discovery, and remediation workflows.

The orchestrator replaces all CVE tools with a single ``cve_agent``
meta-tool. When invoked, the orchestrator delegates to this agent which
runs its own ReAct loop over the 4 CVE MCP tools.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Coroutine, Dict, List, Optional

try:
    from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
except (ModuleNotFoundError, ImportError):
    try:
        # Direct module import fallback
        import importlib.util as _ilu
        import pathlib as _pl
        _dsap = _pl.Path(__file__).resolve().parent / "domain_sub_agent.py"
        _spec = _ilu.spec_from_file_location("domain_sub_agent", _dsap)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        DomainSubAgent = _mod.DomainSubAgent
    except Exception:
        raise ImportError("Cannot import DomainSubAgent from agents.domain_sub_agent")


class CVESubAgent(DomainSubAgent):
    """Focused sub-agent for CVE vulnerability management operations.

    Owns 4 CVE management tools for search, scanning, patch discovery,
    and remediation. Has domain-specific system prompt for CVE workflows
    with strong safety guardrails.
    """

    _DOMAIN_NAME = "cve"
    _MAX_ITERATIONS = 15
    _TIMEOUT_SECONDS = 45.0
    _SUPPORTED_DOMAINS = ["cve", "vulnerability", "security"]
    _CAPABILITIES = [
        "CVE search and discovery",
        "Inventory vulnerability scanning",
        "Patch discovery and mapping",
        "CVE remediation workflows"
    ]

    _SYSTEM_PROMPT = """\
You are the CVE Vulnerability Management specialist agent.
You have access to 4 CVE management tools for Azure VMs and Arc-enabled servers.
Your job is to handle CVE search, inventory scanning, patch discovery,
and remediation workflows.

═══════════════════════════════════════════════════════════════
CRITICAL RULE — NO FABRICATION
═══════════════════════════════════════════════════════════════

You MUST call a tool before presenting ANY CVE data.
NEVER generate fake CVE IDs, fake patch names, fake VM lists, or example data.
If a tool call fails, report the real error — do NOT substitute made-up data.

Examples of FORBIDDEN behavior:
❌ "CVE-2024-1234 is a critical vulnerability affecting Linux..."
   → You haven't called search_cve yet!
❌ "I found 12 VMs affected: vm-prod-01, vm-prod-02, ..."
   → You haven't called scan_inventory yet!
❌ "Install KB5001234 and KB5005678 to fix this"
   → You haven't called get_patches yet!

Always call the tool FIRST, then present real data from the response.

═══════════════════════════════════════════════════════════════
SAFETY — REMEDIATION WORKFLOWS
═══════════════════════════════════════════════════════════════

Before triggering patch installation (trigger_remediation):

1. Call get_patches to understand what will be installed
2. Call trigger_remediation with dry_run=True
3. Present the patch plan to the user:
   - List all patches (KB numbers, package names)
   - Explain reboot requirements clearly
   - Show affected VM and severity
4. Wait for explicit confirmation from user
5. Only after confirmation: call trigger_remediation with confirmed=True

NEVER install patches without user approval.
NEVER skip the dry_run step.

For multi-VM remediation:
- List ALL affected VMs before confirming
- Warn about reboot cascades and downtime windows
- Require batch confirmation (single approval for all VMs in list)

If the system blocks remediation (ALLOW_REAL_REMEDIATION flag):
- Inform the user why remediation is blocked
- Explain the dry_run plan
- Stop — do not retry or bypass

═══════════════════════════════════════════════════════════════
"""

    def __init__(
        self,
        tool_definitions: List[Dict[str, Any]],
        tool_invoker: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        event_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        *,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        super().__init__(
            tool_definitions=tool_definitions,
            tool_invoker=tool_invoker,
            event_callback=event_callback,
            conversation_context=conversation_context,
        )


def build_cve_meta_tool() -> Dict[str, Any]:
    """Returns the meta-tool definition for cve_agent.

    This meta-tool replaces all individual CVE tools in the orchestrator's
    catalog, reducing cognitive load and improving routing accuracy.
    """
    return {
        "type": "function",
        "function": {
            "name": "cve_agent",
            "description": """Delegate to the CVE Vulnerability Management specialist agent.

Use this for ANY CVE-related queries:
- "Search for CVE-2024-1234"
- "What CVEs affect my infrastructure?"
- "Scan my VMs for vulnerabilities"
- "What patches fix CVE-2024-5678?"
- "Remediate CVE-2024-1234 on vm-prod-01"
- "Show me critical CVEs published this month"
- "Which VMs are affected by CVE-2024-9999?"

The CVE agent has access to:
- CVE search across multiple sources (NVD, CVE.org, vendor feeds)
- VM inventory scanning for CVE exposure
- Patch discovery and CVE-to-patch mapping
- Remediation workflows with safety checks

DO NOT use this for:
- Generic VM inventory listing (use main conversation)
- Patch compliance without CVE context (use patch_agent)
- Azure Policy administration
- Network topology design
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "User's CVE-related request in natural language",
                    },
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, for scanning/remediation)",
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Resource group name (optional, for scanning/remediation)",
                    },
                },
                "required": ["request"],
            },
        },
    }
