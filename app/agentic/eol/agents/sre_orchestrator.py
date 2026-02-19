"""SRE Orchestrator Agent - Coordinates all SRE operations.

The orchestrator routes requests to appropriate tools and agents,
manages multi-tool workflows, and aggregates results.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.agent_context_store import get_context_store
    from app.agentic.eol.utils.agent_message_bus import get_message_bus
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.azure_cli_executor import get_azure_cli_executor
    from app.agentic.eol.utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from app.agentic.eol.utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
    from app.agentic.eol.utils.sre_inventory_integration import get_sre_inventory_integration  
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.agent_message_bus import get_message_bus
    from utils.logger import get_logger
    from utils.azure_cli_executor import get_azure_cli_executor
    from utils.sre_response_formatter import (
        SREResponseFormatter,
        format_tool_result,
    )
    from utils.sre_interaction_handler import (
        SREInteractionHandler,
        get_interaction_handler,
    )
    from utils.sre_inventory_integration import get_sre_inventory_integration


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

        # Resource discovery cache (in-memory, short TTL)
        self.resource_cache: Dict[str, Any] = {}
        self.resource_cache_ttl = 300  # 5 minutes

    async def _initialize_impl(self) -> None:
        """Initialize orchestrator-specific resources."""
        # Initialize context store
        self._context_store = await get_context_store()

        # Initialize interaction handler with Azure CLI executor
        self.interaction_handler = get_interaction_handler(
            azure_cli_executor=self._execute_azure_cli
        )

        # Resource inventory integration
        # Use strict_mode=True to ensure resources not found in inventory are blocked
        # This prevents expensive API calls to non-existent resources
        try:
            strict_inventory_mode = os.environ.get("SRE_INVENTORY_STRICT_MODE", "true").lower() == "true"
            self.inventory_integration = get_sre_inventory_integration(strict_mode=strict_inventory_mode)
            logger.info(f"SRE orchestrator inventory integration initialized (strict_mode={strict_inventory_mode})")
        except Exception as e:
            logger.warning(f"Inventory integration not available: {e}")
            self.inventory_integration = None

            
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
                # Container Apps - specific pattern first
                (r"(check|health|status).*container\s*app",
                 ["check_container_app_health"]),
                # AKS/Kubernetes - specific pattern
                (r"(check|health|status).*(aks|kubernetes|k8s|cluster)",
                 ["check_aks_cluster_health"]),
                # Generic resources (VMs, App Services, etc.)
                (r"(check|health|status).*(vm|virtual\s*machine|app\s*service|sql|storage|load\s*balancer)",
                 ["check_resource_health"]),
                # Diagnostic logs
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

        logger.info(f"Tool execution complete: {len(results)} results")
        for i, res in enumerate(results):
            logger.info(f"  Result {i}: status={res.get('status')}, tool={res.get('tool')}")

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
        logger.info(f"Aggregated results: {len(aggregated.get('results', []))} items, has formatted_response check: {bool(aggregated.get('results')  and not aggregated.get('user_interaction_required'))}")
        
        if aggregated.get("results") and not aggregated.get("user_interaction_required"):
            formatted_html = self.format_response(aggregated, intent_category)
            aggregated["formatted_response"] = formatted_html
            logger.info(f"Generated formatted_response: {len(formatted_html)} chars")

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

        # Preflight resource check (after parameters are prepared)
        if self.inventory_integration and parameters:
            try:
                preflight = await self.inventory_integration.preflight_resource_check(
                    tool_name, parameters
                )
                # Check the correct key - it's "ok" not "passed"
                if not preflight.get("ok", True):
                    # Resource not found in inventory - return immediately without calling tool
                    error_msg = preflight.get("result", {}).get("error", "Preflight check failed")
                    suggestion = preflight.get("result", {}).get("suggestion", "")

                    logger.info(f"Preflight check failed for {tool_name}: {error_msg}")

                    return {
                        "tool": tool_name,
                        "agent": agent_id,
                        "status": "not_found",
                        "result": {
                            "success": False,
                            "error": error_msg,
                            "suggestion": suggestion,
                            "preflight_failed": True,
                            "message": f"Resource not found in inventory. {suggestion}" if suggestion else "Resource not found in inventory."
                        }
                    }
                # Log warning if present
                if "warning" in preflight:
                    logger.warning(f"Preflight warning: {preflight['warning']}")
            except Exception as e:
                logger.warning(f"Preflight check failed: {e}")
                # Don't block on inventory errors - continue to tool execution

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

        # Enrich error messages with diagnostic information
        if tool_name in ["get_performance_metrics", "identify_bottlenecks"]:
            # BaseSREAgent wraps execute output under "result"
            wrapped_result = tool_result.get("result", {}) if isinstance(tool_result, dict) else {}
            parsed_result = wrapped_result.get("parsed", {}) if isinstance(wrapped_result, dict) else {}
            metrics = []

            if isinstance(parsed_result, dict):
                metrics = parsed_result.get("metrics", []) or []
            if not metrics and isinstance(wrapped_result, dict):
                metrics = wrapped_result.get("metrics", []) or []

            if not metrics:
                resource_id = parameters.get("resource_id", "")
                diagnostic_info = await self._diagnose_no_metrics(resource_id, tool_result)
                tool_result["diagnostic_info"] = diagnostic_info

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
            "status": "success" if tool_result.get("success") else tool_result.get("status", "error"),
            "inventory_integration": {
                "enabled": self.inventory_integration is not None,
                "statistics": self.inventory_integration.get_statistics() if self.inventory_integration else None
            },
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

        # Resolve/validate scope-based tools (Cost, Compliance, etc.)
        # These tools require ARM scope paths such as:
        # /subscriptions/{id} or /subscriptions/{id}/resourceGroups/{rg}
        if self._tool_requires_scope(tool_name):
            normalized_scope = self._normalize_scope(
                parameters.get("scope"),
                parameters.get("subscription_id"),
            )
            if normalized_scope:
                parameters["scope"] = normalized_scope
            else:
                logger.info(
                    "Cannot execute %s - missing valid scope (expected /subscriptions/{id} or /subscriptions/{id}/resourceGroups/{rg})",
                    tool_name,
                )
                return None

        # Check for ambiguous parameters and handle user interaction
        # Only do this in streaming/interactive mode
        query = request.get("query", "")
        stream_enabled = request.get("stream", False)
        
        if query and self.interaction_handler and stream_enabled:
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

        # For health check and performance tools, try to discover resources if resource_id not provided
        if tool_name in [
            "check_resource_health", "check_container_app_health", "check_aks_cluster_health",
            "get_performance_metrics", "identify_bottlenecks", "get_capacity_recommendations",
            "compare_baseline_metrics"
        ]:
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

        # Enrich with inventory
        if self.inventory_integration:
            try:
                parameters = await self.inventory_integration.enrich_tool_parameters(
                    tool_name, parameters, context
                )
            except Exception as e:
                logger.warning(f"Parameter enrichment failed: {e}")

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

    def _tool_requires_scope(self, tool_name: str) -> bool:
        """Return True when the tool requires an ARM scope parameter."""
        return tool_name in {
            "get_cost_analysis",
            "analyze_cost_anomalies",
            "check_compliance_status",
        }

    def _normalize_scope(
        self,
        scope_value: Optional[Any],
        subscription_id: Optional[Any],
    ) -> Optional[str]:
        """Normalize scope to an ARM path.

        Accepted inputs:
        - '/subscriptions/{id}'
        - '/subscriptions/{id}/resourceGroups/{rg}'
        - raw subscription GUID (converted to '/subscriptions/{id}')
        """
        raw_scope = str(scope_value).strip() if scope_value else ""
        raw_subscription = str(subscription_id).strip() if subscription_id else ""

        candidate = raw_scope or raw_subscription
        if not candidate:
            return None

        if candidate.startswith("/subscriptions/"):
            return candidate

        if candidate.startswith("subscriptions/"):
            return f"/{candidate}"

        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", candidate):
            return f"/subscriptions/{candidate}"

        return None
    
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
        # Check cache first
        subscription_id = parameters.get("subscription_id", "default")
        resource_group = parameters.get("resource_group", "all")
        cache_key = f"{tool_name}_{subscription_id}_{resource_group}"
        
        if cache_key in self.resource_cache:
            cache_entry = self.resource_cache[cache_key]
            now = datetime.now(timezone.utc)
            if now - cache_entry["timestamp"] < timedelta(seconds=self.resource_cache_ttl):
                logger.info(f"Cache hit for {tool_name} ({len(cache_entry['data'])} resources)")
                return cache_entry["data"]
        
        # Map tools to Azure CLI commands
        discovery_map = {
            "check_container_app_health": self._discover_container_apps,
            "check_aks_cluster_health": self._discover_aks_clusters,
            "check_resource_health": self._discover_generic_resources,
            "get_performance_metrics": self._discover_vms,
            "identify_bottlenecks": self._discover_vms,
            "get_capacity_recommendations": self._discover_vms,
            "compare_baseline_metrics": self._discover_vms
        }
        
        if tool_name not in discovery_map:
            return []
        
        try:
            discovery_func = discovery_map[tool_name]
            resources = await discovery_func(parameters)
            
            if resources:
                logger.info(f"Discovered {len(resources)} resources for {tool_name}")
                
                # Cache the result
                self.resource_cache[cache_key] = {
                    "data": resources,
                    "timestamp": datetime.now(timezone.utc)
                }
                
                return resources
            else:
                logger.info(f"No resources found for {tool_name}")
                return []
                
        except Exception as exc:
            logger.error(f"Resource discovery failed for {tool_name}: {exc}")
            return []
    
    async def _discover_container_apps(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover Container Apps.
        
        Args:
            parameters: Current parameters (may contain resource_group, subscription_id)
            
        Returns:
            List of Container App resource IDs
        """
        resource_group = parameters.get("resource_group")
        subscription_id = parameters.get("subscription_id")
        
        # Build command
        if resource_group:
            command = f'az containerapp list --resource-group {resource_group} --query "[].id" -o json'
        else:
            command = 'az containerapp list --query "[].id" -o json'
            
        result = await self._execute_azure_cli(command)
        
        if result.get("status") == "success":
            output = result.get("output", [])
            if isinstance(output, list):
                return output
        
        return []
    
    async def _discover_aks_clusters(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover AKS clusters.
        
        Args:
            parameters: Current parameters
            
        Returns:
            List of AKS cluster resource IDs
        """
        resource_group = parameters.get("resource_group")
        
        if resource_group:
            command = f'az aks list --resource-group {resource_group} --query "[].id" -o json'
        else:
            command = 'az aks list --query "[].id" -o json'
            
        result = await self._execute_azure_cli(command)
        
        if result.get("status") == "success":
            output = result.get("output", [])
            if isinstance(output, list):
                return output
        
        return []
    
    async def _discover_generic_resources(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover generic Azure resources.
        
        Args:
            parameters: Current parameters
            
        Returns:
            List of resource IDs (limited to common resource types)
        """
        # For generic resources, only discover common types that support Resource Health API
        # VMs, App Services, SQL DBs, Storage Accounts, Load Balancers
        resource_types = [
            "Microsoft.Compute/virtualMachines",
            "Microsoft.Web/sites",
            "Microsoft.Sql/servers/databases",
            "Microsoft.Storage/storageAccounts",
            "Microsoft.Network/loadBalancers"
        ]
        
        resource_group = parameters.get("resource_group")
        all_resources = []
        
        for resource_type in resource_types:
            if resource_group:
                command = f'az resource list --resource-group {resource_group} --resource-type {resource_type} --query "[].id" -o json'
            else:
                command = f'az resource list --resource-type {resource_type} --query "[].id" -o json'
            
            result = await self._execute_azure_cli(command)
            
            if result.get("status") == "success":
                output = result.get("output", [])
                if isinstance(output, list):
                    all_resources.extend(output)
                    
        return all_resources[:10]  # Limit to 10 resources to avoid overwhelming the user
    
    async def _discover_vms(self, parameters: Dict[str, Any]) -> List[str]:
        """Discover Virtual Machines for performance analysis.
        
        Args:
            parameters: Current parameters (may contain resource_group, subscription_id)
            
        Returns:
            List of VM resource IDs
        """
        resource_group = parameters.get("resource_group")
        
        # Build command to discover VMs
        if resource_group:
            command = f'az vm list --resource-group {resource_group} --query "[].id" -o json'
        else:
            command = 'az vm list --query "[].id" -o json'
            
        result = await self._execute_azure_cli(command)
        
        if result.get("status") == "success":
            output = result.get("output", [])
            if isinstance(output, list):
                return output[:10]  # Limit to 10 VMs
        
        return []
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

        # Add helpful message if resources not found in inventory
        not_found_results = [
            r for r in failed_results
            if r.get("result", {}).get("preflight_failed", False)
        ]

        if not_found_results and len(not_found_results) == len(results):
            # All tools failed preflight - resources not in inventory
            resource_ids = [
                r.get("result", {}).get("error", "unknown")
                for r in not_found_results
            ]

            aggregated["message"] = self.formatter.format_error_message(
                "❌ Resources not found in inventory.",
                suggestions=[
                    "Verify the resource exists in the Azure subscription",
                    "Check that resource discovery is running (inventory may be out of sync)",
                    "Provide the full resource ID if the resource was recently created",
                    "Run 'list all resources' to see available resources in inventory"
                ]
            )
            # Don't proceed with other formatting if all resources not found
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
            perf_summary = self._summarize_performance(successful_results)
            aggregated["performance_summary"] = perf_summary

            # Add friendly message if no performance data found
            if not perf_summary.get("has_data", False) and len(successful_results) > 0:
                # Check if we have diagnostic information from any result
                diagnostic_details = []
                for result in successful_results:
                    if "diagnostic_info" in result:
                        diag = result["diagnostic_info"]
                        if diag.get("issues_found"):
                            diagnostic_details.extend(diag["issues_found"])

                # Build friendly message with diagnostics
                if diagnostic_details:
                    issues_html = "<br>".join([f"• {issue}" for issue in diagnostic_details[:3]])
                    aggregated["message"] = (
                        f"⚠️ No performance metrics found. <strong>Issues detected:</strong><br>"
                        f"{issues_html}<br><br>"
                    )

                    # Add recommendations from diagnostics
                    recommendations = []
                    for result in successful_results:
                        if "diagnostic_info" in result:
                            diag = result["diagnostic_info"]
                            recommendations.extend(diag.get("recommendations", []))

                    if recommendations:
                        rec_html = "<br>".join([f"• {rec}" for rec in recommendations[:5]])
                        aggregated["message"] += (
                            f"<strong>💡 Recommendations:</strong><br>{rec_html}"
                        )
                else:
                    # Generic message if no specific diagnostics available
                    aggregated["message"] = (
                        "⚠️ No performance metrics found for the specified resources. "
                        "This could be because:<br>"
                        "• The VM or resource is stopped/deallocated<br>"
                        "• Monitoring agent is not installed or configured<br>"
                        "• Metrics collection hasn't started yet (wait 3-5 minutes after starting)<br>"
                        "• The resource doesn't support the requested metrics<br><br>"
                        "💡 <strong>Tip:</strong> Ensure resources are running and have Azure Monitor configured."
                    )

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
        unhealthy_details: List[Dict[str, Any]] = []

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue

            parsed_data = result_data.get("parsed", {})
            if not isinstance(parsed_data, dict):
                parsed_data = {}

            health_data = (
                parsed_data.get("health_data")
                or result_data.get("health_status")
                or result_data.get("health_data")
                or {}
            )
            if not isinstance(health_data, dict):
                health_data = {}

            status = (
                health_data.get("availability_state")
                or health_data.get("health_status")
                or parsed_data.get("availability_state")
                or "unknown"
            )

            resource_id = parsed_data.get("resource_id", "")
            resource_name = (
                parsed_data.get("container_app_name")
                or parsed_data.get("resource_name")
                or (resource_id.split("/")[-1] if resource_id else "Unknown Resource")
            )

            if str(status).lower() in ["available", "healthy"]:
                healthy_count += 1
                continue

            unhealthy_count += 1
            reason = (
                health_data.get("reason_type")
                or health_data.get("summary")
                or parsed_data.get("note")
                or "No additional diagnostic details provided"
            )
            recent_errors = health_data.get("recent_errors") or []
            recent_error = recent_errors[0] if isinstance(recent_errors, list) and recent_errors else ""

            unhealthy_details.append({
                "resource_name": str(resource_name),
                "status": str(status),
                "reason": str(reason),
                "recent_error": str(recent_error) if recent_error else "",
            })

        return {
            "healthy_resources": healthy_count,
            "unhealthy_resources": unhealthy_count,
            "total_checked": len(results),
            "unhealthy_details": unhealthy_details,
        }

    def _summarize_cost(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize cost analysis results.

        Args:
            results: Cost analysis results

        Returns:
            Cost summary
        """
        def _to_float(value: Any) -> float:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip()
            if not text or text.upper() == "N/A":
                return 0.0
            text = text.replace(",", "")
            try:
                return float(text)
            except ValueError:
                return 0.0

        total_savings_identified = 0.0
        orphaned_resources = 0

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue

            parsed_data = result_data.get("parsed", {})
            if not isinstance(parsed_data, dict):
                parsed_data = {}

            payload = parsed_data or result_data

            # Direct potential_savings from analysis tools
            total_savings_identified += _to_float(payload.get("potential_savings", 0.0))

            # Include savings from recommendation entries (Azure Advisor often provides annual values)
            recommendations = payload.get("recommendations", [])
            if isinstance(recommendations, list):
                for rec in recommendations:
                    if not isinstance(rec, dict):
                        continue

                    monthly = _to_float(
                        rec.get("monthly_savings_amount")
                        or rec.get("monthly_savings")
                        or rec.get("estimated_monthly_savings")
                    )
                    if monthly > 0:
                        total_savings_identified += monthly
                        continue

                    annual = _to_float(rec.get("savings_amount") or rec.get("annual_savings_amount"))
                    if annual > 0:
                        total_savings_identified += annual / 12.0

            # Orphaned resources summary
            total_orphaned = payload.get("total_orphaned_resources")
            if isinstance(total_orphaned, int):
                orphaned_resources += total_orphaned
            else:
                orphaned = payload.get("orphaned_resources", {})
                if isinstance(orphaned, dict):
                    orphaned_resources += sum(
                        int(v.get("count", 0)) for v in orphaned.values() if isinstance(v, dict)
                    )
                elif isinstance(orphaned, list):
                    orphaned_resources += len(orphaned)

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
        metrics_count = 0
        has_data = False

        for result in results:
            result_data = result.get("result", {})
            if not isinstance(result_data, dict):
                continue

            # SRE MCP client stores structured payload under "parsed"
            parsed_data = result_data.get("parsed", {})
            if not isinstance(parsed_data, dict):
                parsed_data = {}

            bottlenecks = parsed_data.get("bottlenecks_found") or result_data.get("bottlenecks") or []
            recommendations = parsed_data.get("recommendations") or result_data.get("recommendations") or []
            metrics = parsed_data.get("metrics") or result_data.get("metrics") or []

            bottlenecks_found += len(bottlenecks)
            capacity_recommendations += len(recommendations)
            if metrics:
                metrics_count += len(metrics)
                has_data = True

        return {
            "bottlenecks_identified": bottlenecks_found,
            "capacity_recommendations": capacity_recommendations,
            "metrics_count": metrics_count,
            "has_data": has_data,
            "tools_analyzed": len(results)
        }

    async def _diagnose_no_metrics(self, resource_id: str, tool_result: Dict[str, Any]) -> Dict[str, Any]:
        """Diagnose why there are no metrics for a resource.

        Args:
            resource_id: Azure resource ID
            tool_result: The tool result that returned empty metrics (unused but kept for signature)

        Returns:
            Dictionary with diagnostic information and recommendations
        """
        diagnostics = {
            "issues_found": [],
            "recommendations": []
        }

        if not resource_id:
            diagnostics["issues_found"].append("No resource ID provided")
            diagnostics["recommendations"].append("Specify a resource ID to diagnose")
            return diagnostics

        # Extract resource name and type from resource_id
        resource_name = resource_id.split('/')[-1]
        resource_type = "VM" if "/virtualMachines/" in resource_id else "resource"

        # Parse resource group from resource_id
        resource_group = "unknown"
        try:
            parts = resource_id.split('/')
            rg_index = parts.index('resourceGroups') + 1
            resource_group = parts[rg_index]
        except (ValueError, IndexError):
            logger.warning(f"Could not parse resource group from: {resource_id}")

        # Check if this is a VM - we can check power state using registered SRE MCP proxy agent
        if "/virtualMachines/" in resource_id:
            try:
                proxy_agent = self.registry.get_agent("sre-mcp-server")
                if not proxy_agent:
                    raise RuntimeError("SRE MCP proxy agent not available")

                # Use get_resource_health tool to check VM state
                health_result = await proxy_agent.handle_request({
                    "tool": "get_resource_health",
                    "parameters": {"resource_id": resource_id}
                })

                if health_result.get("status") == "success":
                    # BaseSREAgent wraps execute output under "result"
                    result_wrapper = health_result.get("result", {})
                    health_data = result_wrapper.get("result", result_wrapper) if isinstance(result_wrapper, dict) else {}
                    availability_state = health_data.get("availability_state", "unknown")

                    # Check if VM is unavailable/stopped
                    if availability_state.lower() in ["unavailable", "degraded"]:
                        reason = health_data.get("reason_type", "")
                        diagnostics["issues_found"].append(
                            f"VM '{resource_name}' is {availability_state}: {reason}"
                        )
                        if resource_group != "unknown":
                            diagnostics["recommendations"].append(
                                f"Start the VM: <code>az vm start -g {resource_group} -n {resource_name}</code>"
                            )
                        diagnostics["recommendations"].append(
                            "Wait 3-5 minutes after starting for metrics to populate in Azure Monitor"
                        )
                        return diagnostics

            except Exception as e:
                logger.debug(f"Could not check resource health: {e}")
                # Continue to other checks

        # Generic diagnostics for all resources
        diagnostics["issues_found"].append(
            f"No metrics data available for {resource_type} '{resource_name}'"
        )

        # Provide actionable recommendations
        diagnostics["recommendations"].append(
            "✓ Verify the resource is running and operational"
        )
        diagnostics["recommendations"].append(
            "✓ Check if Azure Monitor diagnostic settings are configured"
        )

        if resource_type == "VM":
            diagnostics["recommendations"].append(
                "✓ Ensure Azure Monitor agent or diagnostic extension is installed"
            )
            if resource_group != "unknown":
                diagnostics["recommendations"].append(
                    f"Check VM status: <code>az vm get-instance-view -g {resource_group} -n {resource_name}</code>"
                )

        diagnostics["recommendations"].append(
            "✓ Allow 3-5 minutes for metrics to populate after resource starts"
        )

        diagnostics["recommendations"].append(
            f"Check diagnostic settings: <code>az monitor diagnostic-settings list --resource {resource_id}</code>"
        )

        return diagnostics

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
        """Execute Azure CLI command using singleton executor.

        Args:
            command: Azure CLI command to execute

        Returns:
            Command execution result
        """
        try:
            executor = await get_azure_cli_executor()
            return await executor.execute(command, timeout=30, add_subscription=True)
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

                unhealthy_details = health_summary.get("unhealthy_details", [])
                if unhealthy_details:
                    html_parts.append("<p><strong>🔎 Unhealthy Resource Details:</strong></p><ul>")
                    for detail in unhealthy_details:
                        name = html.escape(detail.get("resource_name", "Unknown Resource"))
                        status = html.escape(detail.get("status", "Unknown"))
                        reason = html.escape(detail.get("reason", ""))
                        recent_error = html.escape(detail.get("recent_error", ""))

                        html_parts.append(f"<li><strong>{name}</strong> — Status: {status}<br>Reason: {reason}")
                        if recent_error:
                            html_parts.append(f"<br>Recent error: {recent_error}")
                        html_parts.append("</li>")
                    html_parts.append("</ul>")

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
