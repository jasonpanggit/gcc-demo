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
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.agent_message_bus import get_message_bus
    from utils.logger import get_logger


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

        # Intent patterns for routing
        self._intent_patterns = self._build_intent_patterns()

    async def _initialize_impl(self) -> None:
        """Initialize orchestrator-specific resources."""
        # Initialize context store
        self._context_store = await get_context_store()

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
                        "tools_executed": len(results)
                    }
                }
            )

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

        # Execute tool via agent
        tool_result = await agent.handle_request({
            "tool": tool_name,
            "parameters": request.get("parameters", {}),
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
            Aggregated results
        """
        successful_results = [
            r for r in results
            if r.get("status") == "success"
        ]

        failed_results = [
            r for r in results
            if r.get("status") in ["error", "not_found"]
        ]

        # Build aggregated response
        aggregated = {
            "summary": {
                "total_tools": len(results),
                "successful": len(successful_results),
                "failed": len(failed_results),
                "intent": intent_category
            },
            "results": successful_results,
            "errors": failed_results if failed_results else None
        }

        # Add category-specific aggregation
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
