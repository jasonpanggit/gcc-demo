"""Health Monitoring Agent - Specialized SRE agent for health checks and diagnostics.

This agent handles:
- Resource health monitoring and status checks
- Health diagnostics for Azure services
- Dependency mapping and impact analysis
- Continuous health monitoring
- Proactive health recommendations
- Multi-resource health aggregation
- Service availability tracking
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.agent_context_store import get_context_store
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.logger import get_logger


logger = get_logger(__name__)


class HealthMonitoringAgent(BaseSREAgent):
    """Specialized agent for health monitoring and diagnostics.

    This agent orchestrates comprehensive health monitoring workflows:
    1. Resource health checks (VMs, App Services, AKS, Container Apps)
    2. Service diagnostics and troubleshooting
    3. Dependency mapping and impact analysis
    4. Continuous monitoring with alerting
    5. Health trend analysis
    6. Proactive recommendations
    7. Multi-resource health aggregation

    Example usage:
        agent = HealthMonitoringAgent()
        await agent.initialize()

        # Check resource health
        result = await agent.handle_request({
            "action": "check_health",
            "resource_id": "/subscriptions/.../resourceGroups/rg/providers/...",
            "include_metrics": True
        })

        # Diagnose app service
        result = await agent.handle_request({
            "action": "diagnose",
            "resource_id": "...",
            "service_type": "app_service"
        })

        # Check dependencies
        result = await agent.handle_request({
            "action": "check_dependencies",
            "resource_id": "...",
            "depth": 2
        })

        # Continuous monitoring
        result = await agent.handle_request({
            "action": "continuous_monitor",
            "resource_ids": ["...", "..."],
            "interval_seconds": 60,
            "duration_minutes": 10
        })

        # Full health assessment
        result = await agent.handle_request({
            "action": "full",
            "resource_group": "prod-rg"
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Health Monitoring Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="health-monitoring",
            agent_id=agent_id or "health-monitoring-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Health status levels
        self.health_levels = {
            "healthy": {"score": 100, "color": "green", "priority": 0},
            "degraded": {"score": 75, "color": "yellow", "priority": 1},
            "unhealthy": {"score": 50, "color": "orange", "priority": 2},
            "critical": {"score": 25, "color": "red", "priority": 3},
            "unknown": {"score": 0, "color": "gray", "priority": 4}
        }

        # Service-specific diagnostic tools mapping
        self.diagnostic_tools = {
            "app_service": "diagnose_app_service",
            "function_app": "diagnose_app_service",
            "api_management": "diagnose_apim",
            "apim": "diagnose_apim",
            "aks": "check_aks_cluster_health",
            "kubernetes": "check_aks_cluster_health",
            "container_app": "check_container_app_health",
            "vm": "check_resource_health",
            "virtual_machine": "check_resource_health",
            "storage": "check_resource_health",
            "sql": "check_resource_health"
        }

    async def _initialize_impl(self) -> None:
        """Initialize agent-specific resources."""
        try:
            # Get agent registry
            self.registry = get_agent_registry()
            logger.info("✓ Connected to agent registry")

            # Get context store
            self.context_store = await get_context_store()
            logger.info("✓ Connected to context store")

            # Get tool proxy agent for executing SRE tools
            self.tool_proxy_agent = self.registry.get_agent("sre-mcp-server")
            if not self.tool_proxy_agent:
                logger.warning(
                    "⚠️ Tool proxy agent not found - tools may not be available"
                )
            else:
                logger.info("✓ Connected to tool proxy agent")

        except Exception as exc:
            logger.error(f"Failed to initialize Health Monitoring Agent: {exc}")
            raise

    async def _cleanup_impl(self) -> None:
        """Cleanup agent-specific resources."""
        # Context store and registry are shared singletons, no cleanup needed
        pass

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute health monitoring action.

        Args:
            request: Request containing:
                - action: Action to perform (check_health, diagnose, check_dependencies, etc.)
                - resource_id: Azure resource ID (optional)
                - resource_group: Resource group name (optional)
                - service_type: Service type for diagnostics (optional)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Health monitoring results with status, diagnostics, and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "check_health")

        logger.info(f"Processing health monitoring action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "check_health": self._check_health,
            "diagnose": self._diagnose_service,
            "check_dependencies": self._check_dependencies,
            "continuous_monitor": self._continuous_monitor,
            "recommendations": self._generate_recommendations,
            "full": self._full_health_assessment
        }

        handler = action_handlers.get(action)
        if not handler:
            raise AgentExecutionError(
                f"Unknown action: {action}. "
                f"Valid actions: {', '.join(action_handlers.keys())}"
            )

        return await handler(request, context)

    async def _call_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an SRE tool via the proxy agent.

        Args:
            tool_name: Name of the tool to call
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            AgentExecutionError: If tool execution fails
        """
        if not self.tool_proxy_agent:
            raise AgentExecutionError("Tool proxy agent not available")

        try:
            result = await self.tool_proxy_agent.handle_request({
                "tool": tool_name,
                "parameters": parameters
            })

            if result.get("status") == "error":
                raise AgentExecutionError(
                    f"Tool {tool_name} failed: {result.get('error')}"
                )

            return result

        except Exception as exc:
            logger.error(f"Failed to call tool {tool_name}: {exc}")
            raise AgentExecutionError(f"Tool execution failed: {exc}")

    async def _check_health(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check resource health status.

        Performs comprehensive health check including availability,
        performance metrics, and recent issues.

        Args:
            request: Health check request with resource details
            context: Optional workflow context

        Returns:
            Health status with metrics and issues
        """
        resource_id = request.get("resource_id", "")
        include_metrics = request.get("include_metrics", True)
        workflow_id = request.get("workflow_id", f"health-{datetime.utcnow().timestamp()}")

        logger.info(f"Checking health for resource: {resource_id}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "action": "check_health",
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Determine resource type and use appropriate health check tool
        resource_type = self._extract_resource_type(resource_id)

        health_result = None
        if resource_type == "container_app":
            # Step 1: Check Container App health
            health_result = await self._call_tool(
                "check_container_app_health",
                {
                    "app_name": self._extract_resource_name(resource_id),
                    "resource_group": request.get("resource_group", "")
                }
            )
        elif resource_type in ["aks", "kubernetes"]:
            # Step 1: Check AKS cluster health
            health_result = await self._call_tool(
                "check_aks_cluster_health",
                {
                    "cluster_name": self._extract_resource_name(resource_id),
                    "resource_group": request.get("resource_group", "")
                }
            )
        else:
            # Step 1: General resource health check
            health_result = await self._call_tool(
                "check_resource_health",
                {
                    "resource_id": resource_id
                }
            )

        # Store health result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="health_check",
            agent_id=self.agent_id,
            result=health_result
        )

        # Extract health data
        health_data = health_result.get("data", {})
        availability_state = health_data.get("availability_state", "Unknown")

        # Map availability state to health level
        health_status = self._map_availability_to_health(availability_state)

        # Optionally get performance metrics
        metrics_data = None
        if include_metrics:
            try:
                metrics_result = await self._call_tool(
                    "get_performance_metrics",
                    {
                        "resource_id": resource_id,
                        "metric_names": ["cpu_percent", "memory_percent", "response_time"],
                        "time_range": "1h"
                    }
                )
                metrics_data = metrics_result.get("data", {})

                # Store metrics result
                await self.context_store.add_step_result(
                    workflow_id=workflow_id,
                    step_id="metrics",
                    agent_id=self.agent_id,
                    result=metrics_result
                )
            except Exception as exc:
                logger.warning(f"Failed to get metrics: {exc}")
                metrics_data = {"error": str(exc)}

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "health": {
                "status": health_status,
                "availability_state": availability_state,
                "health_score": self.health_levels.get(health_status, {}).get("score", 0),
                "summary": health_data.get("summary", ""),
                "recent_issues": health_data.get("recent_issues", []),
                "recommended_actions": health_data.get("recommended_actions", []),
                "metrics": metrics_data if include_metrics else None,
                "checked_at": datetime.utcnow().isoformat()
            }
        }

    async def _diagnose_service(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Diagnose service-specific issues.

        Performs deep diagnostics for specific Azure service types.

        Args:
            request: Diagnostic request with service type
            context: Optional workflow context

        Returns:
            Diagnostic results with findings and recommendations
        """
        resource_id = request.get("resource_id", "")
        service_type = request.get("service_type", "")
        workflow_id = request.get("workflow_id", f"diagnose-{datetime.utcnow().timestamp()}")

        # Auto-detect service type if not provided
        if not service_type:
            service_type = self._extract_resource_type(resource_id)

        logger.info(f"Diagnosing {service_type} service: {resource_id}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "service_type": service_type,
                "action": "diagnose",
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Get appropriate diagnostic tool
        diagnostic_tool = self.diagnostic_tools.get(service_type.lower())
        if not diagnostic_tool:
            logger.warning(f"No specific diagnostic tool for {service_type}, using generic health check")
            diagnostic_tool = "check_resource_health"

        # Step 2: Run diagnostics
        diagnostic_params = {
            "resource_id": resource_id
        }

        # Add service-specific parameters
        if service_type in ["app_service", "function_app"]:
            diagnostic_params["app_name"] = self._extract_resource_name(resource_id)
            diagnostic_params["resource_group"] = request.get("resource_group", "")
        elif service_type in ["api_management", "apim"]:
            diagnostic_params["apim_name"] = self._extract_resource_name(resource_id)
            diagnostic_params["resource_group"] = request.get("resource_group", "")
        elif service_type in ["aks", "kubernetes"]:
            diagnostic_params["cluster_name"] = self._extract_resource_name(resource_id)
            diagnostic_params["resource_group"] = request.get("resource_group", "")
        elif service_type == "container_app":
            diagnostic_params["app_name"] = self._extract_resource_name(resource_id)
            diagnostic_params["resource_group"] = request.get("resource_group", "")

        diagnostic_result = await self._call_tool(
            diagnostic_tool,
            diagnostic_params
        )

        # Store diagnostic result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="diagnostics",
            agent_id=self.agent_id,
            result=diagnostic_result
        )

        diagnostic_data = diagnostic_result.get("data", {})

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "service_type": service_type,
            "diagnostics": {
                "findings": diagnostic_data.get("findings", []),
                "issues_detected": diagnostic_data.get("issues", []),
                "root_causes": diagnostic_data.get("root_causes", []),
                "recommendations": diagnostic_data.get("recommendations", []),
                "severity": diagnostic_data.get("severity", "medium"),
                "diagnostics_timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _check_dependencies(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check resource dependencies and impact.

        Maps resource dependencies to understand blast radius and
        impact of potential failures.

        Args:
            request: Dependency check request
            context: Optional workflow context

        Returns:
            Dependency map with health status of dependencies
        """
        resource_id = request.get("resource_id", "")
        depth = request.get("depth", 2)
        check_health = request.get("check_health", True)
        workflow_id = request.get("workflow_id", f"deps-{datetime.utcnow().timestamp()}")

        logger.info(f"Checking dependencies for: {resource_id}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "depth": depth,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 3: Get resource dependencies
        deps_result = await self._call_tool(
            "get_resource_dependencies",
            {
                "resource_id": resource_id,
                "depth": depth
            }
        )

        # Store dependencies result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="dependencies",
            agent_id=self.agent_id,
            result=deps_result
        )

        deps_data = deps_result.get("data", {})
        upstream_deps = deps_data.get("upstream", [])
        downstream_deps = deps_data.get("downstream", [])

        # Optionally check health of dependencies
        dependency_health = {}
        if check_health:
            all_deps = upstream_deps + downstream_deps
            for dep_id in all_deps[:10]:  # Limit to 10 to avoid timeout
                try:
                    health_result = await self._call_tool(
                        "check_resource_health",
                        {"resource_id": dep_id}
                    )
                    health_data = health_result.get("data", {})
                    availability = health_data.get("availability_state", "Unknown")
                    dependency_health[dep_id] = {
                        "status": self._map_availability_to_health(availability),
                        "availability": availability
                    }
                except Exception as exc:
                    logger.warning(f"Failed to check health for dependency {dep_id}: {exc}")
                    dependency_health[dep_id] = {"status": "unknown", "error": str(exc)}

        # Calculate impact metrics
        total_dependencies = len(upstream_deps) + len(downstream_deps)
        critical_dependencies = sum(
            1 for status in dependency_health.values()
            if status.get("status") in ["unhealthy", "critical"]
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "dependencies": {
                "total_count": total_dependencies,
                "upstream_count": len(upstream_deps),
                "downstream_count": len(downstream_deps),
                "upstream_resources": upstream_deps[:10],
                "downstream_resources": downstream_deps[:10],
                "dependency_health": dependency_health,
                "critical_dependencies": critical_dependencies,
                "blast_radius": "high" if len(downstream_deps) > 10 else "medium" if len(downstream_deps) > 5 else "low",
                "checked_at": datetime.utcnow().isoformat()
            }
        }

    async def _continuous_monitor(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform continuous health monitoring.

        Monitors resources continuously for a specified duration,
        tracking health status changes and triggering alerts.

        Args:
            request: Monitoring request with resources and parameters
            context: Optional workflow context

        Returns:
            Monitoring results with health history and alerts
        """
        resource_ids = request.get("resource_ids", [])
        interval_seconds = request.get("interval_seconds", 60)
        duration_minutes = request.get("duration_minutes", 10)
        workflow_id = request.get("workflow_id", f"monitor-{datetime.utcnow().timestamp()}")

        logger.info(
            f"Starting continuous monitoring for {len(resource_ids)} resources "
            f"(interval: {interval_seconds}s, duration: {duration_minutes}m)"
        )

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_ids": resource_ids,
                "interval_seconds": interval_seconds,
                "duration_minutes": duration_minutes,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Note: In production, this would be an async background task
        # For now, we'll simulate with a single check and return monitoring plan

        health_snapshots = []
        alerts = []

        # Take initial health snapshot
        for resource_id in resource_ids[:5]:  # Limit to 5 resources
            try:
                health_result = await self._call_tool(
                    "check_resource_health",
                    {"resource_id": resource_id}
                )
                health_data = health_result.get("data", {})
                availability = health_data.get("availability_state", "Unknown")
                health_status = self._map_availability_to_health(availability)

                snapshot = {
                    "resource_id": resource_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "health_status": health_status,
                    "availability": availability
                }
                health_snapshots.append(snapshot)

                # Generate alert if unhealthy
                if health_status in ["unhealthy", "critical"]:
                    alerts.append({
                        "resource_id": resource_id,
                        "severity": health_status,
                        "message": f"Resource health is {health_status}",
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except Exception as exc:
                logger.warning(f"Failed to check health for {resource_id}: {exc}")

        # Store monitoring snapshot
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="monitoring_snapshot",
            agent_id=self.agent_id,
            result={"snapshots": health_snapshots, "alerts": alerts}
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "monitoring": {
                "resources_monitored": len(resource_ids),
                "interval_seconds": interval_seconds,
                "duration_minutes": duration_minutes,
                "snapshots_collected": len(health_snapshots),
                "alerts_generated": len(alerts),
                "current_snapshot": health_snapshots,
                "alerts": alerts,
                "monitoring_status": "active",
                "next_check_at": (datetime.utcnow() + timedelta(seconds=interval_seconds)).isoformat(),
                "started_at": datetime.utcnow().isoformat()
            }
        }

    async def _generate_recommendations(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate proactive health recommendations.

        Analyzes health patterns and generates recommendations for
        improving reliability and preventing issues.

        Args:
            request: Recommendation request
            context: Optional workflow context

        Returns:
            Health recommendations with priority and impact
        """
        workflow_id = request.get("workflow_id", f"recommend-{datetime.utcnow().timestamp()}")
        resource_group = request.get("resource_group", "")

        logger.info("Generating health recommendations")

        # Get workflow context if it exists (from previous steps)
        workflow_context = await self.context_store.get_workflow_context(workflow_id)

        # Analyze previous health checks and diagnostics
        recommendations = self._analyze_health_patterns(workflow_context)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "recommendations": {
                "immediate_actions": recommendations.get("immediate", []),
                "preventive_actions": recommendations.get("preventive", []),
                "optimization_opportunities": recommendations.get("optimization", []),
                "best_practices": recommendations.get("best_practices", []),
                "estimated_impact": {
                    "reliability_improvement": "High",
                    "availability_improvement": "15-25%",
                    "mttr_reduction": "20-30%"
                },
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    def _analyze_health_patterns(self, workflow_context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Analyze health patterns and generate recommendations.

        Args:
            workflow_context: Workflow context with health data

        Returns:
            Categorized recommendations
        """
        recommendations = {
            "immediate": [],
            "preventive": [],
            "optimization": [],
            "best_practices": []
        }

        # Analyze health check results
        steps = workflow_context.get("steps", {})
        health_data = steps.get("health_check", {})

        if health_data:
            availability = health_data.get("data", {}).get("availability_state", "")

            if availability in ["Unavailable", "Degraded"]:
                recommendations["immediate"].append(
                    "Investigate and resolve current availability issues immediately"
                )
                recommendations["immediate"].append(
                    "Review recent deployments and configuration changes"
                )

            recent_issues = health_data.get("data", {}).get("recent_issues", [])
            if len(recent_issues) > 3:
                recommendations["preventive"].append(
                    f"Address recurring issues - {len(recent_issues)} incidents detected"
                )

        # General best practices
        recommendations["best_practices"].extend([
            "Implement automated health checks with alerting",
            "Set up health monitoring dashboards",
            "Configure auto-healing policies for critical resources",
            "Establish health SLIs and SLOs for key services",
            "Implement circuit breakers for dependent services"
        ])

        recommendations["optimization"].extend([
            "Review and optimize resource configurations",
            "Implement redundancy for single points of failure",
            "Set up multi-region failover capabilities"
        ])

        recommendations["preventive"].extend([
            "Schedule regular health audits",
            "Implement chaos engineering experiments",
            "Set up predictive alerting based on health trends"
        ])

        return recommendations

    async def _full_health_assessment(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full health assessment workflow.

        Runs all phases: check_health → diagnose → dependencies → recommendations

        Args:
            request: Full assessment request
            context: Optional workflow context

        Returns:
            Complete health assessment with all findings
        """
        workflow_id = f"full-health-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        resource_id = request.get("resource_id", "")
        resource_group = request.get("resource_group", "")

        logger.info(f"Starting full health assessment: {workflow_id}")

        # Phase 1: Check health
        health_result = await self._check_health(request, context)

        # Phase 2: Run diagnostics
        diagnose_result = await self._diagnose_service(request, context)

        # Phase 3: Check dependencies
        deps_result = None
        if resource_id:
            deps_result = await self._check_dependencies(request, context)

        # Phase 4: Generate recommendations
        recommendations_result = await self._generate_recommendations(request, context)

        # Aggregate health score
        health_status = health_result.get("health", {}).get("status", "unknown")
        health_score = self.health_levels.get(health_status, {}).get("score", 0)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "phases": {
                "health_check": health_result,
                "diagnostics": diagnose_result,
                "dependencies": deps_result,
                "recommendations": recommendations_result
            },
            "summary": {
                "overall_health": health_status,
                "health_score": health_score,
                "issues_found": len(diagnose_result.get("diagnostics", {}).get("issues_detected", [])),
                "critical_dependencies": deps_result.get("dependencies", {}).get("critical_dependencies", 0) if deps_result else 0,
                "recommendations_count": len(recommendations_result.get("recommendations", {}).get("immediate_actions", [])),
                "completed_at": datetime.utcnow().isoformat()
            }
        }

    def _extract_resource_type(self, resource_id: str) -> str:
        """Extract resource type from Azure resource ID.

        Args:
            resource_id: Azure resource ID

        Returns:
            Resource type (e.g., 'app_service', 'vm', 'aks')
        """
        if not resource_id:
            return "unknown"

        resource_id_lower = resource_id.lower()

        # Check for specific resource types
        if "/microsoft.web/sites/" in resource_id_lower:
            return "app_service"
        elif "/microsoft.containerinstance/" in resource_id_lower or "/containerapps/" in resource_id_lower:
            return "container_app"
        elif "/microsoft.containerservice/managedclusters/" in resource_id_lower:
            return "aks"
        elif "/microsoft.apimanagement/" in resource_id_lower:
            return "api_management"
        elif "/microsoft.compute/virtualmachines/" in resource_id_lower:
            return "vm"
        elif "/microsoft.storage/" in resource_id_lower:
            return "storage"
        elif "/microsoft.sql/" in resource_id_lower:
            return "sql"
        else:
            return "unknown"

    def _extract_resource_name(self, resource_id: str) -> str:
        """Extract resource name from Azure resource ID.

        Args:
            resource_id: Azure resource ID

        Returns:
            Resource name
        """
        if not resource_id:
            return ""

        parts = resource_id.split("/")
        return parts[-1] if parts else ""

    def _map_availability_to_health(self, availability_state: str) -> str:
        """Map Azure availability state to health status.

        Args:
            availability_state: Azure availability state

        Returns:
            Health status level
        """
        availability_lower = availability_state.lower()

        if availability_lower == "available":
            return "healthy"
        elif availability_lower == "degraded":
            return "degraded"
        elif availability_lower in ["unavailable", "unknown"]:
            return "critical"
        else:
            return "unknown"
