"""Azure Monitor sub-agent for the hybrid orchestrator architecture.

Handles the full lifecycle of Azure Monitor Community resources:
  discover → present → deploy

This agent has its own focused system prompt and only sees monitor + CLI tools,
eliminating tool-selection confusion and multi-step workflow issues.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from copy import deepcopy
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from utils.logging_config import get_logger

logger = get_logger(__name__, level=os.getenv("LOG_LEVEL", "DEBUG"))


class MonitorAgent:
    """Focused sub-agent for Azure Monitor Community resource discovery and deployment.

    Design principles:
    - Owns only monitor + azure_cli tools (~6-10 tools vs 100+ in orchestrator)
    - Has a concise, domain-specific system prompt with deployment rules baked in
    - Runs its own ReAct loop (up to 15 iterations — monitor flows are bounded)
    - Forwards SSE events through a callback so the orchestrator can relay them
    - Stateless per-invocation — no persistent conversation history
    """

    _SYSTEM_PROMPT = """\
You are the Azure Monitor resource specialist. You discover, present, and deploy
Azure Monitor Community resources (workbooks, alerts, KQL queries) for users.

⚠️ CRITICAL DEPLOYMENT RULE (read first) ⚠️
Before calling deploy_query, deploy_alert, or deploy_workbook, you MUST have non-empty values for ALL required parameters.
If the user has NOT provided resource_group, workspace_name, or other required deployment details:
  → Do NOT call the deploy tool. Instead, RESPOND to the user asking for the missing values.
  → Offer to look them up by calling azure_cli_execute_command with:
      'az monitor log-analytics workspace list --query [].{{name:name,id:id,resourceGroup:resourceGroup}} -o table'
Do NOT pass empty strings '' to any deploy tool parameter. This will be blocked.

TOOLS YOU HAVE:
• get_service_monitor_resources — find ALL resources for a service in ONE call.
• list_resources — drill into a specific category + type if needed.
• search_categories — find categories by keyword.
• list_categories — list all categories for a resource type.
• get_resource_content — download a resource's content (KQL text, workbook JSON, alert config).
• deploy_workbook — deploy a workbook to Azure via ARM template.
• deploy_query — deploy a KQL query as a saved search in a Log Analytics workspace.
• deploy_alert — deploy an alert rule as a scheduled query in Azure Monitor.
• azure_cli_execute_command — run any az CLI command (fallback only).

WORKFLOW — DISCOVERY:
1. Call get_service_monitor_resources(keyword=<service>) to get everything in one call.
2. Present results as an HTML table with columns:
   Name | Type | Deploy Status | Action
3. Every resource is ✅ Deployable. Show the deploy method in the Action column:
   - Workbooks: "Deploy via deploy_workbook"
   - Queries: "Deploy via deploy_query"
   - Alerts: "Deploy via deploy_alert"
4. Ask which resource(s) the user wants to deploy.

WORKFLOW — DEPLOYMENT:
When the user picks a resource to deploy:

Step 1 — Check if you have ALL required parameters with non-empty values:
  For queries:   resource_group, workspace_name
  For alerts:    resource_group, scopes (full workspace resource ID)
  For workbooks: subscription_id, resource_group, workbook_name, location

  If ANY parameter is missing or unknown:
    → The system will automatically look up available workspaces and resource groups.
    → A selection table will be presented to the user.
    → Wait for the user to specify their choice before retrying deployment.
    → Do NOT call the deploy tool until the user has provided all required values.

Step 2 — Confirm deployment plan:
  • Show: Resource Name, Type, Target (resource group + workspace), all param values.
  • Wait for explicit user confirmation.

Step 3 — Deploy (only after Steps 1-2 are complete with all params filled):

Workbooks:
  → deploy_workbook(download_url, subscription_id, resource_group, workbook_name, location).

Queries (.kql):
  → deploy_query(download_url, resource_group, workspace_name, query_name, category).
  → The tool handles KQL formatting automatically.

Alerts:
  → deploy_alert(download_url, resource_group, scopes, alert_name, severity, threshold, ...).
  → The tool handles KQL extraction and formatting automatically.

