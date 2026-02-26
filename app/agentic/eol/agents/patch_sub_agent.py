"""Patch Management domain sub-agent — wraps patch management tools behind patch_agent meta-tool.

Inherits from DomainSubAgent and provides a patch management-specific system prompt
covering patch assessment, compliance analysis, installation workflows, and reboot management.

The orchestrator replaces all patch-source tools with a single ``patch_agent``
meta-tool.  When invoked, the orchestrator delegates to this agent which
runs its own ReAct loop over the full patch management tool set.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Coroutine, Dict, List, Optional

try:
    from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
except (ModuleNotFoundError, ImportError):
    try:
        # Direct module import — avoids agents/__init__.py cascade
        import importlib.util as _ilu
        import pathlib as _pl
        _dsap = _pl.Path(__file__).resolve().parent / "domain_sub_agent.py"
        _spec = _ilu.spec_from_file_location("domain_sub_agent", _dsap)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        DomainSubAgent = _mod.DomainSubAgent
    except Exception:
        raise ImportError("Cannot import DomainSubAgent from agents.domain_sub_agent")


class PatchSubAgent(DomainSubAgent):
    """Focused sub-agent for Azure Patch Management operations.

    Owns 7 patch management tools for Azure VMs and Arc-enabled servers.
    Has a concise domain-specific system prompt for patch assessment,
    compliance analysis, and remediation workflows.
    """

    _DOMAIN_NAME = "patch"
    _MAX_ITERATIONS = 15
    _TIMEOUT_SECONDS = 45.0

    _SYSTEM_PROMPT = """\
You are the Azure Patch Management specialist agent.
You have access to 7 patch management tools for Azure VMs and Arc-enabled servers.
Your job is to handle patch assessment, compliance analysis, patch installation,
and reboot management.

CRITICAL RULE — NO FABRICATION:
You MUST call a tool before presenting ANY patch data.
NEVER generate fake VM names, patch counts, or example data.
If a tool call fails, report the real error — do NOT substitute made-up data.

SAFETY — DESTRUCTIVE OPERATIONS:
Before installing patches:
1. Call assess_vm_patches or query_patch_assessments to understand current state.
2. Present the patch list to the user with severity breakdown.
3. Explain reboot requirements clearly.
4. Wait for confirmation — do NOT install patches without explicit approval.

AVAILABLE TOOLS:

Discovery:
  → list_azure_vms(subscription_id, resource_group=None)
    Lists all Azure VMs and Arc-enabled servers in a subscription.
    Returns unified list tagged with vm_type ('arc' or 'azure-vm').
    Use this first to discover patch targets.

Assessment:
  → query_patch_assessments(subscription_id, machine_name=None, vm_type='arc')
    Query Azure Resource Graph for historical patch assessment data.
    Returns stored assessments without triggering new scans.
    Use this to check last-known patch status quickly.

  → assess_vm_patches(machine_name, subscription_id, resource_group, vm_type='arc', resource_id=None)
    Trigger a live patch assessment on a VM or Arc server.
    Returns operation_url (fire-and-forget, completes in 1-3 minutes).
    Use this when you need fresh patch data.

  → get_assessment_result(machine_name, subscription_id, vm_type='arc')
    Fetch latest assessment result from Azure Resource Graph.
    Use after assess_vm_patches to retrieve completed assessment.

Installation:
  → install_vm_patches(machine_name, subscription_id, resource_group, classifications=['Critical','Security'], vm_type='arc', ...)
    Trigger patch installation with classification filters.
    Parameters:
      - classifications: ['Critical', 'Security', 'Important', 'Updates', etc.]
      - reboot_setting: 'IfRequired' | 'NeverReboot' | 'AlwaysReboot'
      - maximum_duration: 'PT2H' (ISO 8601 duration)
      - kb_numbers_to_include/exclude: Specific KB IDs or package names
    Returns operation_url for status monitoring.
    Installation can take 10-30+ minutes.

  → get_install_status(operation_url)
    Poll installation progress using operation_url from install_vm_patches.
    Returns status and detailed results when completed.

Reporting:
  → get_vm_patch_summary(subscription_id, resource_group=None)
    Consolidated patch compliance summary across all VMs.
    Returns: total VMs, compliant count, non-compliant count, compliance %.
    Use for dashboard views and reporting.

PATCH SEVERITY LEVELS (most critical first):
1. **Critical** — Severe vulnerabilities, immediate installation recommended
2. **Security** — Security vulnerabilities, high priority
3. **Important** — Important updates, medium priority
4. **Updates** — Recommended updates, lower priority
5. **Other** — Optional updates, lowest priority

COMPLIANCE ANALYSIS:
- **Compliant**: No Critical or Security patches pending
- **Non-Compliant**: Has Critical or Security patches pending
- Present compliance percentage: (compliant VMs / total VMs) × 100

REBOOT REQUIREMENTS:
- Always check rebootBehavior field in patch assessment results
- Common values: 'AlwaysRequiresReboot', 'CanRequestReboot', 'NeverReboots'
- Warn users about required reboots before installation
- Default reboot_setting is 'IfRequired' (reboot if patches require it)

COMMON WORKFLOWS:

**Compliance Check:**
1. list_azure_vms → get VM inventory
2. query_patch_assessments → check last assessments
3. get_vm_patch_summary → calculate compliance metrics
4. Report: X% compliant, Y VMs need critical patches

**Patch Assessment:**
1. list_azure_vms → find target VMs
2. assess_vm_patches → trigger fresh scan (if last assessment > 7 days)
3. get_assessment_result → retrieve results (after 1-3 min)
4. Analyze: critical vs security vs other patches
5. Report reboot requirements

**Patch Installation:**
1. assess_vm_patches → ensure current assessment
2. Present patches to user with severity breakdown
3. Get user confirmation (required!)
4. install_vm_patches with approved classifications
5. get_install_status → monitor progress
6. Report: installed count, failed count, reboot status

**Multi-VM Patching:**
1. list_azure_vms → get all VMs
2. query_patch_assessments → bulk assessment check
3. Filter VMs with critical/security patches
4. Present list to user for approval
5. Loop: install_vm_patches for each approved VM
6. get_vm_patch_summary → final compliance report

PARAMETER DEFAULTS:
- If subscription_id missing → ask user
- If vm_type not specified → default to 'arc'
- If classifications not specified → default to ['Critical', 'Security']
- If reboot_setting not specified → default to 'IfRequired'
- If maximum_duration not specified → default to 'PT2H'

CONTEXT INJECTION:
If the user's request includes a subscription_id or resource_group in context,
use those values automatically without asking.

RESPONSE FORMAT:
Always structure your responses clearly:
- Start with summary (e.g., "Found 15 VMs, 3 need critical patches")
- Show breakdown by severity
- Highlight non-compliant VMs
- Explain next steps
- For installation: get explicit user confirmation

Remember: Patch management affects production systems. Always err on the side of
caution and require user confirmation before installing patches.
"""

    def __init__(
        self,
        tool_definitions: List[Dict[str, Any]],
        tool_invoker: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        event_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
        *,
        domain_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_iterations: Optional[int] = None,
    ) -> None:
        """Initialize the Patch sub-agent.

        Args:
            tool_definitions: OpenAI function-calling defs for patch tools only.
            tool_invoker: ``async (tool_name, arguments) → result_dict`` callback.
            event_callback: Optional SSE emitter ``async (event_type, content, **kw)``.
            domain_name: Override domain name (default: "patch").
            system_prompt: Override system prompt.
            max_iterations: Override max iterations.
        """
        if domain_name:
            self._DOMAIN_NAME = domain_name
        if system_prompt:
            self._SYSTEM_PROMPT = system_prompt
        if max_iterations:
            self._MAX_ITERATIONS = max_iterations

        super().__init__(
            tool_definitions=tool_definitions,
            tool_invoker=tool_invoker,
            event_callback=event_callback,
        )

        # Context for parameter injection
        self._context: Dict[str, Any] = {}

    async def _pre_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Pre-process tool calls to inject context parameters.

        Injects subscription_id and resource_group from context if not provided.
        Adds default classifications for install operations.
        """
        # Inject subscription_id from context if missing
        if "subscription_id" not in arguments and "subscription_id" in self._context:
            arguments["subscription_id"] = self._context["subscription_id"]

        # Inject resource_group from context if missing
        if "resource_group" not in arguments and "resource_group" in self._context:
            arguments["resource_group"] = self._context["resource_group"]

        # Default classifications for install operations
        if tool_name == "install_vm_patches" and "classifications" not in arguments:
            arguments["classifications"] = ["Critical", "Security"]

        # No modification needed — return None to proceed with original call
        return None


def build_patch_meta_tool() -> Dict[str, Any]:
    """Returns the meta-tool definition for patch_agent.

    This replaces all individual patch tools in the orchestrator's catalog.
    The orchestrator delegates patch-related requests to the PatchSubAgent.
    """
    return {
        "type": "function",
        "function": {
            "name": "patch_agent",
            "description": """Delegate to the Azure Patch Management specialist agent.

Use this for ANY patch-related queries:
- "Show patch status for my VMs"
- "Which VMs need critical patches?"
- "Install security patches on vm-prod-01"
- "Check compliance across all servers"
- "What's the reboot impact of pending patches?"
- "Generate a patch compliance report"

The patch agent has access to all patch management tools and can:
- List Azure VMs and Arc-enabled servers
- Assess current patch state via Azure Resource Graph or live API calls
- Analyze compliance (critical/security patches = non-compliant)
- Trigger patch assessments (assessPatches API, completes in 1-3 min)
- Install patches with classification filters (Critical, Security, etc.)
- Track installation progress and reboot requirements
- Generate compliance reports and summaries

Provide natural language requests — the agent will use the right tools and workflows.

IMPORTANT: The patch agent will ask for user confirmation before installing patches.
Never bypass this safety check.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "User's patch management request in natural language",
                    },
                    "subscription_id": {
                        "type": "string",
                        "description": "Azure subscription ID (optional, can be inferred from context)",
                    },
                    "resource_group": {
                        "type": "string",
                        "description": "Azure resource group (optional, can be inferred from context)",
                    },
                },
                "required": ["request"],
            },
        },
    }
