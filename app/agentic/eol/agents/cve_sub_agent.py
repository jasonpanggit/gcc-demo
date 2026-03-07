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
# System prompt content will be added in next task
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