RULES:
• NEVER call deploy_query, deploy_alert, or deploy_workbook with empty '' parameters.
• If the user says 'deploy all' or 'deploy it', STILL ask for resource group and workspace name first.
• NEVER fabricate CLI commands.
• Do NOT manually construct 'az monitor' commands — the deploy tools handle it.
• Return responses as raw HTML. Use <table> for structured data.
• NEVER generate fake data. Only present data from tool results."""

    _MAX_ITERATIONS = 15

    def __init__(
        self,
        tool_definitions: List[Dict[str, Any]],
        tool_invoker: Callable[[str, Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]],
        event_callback: Optional[Callable[..., Coroutine[Any, Any, None]]] = None,
    ) -> None:
        """
        Args:
            tool_definitions: OpenAI function-calling tool defs (monitor + CLI only).
            tool_invoker: Async callable(tool_name, arguments) → result dict.
            event_callback: Optional async callable(event_type, content, **kw) for SSE events.
        """
        self._tool_definitions = tool_definitions
        self._invoke_tool = tool_invoker
        self._push_event = event_callback or self._noop_event

    # Required-param specs per deploy tool: {tool_name: [param_names]}
    _DEPLOY_REQUIRED_PARAMS: Dict[str, List[str]] = {
        "deploy_query": ["resource_group", "workspace_name"],
        "deploy_alert": ["resource_group", "scopes"],
        "deploy_workbook": ["subscription_id", "resource_group", "workbook_name", "location"],
    }

    @staticmethod
    def _check_deploy_params(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return a validation-error dict if a deploy tool is called with empty required params.

        Returns None if the tool is not a deploy tool or all required params are present.
        """
        required = MonitorAgent._DEPLOY_REQUIRED_PARAMS.get(tool_name)
        if not required:
            return None  # Not a deploy tool — no validation needed

        missing = [p for p in required if not str(arguments.get(p, "")).strip()]
        if not missing:
            return None  # All params are filled

        return {
            "success": True,
            "status": "needs_user_input",
            "message": (
                f"I need the following information from the user before I can deploy: {', '.join(missing)}. "
                "Do NOT say deployment failed. Instead, politely ask the user to provide: " + ", ".join(missing) + ". "
                "Offer to look up available workspaces and resource groups by calling azure_cli_execute_command with: "
                "'az monitor log-analytics workspace list --query [].{name:name,id:id,resourceGroup:resourceGroup} -o table'. "
                "Frame your response as: 'To deploy this resource, I need a few details from you:' "
                "followed by a bullet list of the missing parameters. "
                "Do NOT mention any error, failure, or blocking."
            ),
            "missing_params": missing,
            "action_required": "ASK_USER",
        }

    async def _lookup_deploy_options(self) -> Tuple[str, str]:
        """Auto-discover Log Analytics workspaces and resource groups via CLI.

        Returns:
            (workspaces_html, resource_groups_html) — HTML table strings, empty if lookup fails.
        """
        workspaces_html = ""
        rg_html = ""

        try:
            # Look up Log Analytics workspaces
            ws_result = await self._invoke_tool("azure_cli_execute_command", {
                "command": "az monitor log-analytics workspace list --query \"[].{Name:name, ResourceGroup:resourceGroup, Location:location, Id:id}\" -o json"
            })
            ws_data = None
            if isinstance(ws_result, dict):
                output = ws_result.get("output") or ws_result.get("result") or ws_result.get("response", "")
                if isinstance(output, str):
                    try:
                        ws_data = json.loads(output)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(output, list):
                    ws_data = output

            if ws_data and isinstance(ws_data, list) and len(ws_data) > 0:
                rows = ""
                for ws in ws_data:
                    name = ws.get("Name", ws.get("name", ""))
                    rg = ws.get("ResourceGroup", ws.get("resourceGroup", ""))
                    loc = ws.get("Location", ws.get("location", ""))
                    ws_id = ws.get("Id", ws.get("id", ""))
                    rows += (
                        f"<tr><td>{name}</td><td>{rg}</td><td>{loc}</td>"
                        f"<td style='font-size:0.8em;word-break:break-all'>{ws_id}</td></tr>"
                    )
                workspaces_html = (
                    "<table border='1' style='border-collapse:collapse;width:100%'>"
                    "<tr><th>Workspace Name</th><th>Resource Group</th><th>Location</th><th>Resource ID (for alerts)</th></tr>"
                    f"{rows}</table>"
                )
                logger.info("✅ Found %d Log Analytics workspaces", len(ws_data))
            else:
                logger.warning("No workspaces found or CLI call failed")
        except Exception as exc:
            logger.warning("Failed to lookup workspaces: %s", exc)

        # If no workspaces found, try listing resource groups as fallback
        if not workspaces_html:
            try:
                rg_result = await self._invoke_tool("azure_cli_execute_command", {
                    "command": "az group list --query \"[].{Name:name, Location:location}\" -o json"
                })
                rg_data = None
                if isinstance(rg_result, dict):
                    output = rg_result.get("output") or rg_result.get("result") or rg_result.get("response", "")
                    if isinstance(output, str):
                        try:
                            rg_data = json.loads(output)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif isinstance(output, list):
                        rg_data = output

                if rg_data and isinstance(rg_data, list) and len(rg_data) > 0:
                    rows = ""
                    for rg in rg_data:
                        name = rg.get("Name", rg.get("name", ""))
                        loc = rg.get("Location", rg.get("location", ""))
                        rows += f"<tr><td>{name}</td><td>{loc}</td></tr>"
                    rg_html = (
                        "<table border='1' style='border-collapse:collapse;width:100%'>"
                        "<tr><th>Resource Group</th><th>Location</th></tr>"
                        f"{rows}</table>"
                    )
                    logger.info("✅ Found %d resource groups", len(rg_data))
            except Exception as exc:
                logger.warning("Failed to lookup resource groups: %s", exc)

        return workspaces_html, rg_html

    @staticmethod
    async def _noop_event(event_type: str, content: str, **kw: Any) -> None:
        """No-op event callback when none is provided."""

    async def run(self, user_message: str) -> Dict[str, Any]:
        """Execute the monitor sub-agent ReAct loop.

        Returns a dict with:
          - success (bool)
          - response (str): final HTML response
          - tool_calls_made (int)
          - iterations (int)
        """
        start_time = time.time()
        tool_calls_made = 0

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        await self._push_event(
            "reasoning",
            f"[Monitor Agent] Analyzing: {user_message}",
            agent="monitor",
        )

        final_text = ""

        for iteration in range(1, self._MAX_ITERATIONS + 1):
            elapsed = time.time() - start_time
            if elapsed > 45:
                logger.warning("MonitorAgent approaching timeout (%.1fs)", elapsed)
                final_text = (
                    final_text
                    or "<p>Monitor agent processing timed out. Please try a simpler request.</p>"
                )
                break

            # Call LLM
            try:
                response = await self._call_llm(messages)
            except Exception as exc:
                logger.exception("MonitorAgent LLM call failed: %s", exc)
                return {
                    "success": False,
                    "response": f"Monitor agent error: {exc}",
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration,
                }

            assistant_msg = response["message"]
            messages.append(assistant_msg)

            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # No tools requested — this is the final answer
                final_text = assistant_msg.get("content", "") or ""
                await self._push_event(
                    "synthesis",
                    "[Monitor Agent] Response ready",
                    agent="monitor",
                    iteration=iteration,
                )
                break

            # Process tool calls
            tool_names = [tc["function"]["name"] for tc in tool_calls]
            await self._push_event(
                "action",
                f"[Monitor Agent] Calling {len(tool_calls)} tool(s): {', '.join(tool_names)}",
                agent="monitor",
                iteration=iteration,
                tool_names=tool_names,
            )

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except json.JSONDecodeError:
                    arguments = {}

                tool_calls_made += 1
                logger.info(
                    "🧰 MonitorAgent tool %d: %s args=%s",
                    tool_calls_made,
                    tool_name,
                    json.dumps(arguments, ensure_ascii=False)[:300],
                )

                # ── Pre-call validation: block deploy tools with empty params ──
                blocked = self._check_deploy_params(tool_name, arguments)
                if blocked:
                    logger.warning(
                        "⛔ MonitorAgent blocked %s — missing params: %s",
                        tool_name, blocked["missing_params"],
                    )
                    # Auto-discover available values for missing params
                    missing = blocked["missing_params"]
                    resource_name = arguments.get("query_name") or arguments.get("alert_name") or arguments.get("workbook_name") or "this resource"

                    await self._push_event(
                        "action",
                        "[Monitor Agent] Looking up available workspaces and resource groups...",
                        agent="monitor",
                        iteration=iteration,
                    )

                    # Programmatically look up workspaces and resource groups
                    workspaces_html, rg_html = await self._lookup_deploy_options()

                    # Build selection HTML
                    params_section = ""
                    needs_workspace = any(p in ("workspace_name", "scopes") for p in missing)
                    needs_rg = "resource_group" in missing
                    needs_sub = "subscription_id" in missing
                    needs_location = "location" in missing

                    if needs_rg or needs_workspace or needs_sub:
                        if workspaces_html:
                            params_section += (
                                "<p><strong>Available Log Analytics Workspaces:</strong></p>"
                                + workspaces_html
                            )
                        elif rg_html:
                            params_section += (
                                "<p><strong>Available Resource Groups:</strong></p>"
                                + rg_html
                            )

                    if needs_location:
                        params_section += (
                            "<p><strong>Location:</strong> Please specify the Azure region "
                            "(e.g., <code>eastus</code>, <code>westus2</code>, <code>southeastasia</code>).</p>"
                        )

                    if not params_section:
                        # Fallback: just list what's needed
                        param_bullets = "".join(
                            f"<li><strong>{p.replace('_', ' ').title()}</strong></li>" for p in missing
                        )
                        params_section = f"<ul>{param_bullets}</ul>"

                    final_text = (
                        f"<p>To deploy <strong>{resource_name}</strong>, please select the target from the options below:</p>"
                        f"{params_section}"
                        "<p>Please provide the <strong>workspace name</strong> and <strong>resource group</strong> "
                        "you'd like to deploy to (e.g., <em>\"deploy to workspace my-workspace in resource group my-rg\"</em>).</p>"
                    )
                    await self._push_event(
                        "synthesis",
                        "[Monitor Agent] Presenting deployment options to user",
                        agent="monitor",
                        iteration=iteration,
                    )
                    break  # Break inner for-loop
                
                result = await self._invoke_tool(tool_name, arguments)

                # Extract CLI command for display
                cli_command = None
                if tool_name == "azure_cli_execute_command" and isinstance(arguments, dict):
                    cli_command = arguments.get("command")

                observation_success = bool(result.get("success")) if isinstance(result, dict) else False

                await self._push_event(
                    "observation",
                    "[Monitor Agent] Tool execution completed",
                    agent="monitor",
                    iteration=iteration,
                    tool_name=tool_name,
                    tool_parameters=arguments,
                    cli_command=cli_command,
                    tool_result=result,
                    is_error=not observation_success,
                )

                # Append tool result to messages
                try:
                    result_text = json.dumps(result, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    result_text = str(result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text,
                })

            # If a deploy tool was blocked, final_text is already set — break outer loop
            if final_text:
                break

        duration = time.time() - start_time
        logger.info(
            "📊 MonitorAgent complete: %d iterations, %d tool calls, %.1fs",
            iteration,
            tool_calls_made,
            duration,
        )

        return {
            "success": True,
            "response": final_text,
            "tool_calls_made": tool_calls_made,
            "iterations": iteration,
            "duration_seconds": duration,
        }

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call Azure OpenAI with the current messages and monitor tools.

        Returns:
            dict with 'message' (the assistant message dict) and 'tool_calls' (list or empty).
        """
        from openai import AsyncAzureOpenAI

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        )

        client: Optional[AsyncAzureOpenAI] = None
        try:
            if api_key:
                client = AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )
            else:
                from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential

                credential = AsyncDefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                    exclude_shared_token_cache_credential=True,
                    exclude_visual_studio_code_credential=True,
                    exclude_powershell_credential=True,
                )
                token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                client = AsyncAzureOpenAI(
                    api_key=token.token,
                    azure_endpoint=endpoint,
                    api_version=api_version,
                )

            create_kwargs: Dict[str, Any] = {
                "model": deployment,
                "messages": messages,
                "temperature": 0.15,
                "max_tokens": 3000,
            }
            if self._tool_definitions:
                create_kwargs["tools"] = [
                    {"type": "function", "function": t.get("function", t)}
                    for t in self._tool_definitions
                ]

            raw = await client.chat.completions.create(**create_kwargs)
            choice = raw.choices[0]

            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": choice.message.content or ""}

            tool_calls_out = []
            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]
                tool_calls_out = assistant_msg["tool_calls"]

            return {"message": assistant_msg, "tool_calls": tool_calls_out}

        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass
