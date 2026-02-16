"""SRE Orchestrator Agent - Coordinates all SRE operations.

The orchestrator routes requests to appropriate tools and agents,
manages multi-tool workflows, and aggregates results.
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.agent_context_store import get_context_store
    from app.agentic.eol.utils.agent_message_bus import get_message_bus
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from app.agentic.eol.utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.agent_message_bus import get_message_bus
    from utils.logger import get_logger
    from utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )


logger = get_logger(__name__)


class SREOrchestratorAgent(BaseSREAgent):
    """SRE Orchestrator Agent.

    Responsibilities:
    - Analyze user requests and extract intent
    - Route requests to appropriate tools/agents
    - Orchestrate multi-tool workflows
    - Aggregate and synthesize results
    - Manage workflow context and state

    The orchestrator coordinates 48 existing SRE tools across:
    - Resource health & diagnostics
    - Incident response
    - Performance monitoring
    - Safe remediation
    - Cost optimization
    - SLO management
    - Security & compliance
    - And more...
    """

    def __init__(self):
        """Initialize SRE Orchestrator Agent."""
        super().__init__(
            agent_type="sre-orchestrator",
            agent_id="sre-orchestrator-main",
            max_retries=2,
            timeout=300
        )

        self.registry = get_agent_registry()
        self.message_bus = get_message_bus()
        self._context_store = None

        # User interaction and response formatting
        self.formatter = SREResponseFormatter()
        self.interaction_handler = None  # Initialized in _initialize_impl

        # Intent patterns for routing
        self._intent_patterns = self._build_intent_patterns()

    async def _initialize_impl(self) -> None:
        """Initialize orchestrator-specific resources."""
        # Initialize context store
        self._context_store = await get_context_store()

        # Initialize interaction handler with Azure CLI executor
        self.interaction_handler = get_interaction_handler(
            azure_cli_executor=self._execute_azure_cli
        )

        # Subscribe to message bus
        await self.message_bus.subscribe(
            self.agent_id,
            message_types=["request.*", "response", "event.*"]
        )

        logger.info("✓ SRE Orchestrator initialized")

    async def _cleanup_impl(self) -> None:
        """Clean up orchestrator resources."""
        await self.message_bus.unsubscribe(self.agent_id)

    def _build_intent_patterns(self) -> Dict[str, List[Tuple[str, List[str]]]]:
        """Build intent patterns for request routing.

        Returns:
            Dictionary mapping categories to (pattern, tools) tuples
        """
        return {
            # Health & Diagnostics
            "health": [
                (r"(check|health|status|diagnose).*(?:resource|vm|app|container|aks)",
                 ["check_resource_health", "check_container_app_health", "check_aks_cluster_health"]),
                (r"(diagnostic|logs).*",
                 ["get_diagnostic_logs", "search_logs_by_error"]),
            ],

            # Incident Response
            "incident": [
                (r"(incident|triage|investigate|troubleshoot)",
                 ["triage_incident", "generate_incident_summary"]),
                (r"(alert|correlate)",
                 ["correlate_alerts"]),
                (r"(postmortem|rca|root cause)",
                 ["generate_postmortem_template", "analyze_activity_log"]),
            ],

            # Performance
            "performance": [
                (r"(performance|metrics|cpu|memory|utilization)",
                 ["get_performance_metrics", "identify_bottlenecks"]),
                (r"(capacity|scale|sizing)",
                 ["get_capacity_recommendations", "compare_baseline_metrics"]),
            ],

            # Cost Optimization
            "cost": [
                (r"(cost|spending|budget|savings)",
                 ["get_cost_analysis", "get_cost_recommendations"]),
                (r"(orphaned|unused|idle|waste)",
                 ["identify_orphaned_resources", "analyze_idle_resources"]),
            ],

            # SLO Management
            "slo": [
                (r"(slo|service level|error budget)",
                 ["calculate_error_budget", "get_slo_dashboard"]),
                (r"(availability|uptime|reliability)",
                 ["define_slo", "calculate_error_budget"]),
            ],

            # Security & Compliance
            "security": [
                (r"(security|secure score|vulnerabilities)",
                 ["get_security_score", "list_security_recommendations"]),
                (r"(compliance|policy|cis|nist)",
                 ["check_compliance_status"]),
            ],

            # Remediation
            "remediation": [
                (r"(restart|reboot|fix)",
                 ["plan_remediation", "execute_safe_restart"]),
                (r"(scale|resize)",
                 ["scale_resource"]),
                (r"(cache|clear)",
                 ["clear_cache"]),
            ],

            # Configuration Discovery
            "config": [
                (r"(app service|web app).*config",
                 ["query_app_service_configuration"]),
                (r"(container app).*config",
                 ["query_container_app_configuration"]),
                (r"(aks|kubernetes).*config",
                 ["query_aks_configuration"]),
                (r"(apim|api management).*config",
                 ["query_apim_configuration"]),
            ],
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute orchestrator logic.

        Args:
            request: Request with 'query' or 'intent' field
            context: Optional workflow context

        Returns:
            Orchestrated result
        """
        query = request.get("query", request.get("intent", ""))
        workflow_id = request.get("workflow_id", uuid.uuid4().hex)

        logger.info(f"Orchestrating request: {query[:100]}...")

        # Create workflow context
        if self._context_store:
            await self._context_store.create_workflow_context(
                workflow_id,
                initial_data={"query": query, "request": request}
            )

        # Analyze intent and route
        intent_category, tools = self._analyze_intent(query)

        logger.info(
            f"Intent: {intent_category}, Tools: {[t[:30] for t in tools]}"
        )

        # Stream progress
        await self._stream_event("progress", {
            "workflow_id": workflow_id,
            "status": "routing",
            "intent": intent_category,
            "tools": tools
        })

        # Execute tools
        results = await self._execute_tools(
            tools,
            request,
            workflow_id
        )

        # Aggregate results
        aggregated = self._aggregate_results(results, intent_category)

        # Update workflow context
        if self._context_store:
            await self._context_store.update_workflow_context(
                workflow_id,
                {
                    "metadata": {
                        "status": "completed",
                        "intent": intent_category,
                        "tools_executed": len(results),
                        "user_interaction_required": aggregated.get("user_interaction_required", False)
                    }
                }
            )

        # Format response if successful results exist
        if aggregated.get("results") and not aggregated.get("user_interaction_required"):
            formatted_html = self.format_response(aggregated, intent_category)
            aggregated["formatted_response"] = formatted_html

        return {
            "workflow_id": workflow_id,
            "intent": intent_category,
            "tools_executed": len(results),
            "results": aggregated
        }

    def _analyze_intent(self, query: str) -> Tuple[str, List[str]]:
        """Analyze query intent and identify relevant tools.

        Args:
            query: User query string

        Returns:
            Tuple of (intent_category, list_of_tools)
        """
        query_lower = query.lower()

        # Try to match intent patterns
        for category, patterns in self._intent_patterns.items():
            for pattern, tools in patterns:
                if re.search(pattern, query_lower):
                    return category, tools

        # Default: Use general diagnostics
        return "general", ["describe_capabilities"]

    async def _execute_tools(
        self,
        tool_names: List[str],
        request: Dict[str, Any],
        workflow_id: str
    ) -> List[Dict[str, Any]]:
        """Execute multiple tools in parallel or sequence.

        Args:
            tool_names: List of tool names to execute
            request: Original request
            workflow_id: Workflow identifier

        Returns:
            List of tool results
        """
        results = []

        # For now, execute sequentially (can optimize for parallel later)
        for tool_name in tool_names:
            try:
                result = await self._execute_single_tool(
                    tool_name,
                    request,
                    workflow_id
                )
                results.append(result)

            except Exception as exc:
                logger.error(f"Tool {tool_name} failed: {exc}")
                results.append({
                    "tool": tool_name,
                    "status": "error",
                    "error": str(exc)
                })

        return results

    async def _execute_single_tool(
        self,
        tool_name: str,
        request: Dict[str, Any],
        workflow_id: str
    ) -> Dict[str, Any]:
        """Execute a single tool.

        Args:
            tool_name: Tool name
            request: Request data
            workflow_id: Workflow identifier

        Returns:
            Tool execution result
        """
        # Get tool info from registry
        tool_info = self.registry.get_tool(tool_name)

        if not tool_info:
            logger.warning(f"Tool {tool_name} not found in registry")
            return {
                "tool": tool_name,
                "status": "not_found",
                "error": f"Tool {tool_name} not registered"
            }

        agent_id = tool_info["agent_id"]

        # Stream progress
        await self._stream_event("progress", {
            "workflow_id": workflow_id,
            "status": "executing_tool",
            "tool": tool_name,
            "agent": agent_id
        })

        # Get agent
        agent = self.registry.get_agent(agent_id)

        if not agent:
            return {
                "tool": tool_name,
                "status": "error",
                "error": f"Agent {agent_id} not available"
            }

        # Prepare tool parameters
        parameters = await self._prepare_tool_parameters(
            tool_name,
            tool_info,
            request
        )

        # Check if user input is needed
        if isinstance(parameters, dict) and parameters.get("status") == "needs_user_input":
            logger.info(f"Tool {tool_name} requires user input")
            return {
                "tool": tool_name,
                "agent": agent_id,
                "status": "needs_user_input",
                "result": parameters
            }

        # Skip tool if required parameters cannot be satisfied
        if parameters is None:
            logger.info(f"Skipping {tool_name} - required parameters not available")
            return {
                "tool": tool_name,
                "agent": agent_id,
                "status": "skipped",
                "result": {
                    "success": False,
                    "message": "Tool requires parameters that are not available in current context"
                }
            }

        # Execute tool via agent
        tool_result = await agent.handle_request({
            "tool": tool_name,
            "parameters": parameters,
            **request
        })

        # Record in workflow context
        if self._context_store:
            await self._context_store.add_step_result(
                workflow_id,
                step_id=f"tool-{tool_name}",
                agent_id=agent_id,
                result=tool_result
            )

        return {
            "tool": tool_name,
            "agent": agent_id,
            "status": tool_result.get("status", "unknown"),
            "result": tool_result.get("result", tool_result)
        }

    async def _prepare_tool_parameters(
        self,
        tool_name: str,
        tool_info: Dict[str, Any],
        request: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Prepare parameters for tool execution.

        Merges parameters from:
        1. Request parameters
        2. Request context
        3. Environment defaults
        4. Discovers resources if needed
        5. Prompts user for ambiguous selections

        Args:
            tool_name: Name of the tool
            tool_info: Tool metadata from registry
            request: Original request

        Returns:
            Parameters dict, None if unavailable, or dict with "needs_user_input" status
        """
        import os

        # Start with request parameters
        parameters = dict(request.get("parameters", {}))

        # Merge context parameters
        context = request.get("context", {})
        parameters.update({
            k: v for k, v in context.items()
            if k not in parameters and v is not None
        })

        # Apply environment defaults
        if "subscription_id" not in parameters:
            sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
            if sub_id:
                parameters["subscription_id"] = sub_id

        if "workspace_id" not in parameters:
            ws_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID")
            if ws_id:
                parameters["workspace_id"] = ws_id

        # Check for ambiguous parameters and handle user interaction
        query = request.get("query", "")
        if query and self.interaction_handler:
            ambiguity_check = await self._check_and_handle_ambiguous_params(
                tool_name,
                parameters,
                query
            )

            if ambiguity_check:
                # Check if resource was auto-selected
                if ambiguity_check.get("auto_selected"):
                    resource = ambiguity_check.get("resource", {})
                    # Update parameters with auto-selected resource
                    if resource.get("id"):
                        parameters["resource_id"] = resource["id"]
                    if resource.get("name"):
                        parameters["resource_name"] = resource["name"]
                    if resource.get("resource_group"):
                        parameters["resource_group"] = resource["resource_group"]
                    logger.info(f"Auto-selected resource: {resource.get('name')}")
                else:
                    # User input needed - return special status
                    return ambiguity_check

        # Tool-specific parameter preparation
        tool_def = tool_info.get("definition", {}).get("function", {})
        required_params = self._get_required_parameters(tool_def)

        # For health check tools, try to discover resources if resource_id not provided
        if tool_name in ["check_resource_health", "check_container_app_health", "check_aks_cluster_health"]:
            if "resource_id" not in parameters:
                # Try to discover resources
                discovered = await self._discover_resources_for_tool(tool_name, parameters)
                if discovered:
                    # Use first discovered resource
                    parameters["resource_id"] = discovered[0]
                    logger.info(f"Discovered resource for {tool_name}: {discovered[0]}")
                else:
                    # Cannot execute without resource_id
                    logger.info(f"Cannot execute {tool_name} - no resource_id and discovery failed")
                    return None

        # Check if all required parameters are present
        missing = [p for p in required_params if p not in parameters]
        if missing:
            logger.info(f"Tool {tool_name} missing required params: {missing}")
            return None

        return parameters
    
    def _get_required_parameters(self, tool_def: Dict[str, Any]) -> List[str]:
        """Extract required parameters from tool definition.
        
        Args:
            tool_def: Tool function definition
            
        Returns:
            List of required parameter names
        """
        parameters = tool_def.get("parameters", {})
        if not parameters:
            return []
            
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])
        
        return required
    
    async def _discover_resources_for_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> List[str]:
        """Discover resources for a tool.
        
        Args:
            tool_name: Name of the tool
            parameters: Current parameters
            
        Returns:
            List of discovered resource IDs
        """
        # Map tools to resource discovery methods
        discovery_map = {
            "check_container_app_health": ("list", "Microsoft.App/containerApps"),
            "check_aks_cluster_health": ("list", "Microsoft.ContainerService/managedClusters"),
            "check_resource_health": ("list", "*")  # Generic resources
        }
        
        if tool_name not in discovery_map:
            return []
        
        # For now, return empty list - resource discovery will be enhanced in next phase
        # This allows the orchestrator to skip tools that need specific resources
        logger.info(f"Resource discovery for {tool_name} - not yet implemented")
        return []

    def _aggregate_results(
        self,
        results: List[Dict[str, Any]],
        intent_category: str
    ) -> Dict[str, Any]:
        """Aggregate results from multiple tools.

        Args:
            results: List of tool results
            intent_category: Intent category

        Returns:
            Aggregated results with user-friendly formatting
        """
        successful_results = [
            r for r in results
            if r.get("status") == "success"
        ]

        failed_results = [
            r for r in results
            if r.get("status") in ["error", "not_found"]
        ]

        skipped_results = [
            r for r in results
            if r.get("status") == "skipped"
        ]

        needs_input_results = [
            r for r in results
            if r.get("status") == "needs_user_input"
        ]

        # Build aggregated response
        aggregated = {
            "summary": {
                "total_tools": len(results),
                "successful": len(successful_results),
                "failed": len(failed_results),
                "skipped": len(skipped_results),
                "needs_input": len(needs_input_results),
                "intent": intent_category
            },
            "results": successful_results,
            "errors": failed_results if failed_results else None,
            "skipped": skipped_results if skipped_results else None,
            "needs_input": needs_input_results if needs_input_results else None,
        }

        # If user input is needed, prioritize that in the response
        if needs_input_results:
            # Return first user input request
            first_input_request = needs_input_results[0].get("result", {})
            aggregated["user_interaction_required"] = True
            aggregated["interaction_data"] = first_input_request
            aggregated["message"] = first_input_request.get("message", "User input required")
            return aggregated

        # Add helpful message if all tools were skipped
        if len(skipped_results) == len(results) and intent_category == "health":
            aggregated["message"] = self.formatter.format_error_message(
                "Health check tools require specific resource information.",
                suggestions=[
                    "Provide a resource name: 'Check health of container app my-app'",
                    "Specify a resource group: 'Check health in resource-group prod-rg'",
                    "List available resources first: 'List all container apps'"
                ]
            )

        # Add category-specific aggregation with friendly formatting
        if intent_category == "health":
            aggregated["health_summary"] = self._summarize_health(successful_results)
        elif intent_category == "cost":
            aggregated["cost_summary"] = self._summarize_cost(successful_results)
        elif intent_category == "performance":
            aggregated["performance_summary"] = self._summarize_performance(successful_results)

        return aggregated

    def _summarize_health(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize health check results.

        Args:
            results: Health check results

        Returns:
            Health summary
        """
        healthy_count = 0
        unhealthy_count = 0

        for result in results:
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                status = result_data.get("health_status", {}).get("availability_state", "")
                if status.lower() in ["available", "healthy"]:
                    healthy_count += 1
                else:
                    unhealthy_count += 1

        return {
            "healthy_resources": healthy_count,
            "unhealthy_resources": unhealthy_count,
            "total_checked": len(results)
        }

    def _summarize_cost(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize cost analysis results.

        Args:
            results: Cost analysis results

        Returns:
            Cost summary
        """
        total_savings_identified = 0.0
        orphaned_resources = 0

        for result in results:
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                total_savings_identified += result_data.get("potential_savings", 0.0)
                orphaned_resources += len(result_data.get("orphaned_resources", []))

        return {
            "potential_savings": f"${total_savings_identified:,.2f}",
            "orphaned_resources": orphaned_resources,
            "tools_analyzed": len(results)
        }

    def _summarize_performance(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize performance analysis results.

        Args:
            results: Performance results

        Returns:
            Performance summary
        """
        bottlenecks_found = 0
        capacity_recommendations = 0

        for result in results:
            result_data = result.get("result", {})
            if isinstance(result_data, dict):
                bottlenecks_found += len(result_data.get("bottlenecks", []))
                capacity_recommendations += len(result_data.get("recommendations", []))

        return {
            "bottlenecks_identified": bottlenecks_found,
            "capacity_recommendations": capacity_recommendations,
            "tools_analyzed": len(results)
        }

    async def route_to_specialist(
        self,
        specialist_type: str,
        request: Dict[str, Any],
        workflow_id: str
    ) -> Dict[str, Any]:
        """Route request to a specialist agent.

        Args:
            specialist_type: Type of specialist (e.g., "incident", "cost")
            request: Request data
            workflow_id: Workflow identifier

        Returns:
            Specialist agent result
        """
        # Get specialist agent
        specialist = self.registry.get_agent_by_type(specialist_type)

        if not specialist:
            logger.warning(f"Specialist agent {specialist_type} not available")
            return {
                "status": "error",
                "error": f"Specialist {specialist_type} not available"
            }

        # Send request via message bus
        try:
            response = await self.message_bus.send_request(
                from_agent=self.agent_id,
                to_agent=specialist.agent_id,
                request_type="execute",
                payload={
                    "request": request,
                    "workflow_id": workflow_id
                },
                timeout=60.0
            )

            return response

        except Exception as exc:
            logger.error(f"Failed to route to specialist {specialist_type}: {exc}")
            return {
                "status": "error",
                "error": str(exc)
            }

    def get_capabilities(self) -> Dict[str, Any]:
        """Get orchestrator capabilities.

        Returns:
            Capabilities summary
        """
        tools = self.registry.list_tools()
        agents = self.registry.list_agents()

        capabilities = {
            "orchestrator_version": "1.0.0",
            "total_tools": len(tools),
            "total_agents": len(agents),
            "categories": list(self._intent_patterns.keys()),
            "tools_by_category": {}
        }

        # Group tools by category
        for category, patterns in self._intent_patterns.items():
            category_tools = []
            for _, tools_list in patterns:
                category_tools.extend(tools_list)
            capabilities["tools_by_category"][category] = list(set(category_tools))

        return capabilities

    async def _execute_azure_cli(self, command: str) -> Dict[str, Any]:
        """Execute Azure CLI command via the azure_cli tool.

        Args:
            command: Azure CLI command to execute

        Returns:
            Command execution result
        """
        try:
            # Get the Azure CLI tool from registry
            cli_tool = self.registry.get_tool("azure_cli_execute_command")

            if not cli_tool:
                logger.error("Azure CLI tool not found in registry")
                return {
                    "status": "error",
                    "error": "Azure CLI tool not available"
                }

            agent_id = cli_tool["agent_id"]
            agent = self.registry.get_agent(agent_id)

            if not agent:
                logger.error(f"Agent {agent_id} not found")
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not available"
                }

            # Execute command
            result = await agent.handle_request({
                "tool": "azure_cli_execute_command",
                "parameters": {"command": command}
            })

            return result

        except Exception as exc:
            logger.error(f"Azure CLI execution failed: {exc}")
            return {
                "status": "error",
                "error": str(exc)
            }

    async def _check_and_handle_ambiguous_params(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        query: str
    ) -> Optional[Dict[str, Any]]:
        """Check if parameters are ambiguous and prompt user for selection.

        Args:
            tool_name: Name of the tool
            parameters: Current parameters
            query: Original user query

        Returns:
            Selection prompt dict or None if no ambiguity
        """
        if not self.interaction_handler:
            return None

        # Check if required parameters are missing
        missing_check = self.interaction_handler.check_required_params(
            tool_name,
            parameters
        )

        if missing_check:
            # Need to discover resources
            resource_type = self.interaction_handler.needs_resource_discovery(
                tool_name,
                parameters,
                query
            )

            if resource_type:
                # Discover resources
                resources = await self._discover_resources_by_type(
                    resource_type,
                    parameters
                )

                if resources:
                    # Multiple resources found - prompt user to select
                    if len(resources) > 1:
                        return self.interaction_handler.format_selection_prompt(
                            resources,
                            self._get_resource_type_label(resource_type),
                            action="use for this operation"
                        )
                    # Single resource found - use it automatically
                    elif len(resources) == 1:
                        await self._stream_event("info", {
                            "message": f"Found {self._get_resource_type_label(resource_type)}: {resources[0].get('name')}"
                        })
                        return {
                            "auto_selected": True,
                            "resource": resources[0]
                        }

            # Return missing params message
            return missing_check

        return None

    async def _discover_resources_by_type(
        self,
        resource_type: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Discover resources by type.

        Args:
            resource_type: Type of resource to discover
            context: Context parameters (resource_group, subscription, etc.)

        Returns:
            List of discovered resources
        """
        if not self.interaction_handler:
            return []

        resource_group = context.get("resource_group")
        name_filter = context.get("name_filter")

        try:
            if resource_type == "container_app":
                return await self.interaction_handler.discover_container_apps(
                    resource_group, name_filter
                )
            elif resource_type == "vm":
                return await self.interaction_handler.discover_virtual_machines(
                    resource_group, name_filter
                )
            elif resource_type == "resource_group":
                subscription_id = context.get("subscription_id")
                return await self.interaction_handler.discover_resource_groups(
                    subscription_id
                )
            elif resource_type == "workspace":
                return await self.interaction_handler.discover_log_analytics_workspaces(
                    resource_group
                )
            else:
                logger.warning(f"Unknown resource type for discovery: {resource_type}")
                return []

        except Exception as exc:
            logger.error(f"Resource discovery failed for {resource_type}: {exc}")
            return []

    def _get_resource_type_label(self, resource_type: str) -> str:
        """Get user-friendly label for a resource type.

        Args:
            resource_type: Resource type key

        Returns:
            Human-readable label
        """
        labels = {
            "container_app": "Container App",
            "vm": "Virtual Machine",
            "resource_group": "Resource Group",
            "workspace": "Log Analytics Workspace",
        }
        return labels.get(resource_type, resource_type.replace("_", " ").title())

    def format_response(
        self,
        aggregated_results: Dict[str, Any],
        intent_category: str
    ) -> str:
        """Format aggregated results into user-friendly HTML.

        Args:
            aggregated_results: Aggregated tool results
            intent_category: Intent category

        Returns:
            HTML-formatted response
        """
        html_parts = []

        # Add summary header
        summary = aggregated_results.get("summary", {})
        successful = summary.get("successful", 0)
        total = summary.get("total_tools", 0)

        if successful > 0:
            html_parts.append(
                f"<h3>✅ Operation Complete</h3>"
                f"<p>Successfully executed {successful} out of {total} operations.</p>"
            )
        else:
            html_parts.append(
                f"<h3>ℹ️ Results</h3>"
                f"<p>Processed {total} operation(s).</p>"
            )

        # Format individual results
        results = aggregated_results.get("results", [])
        for result in results:
            tool_name = result.get("tool", "Unknown Tool")
            tool_result = result.get("result", {})

            html_parts.append(f"<hr>")
            formatted = format_tool_result(tool_name, tool_result)
            html_parts.append(formatted)

        # Add category-specific summaries
        if intent_category == "health":
            health_summary = aggregated_results.get("health_summary", {})
            if health_summary:
                html_parts.append("<hr>")
                html_parts.append(
                    f"<h4>📊 Health Summary</h4>"
                    f"<p><strong>Healthy Resources:</strong> {health_summary.get('healthy_resources', 0)}</p>"
                    f"<p><strong>Unhealthy Resources:</strong> {health_summary.get('unhealthy_resources', 0)}</p>"
                )

        elif intent_category == "cost":
            cost_summary = aggregated_results.get("cost_summary", {})
            if cost_summary:
                html_parts.append("<hr>")
                html_parts.append(
                    f"<h4>💰 Cost Summary</h4>"
                    f"<p><strong>Potential Savings:</strong> {cost_summary.get('potential_savings', '$0.00')}</p>"
                    f"<p><strong>Orphaned Resources:</strong> {cost_summary.get('orphaned_resources', 0)}</p>"
                )

        # Add helpful message if all tools were skipped
        message = aggregated_results.get("message")
        if message:
            html_parts.append(
                f"<div class='alert alert-info'>"
                f"<p><strong>💡 Tip:</strong> {message}</p>"
                f"</div>"
            )

        return "\n".join(html_parts)
