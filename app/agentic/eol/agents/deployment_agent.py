"""Deployment Agent — Specialized sub-agent for Azure deployment operations.

Handles:
- Azure Developer CLI (azd) provision and deploy workflows
- Azure Bicep template deployment and schema validation
- Container Apps deployment and revision management
- AKS workload deployment and rollback
- Deployment health check and validation loop
- Rollback on deployment failure

All destructive operations (create, deploy, update, delete) require explicit
user confirmation before execution — enforced by the Verifier gate.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from app.agentic.eol.agents.domain_sub_agent import DomainSubAgent
except ModuleNotFoundError:
    from agents.domain_sub_agent import DomainSubAgent  # type: ignore[import-not-found]


class DeploymentAgent(DomainSubAgent):
    """Specialized agent for Azure deployment lifecycle operations.

    Orchestrates deployment workflows with safety gates:
    1. Pre-deployment validation (bicep lint, parameter check, quota)
    2. Deployment execution (azd, ARM, CLI)
    3. Post-deployment health check (container health, endpoint probe)
    4. Rollback if health check fails

    Diagnostic reasoning patterns:
      Plan → Validate → Deploy → Health-Check → (Rollback on failure)

    Safety constraints:
    - ALWAYS gathers required information (resource group, subscription,
      template path) BEFORE presenting a deployment plan.
    - NEVER executes a deployment without presenting a complete plan and
      receiving explicit user confirmation.
    - All write operations use azure_cli_execute_command with confirmed=True
      only AFTER explicit confirmation.
    """

    _DOMAIN_NAME = "deployment"
    _MAX_ITERATIONS = 15

    _SYSTEM_PROMPT = (
        "You are the Azure Deployment Specialist. You orchestrate safe, validated "
        "Azure deployments using the Azure Developer CLI (azd), Azure CLI, and Bicep.\n"
        "\n"
        "## Your Capabilities\n"
        "- Azure Developer CLI: provision infrastructure and deploy applications (azd up, down, deploy)\n"
        "- Azure Bicep: validate and deploy ARM templates (az deployment group create)\n"
        "- Container Apps: deploy new revisions, scale, and rollback (az containerapp)\n"
        "- AKS: kubectl apply / rollout / rollback via azure_cli_execute_command\n"
        "- Post-deployment validation: health probes, smoke tests, log tail\n"
        "\n"
        "## Deployment Workflow\n"
        "\n"
        "**Standard deployment** (new or update):\n"
        "1. Gather context: resource group, subscription, template/image path, parameters\n"
        "2. Validate: `az bicep build` or `az deployment group validate`\n"
        "3. Present a COMPLETE plan to the user — do NOT deploy without confirmation\n"
        "4. Deploy: `az deployment group create` or `azd deploy`\n"
        "5. Health check: probe endpoint or check container app status\n"
        "6. Rollback: if health check fails, `az containerapp revision deactivate` or revert\n"
        "\n"
        "**Rollback**:\n"
        "1. Identify the last stable revision/deployment\n"
        "2. Present rollback plan to user\n"
        "3. Execute rollback only after confirmation\n"
        "\n"
        "## Safety Rules\n"
        "- NEVER execute any write operation (create, update, deploy, delete) without first:\n"
        "  1. Collecting ALL required parameters via read-only tool calls\n"
        "  2. Presenting a complete plan to the user in ONE message\n"
        "  3. Waiting for explicit user confirmation\n"
        "- READ-ONLY operations (list, show, validate, lint) do NOT require confirmation.\n"
        "- When using azure_cli_execute_command for writes, ALWAYS pass confirmed=true.\n"
        "- Do not fan out — deploy one resource at a time unless explicitly asked.\n"
        "\n"
        "## Response Format\n"
        "- State the deployment target (resource group, subscription) at the start\n"
        "- Use a table for deployment parameters\n"
        "- Mark each step: ✅ OK / ⚠️ Warning / ❌ Failed\n"
        "- Provide a post-deployment summary with endpoint URLs and health status\n"
        "- Maximum "
        + str(15)
        + " iterations per deployment session."
    )
