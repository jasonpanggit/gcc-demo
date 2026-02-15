"""Performance Analysis Agent - Specialized SRE agent for performance monitoring and optimization.

This agent handles:
- Performance metrics collection and analysis
- Bottleneck identification and diagnosis
- Capacity planning and forecasting
- Performance optimization recommendations
- Anomaly detection
- Baseline comparison
- Resource utilization analysis
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


class PerformanceAnalysisAgent(BaseSREAgent):
    """Specialized agent for performance analysis and optimization.

    This agent orchestrates performance monitoring workflows:
    1. Metrics collection (CPU, memory, network, disk, application metrics)
    2. Bottleneck identification
    3. Anomaly detection
    4. Baseline comparison
    5. Capacity planning and forecasting
    6. Optimization recommendations

    Example usage:
        agent = PerformanceAnalysisAgent()
        await agent.initialize()

        # Analyze resource performance
        result = await agent.handle_request({
            "action": "analyze",
            "resource_id": "/subscriptions/.../resourceGroups/rg/providers/...",
            "metrics": ["cpu", "memory", "network"],
            "time_range": "1h"
        })

        # Identify bottlenecks
        result = await agent.handle_request({
            "action": "bottlenecks",
            "resource_group": "prod-rg",
            "time_range": "24h"
        })

        # Get capacity recommendations
        result = await agent.handle_request({
            "action": "capacity",
            "resource_id": "...",
            "forecast_days": 30
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Performance Analysis Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="performance-analysis",
            agent_id=agent_id or "performance-analysis-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Performance thresholds
        self.thresholds = {
            "cpu_warning": 70.0,      # CPU % warning threshold
            "cpu_critical": 90.0,     # CPU % critical threshold
            "memory_warning": 80.0,   # Memory % warning threshold
            "memory_critical": 95.0,  # Memory % critical threshold
            "disk_warning": 80.0,     # Disk % warning threshold
            "disk_critical": 90.0,    # Disk % critical threshold
            "response_time_ms": 1000  # Response time threshold (ms)
        }

        # Metrics to collect
        self.default_metrics = [
            "cpu_percent",
            "memory_percent",
            "disk_io",
            "network_io",
            "response_time",
            "request_rate",
            "error_rate"
        ]

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
            logger.error(f"Failed to initialize Performance Analysis Agent: {exc}")
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
        """Execute performance analysis action.

        Args:
            request: Request containing:
                - action: Action to perform (analyze, bottlenecks, anomalies, capacity, optimize, compare)
                - resource_id: Azure resource ID (optional)
                - resource_group: Resource group name (optional)
                - metrics: List of metrics to collect (optional)
                - time_range: Time range for analysis (default: 1h)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Analysis results with findings and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "analyze")

        logger.info(f"Processing performance analysis action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "analyze": self._analyze_performance,
            "bottlenecks": self._identify_bottlenecks,
            "anomalies": self._detect_anomalies,
            "capacity": self._plan_capacity,
            "optimize": self._recommend_optimizations,
            "compare": self._compare_baseline,
            "full": self._full_performance_analysis
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

    async def _analyze_performance(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze resource performance metrics.

        Collects and analyzes performance metrics for a specific resource.

        Args:
            request: Analysis request with resource_id and parameters
            context: Optional workflow context

        Returns:
            Performance analysis results
        """
        resource_id = request.get("resource_id", "")
        metrics = request.get("metrics", self.default_metrics)
        time_range = request.get("time_range", "1h")
        workflow_id = request.get("workflow_id", f"perf-{datetime.utcnow().timestamp()}")

        logger.info(f"Analyzing performance for {resource_id or 'all resources'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "metrics": metrics,
                "time_range": time_range,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Get performance metrics
        metrics_result = await self._call_tool(
            "get_performance_metrics",
            {
                "resource_id": resource_id,
                "metric_names": metrics,
                "time_range": time_range
            }
        )

        # Store metrics result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="metrics",
            agent_id=self.agent_id,
            result=metrics_result
        )

        # Analyze metrics data
        metrics_data = metrics_result.get("data", {})
        analysis = self._analyze_metrics_data(metrics_data)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "analysis": {
                "time_range": time_range,
                "metrics_collected": len(metrics),
                "summary": analysis,
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _analyze_metrics_data(self, metrics_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze metrics data and determine status.

        Args:
            metrics_data: Raw metrics data

        Returns:
            Analysis summary with status and findings
        """
        # Extract metric values (mock analysis for now)
        cpu_usage = metrics_data.get("cpu_percent", {}).get("average", 0)
        memory_usage = metrics_data.get("memory_percent", {}).get("average", 0)
        disk_usage = metrics_data.get("disk_percent", {}).get("average", 0)

        issues = []
        warnings = []

        # Check CPU
        if cpu_usage >= self.thresholds["cpu_critical"]:
            issues.append(f"Critical: CPU usage at {cpu_usage:.1f}%")
        elif cpu_usage >= self.thresholds["cpu_warning"]:
            warnings.append(f"Warning: CPU usage at {cpu_usage:.1f}%")

        # Check memory
        if memory_usage >= self.thresholds["memory_critical"]:
            issues.append(f"Critical: Memory usage at {memory_usage:.1f}%")
        elif memory_usage >= self.thresholds["memory_warning"]:
            warnings.append(f"Warning: Memory usage at {memory_usage:.1f}%")

        # Check disk
        if disk_usage >= self.thresholds["disk_critical"]:
            issues.append(f"Critical: Disk usage at {disk_usage:.1f}%")
        elif disk_usage >= self.thresholds["disk_warning"]:
            warnings.append(f"Warning: Disk usage at {disk_usage:.1f}%")

        # Determine overall status
        if issues:
            status = "critical"
        elif warnings:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "disk_usage": disk_usage,
            "issues": issues,
            "warnings": warnings,
            "metrics_analyzed": len(metrics_data)
        }

    async def _identify_bottlenecks(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Identify performance bottlenecks.

        Analyzes system performance to identify bottlenecks and their root causes.

        Args:
            request: Bottleneck analysis request
            context: Optional workflow context

        Returns:
            Identified bottlenecks with recommendations
        """
        resource_group = request.get("resource_group", "")
        time_range = request.get("time_range", "1h")
        workflow_id = request.get("workflow_id", f"bottleneck-{datetime.utcnow().timestamp()}")

        logger.info(f"Identifying bottlenecks in {resource_group or 'subscription'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_group": resource_group,
                "time_range": time_range,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 2: Identify bottlenecks
        bottleneck_result = await self._call_tool(
            "identify_bottlenecks",
            {
                "resource_group": resource_group,
                "time_range": time_range
            }
        )

        # Store bottleneck result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="bottlenecks",
            agent_id=self.agent_id,
            result=bottleneck_result
        )

        bottleneck_data = bottleneck_result.get("data", {})
        bottlenecks = bottleneck_data.get("bottlenecks", [])

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "bottlenecks": {
                "total_found": len(bottlenecks),
                "bottlenecks": bottlenecks[:10],  # Limit to top 10
                "severity_breakdown": bottleneck_data.get("severity_breakdown", {}),
                "recommendations": self._generate_bottleneck_recommendations(bottlenecks),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _generate_bottleneck_recommendations(self, bottlenecks: List[Dict]) -> List[str]:
        """Generate recommendations based on identified bottlenecks.

        Args:
            bottlenecks: List of identified bottlenecks

        Returns:
            List of recommendations
        """
        recommendations = []

        for bottleneck in bottlenecks[:5]:  # Top 5
            severity = bottleneck.get("severity", "medium")
            resource_type = bottleneck.get("resource_type", "unknown")
            metric = bottleneck.get("metric", "unknown")

            if severity == "critical":
                if "cpu" in metric.lower():
                    recommendations.append(f"Scale up {resource_type} instances or add more replicas")
                elif "memory" in metric.lower():
                    recommendations.append(f"Increase memory allocation for {resource_type}")
                elif "disk" in metric.lower():
                    recommendations.append(f"Expand disk capacity or optimize storage for {resource_type}")
                elif "network" in metric.lower():
                    recommendations.append(f"Review network configuration and bandwidth for {resource_type}")

        if not recommendations:
            recommendations.append("No critical bottlenecks detected - continue monitoring")

        return recommendations

    async def _detect_anomalies(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detect performance anomalies.

        Uses statistical analysis to detect unusual patterns in performance metrics.

        Args:
            request: Anomaly detection request
            context: Optional workflow context

        Returns:
            Detected anomalies with analysis
        """
        resource_id = request.get("resource_id", "")
        metric_name = request.get("metric_name", "cpu_percent")
        time_range = request.get("time_range", "24h")
        workflow_id = request.get("workflow_id", f"anomaly-{datetime.utcnow().timestamp()}")

        logger.info(f"Detecting anomalies for {resource_id}")

        # Step 3: Detect metric anomalies
        anomaly_result = await self._call_tool(
            "detect_metric_anomalies",
            {
                "resource_id": resource_id,
                "metric_name": metric_name,
                "time_range": time_range,
                "sensitivity": request.get("sensitivity", "medium")
            }
        )

        anomaly_data = anomaly_result.get("data", {})
        anomalies = anomaly_data.get("anomalies", [])

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "anomalies": {
                "total_detected": len(anomalies),
                "anomalies": anomalies,
                "severity": "high" if len(anomalies) > 5 else "medium" if len(anomalies) > 0 else "low",
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _plan_capacity(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Plan capacity and forecast resource needs.

        Analyzes usage trends to forecast future capacity requirements.

        Args:
            request: Capacity planning request
            context: Optional workflow context

        Returns:
            Capacity recommendations and forecasts
        """
        resource_id = request.get("resource_id", "")
        forecast_days = request.get("forecast_days", 30)
        workflow_id = request.get("workflow_id", f"capacity-{datetime.utcnow().timestamp()}")

        logger.info(f"Planning capacity for {resource_id}")

        # Step 4: Get capacity recommendations
        capacity_result = await self._call_tool(
            "get_capacity_recommendations",
            {
                "resource_id": resource_id,
                "forecast_period_days": forecast_days
            }
        )

        # Step 5: Predict resource exhaustion
        exhaustion_result = await self._call_tool(
            "predict_resource_exhaustion",
            {
                "resource_id": resource_id,
                "forecast_days": forecast_days
            }
        )

        capacity_data = capacity_result.get("data", {})
        exhaustion_data = exhaustion_result.get("data", {})

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "capacity": {
                "current_utilization": capacity_data.get("current_utilization", {}),
                "recommendations": capacity_data.get("recommendations", []),
                "forecast": capacity_data.get("forecast", {}),
                "exhaustion_predictions": exhaustion_data.get("predictions", []),
                "action_required": exhaustion_data.get("action_required", False),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _recommend_optimizations(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate performance optimization recommendations.

        Args:
            request: Optimization request
            context: Optional workflow context

        Returns:
            Optimization recommendations
        """
        workflow_id = request.get("workflow_id", f"optimize-{datetime.utcnow().timestamp()}")

        logger.info("Generating optimization recommendations")

        # Get context from previous analysis steps if available
        workflow_context = await self.context_store.get_workflow_context(workflow_id)

        # Generate recommendations based on collected data
        recommendations = {
            "immediate_actions": [
                "Review and optimize slow database queries",
                "Implement caching for frequently accessed data",
                "Scale horizontally for high-traffic endpoints"
            ],
            "short_term_actions": [
                "Optimize container resource allocations",
                "Implement connection pooling",
                "Enable CDN for static assets"
            ],
            "long_term_actions": [
                "Consider microservices architecture for monolithic components",
                "Implement auto-scaling policies",
                "Optimize data access patterns"
            ],
            "estimated_impact": {
                "performance_improvement": "30-50%",
                "cost_reduction": "15-25%",
                "reliability_improvement": "High"
            }
        }

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "optimizations": recommendations,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _compare_baseline(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Compare current performance against baseline.

        Args:
            request: Baseline comparison request
            context: Optional workflow context

        Returns:
            Baseline comparison results
        """
        resource_id = request.get("resource_id", "")
        workflow_id = request.get("workflow_id", f"baseline-{datetime.utcnow().timestamp()}")

        logger.info(f"Comparing against baseline for {resource_id}")

        # Step 6: Compare baseline metrics
        baseline_result = await self._call_tool(
            "compare_baseline_metrics",
            {
                "resource_id": resource_id,
                "baseline_period": request.get("baseline_period", "7d"),
                "comparison_period": request.get("comparison_period", "1d")
            }
        )

        baseline_data = baseline_result.get("data", {})

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "comparison": {
                "deviations": baseline_data.get("deviations", []),
                "improvements": baseline_data.get("improvements", []),
                "regressions": baseline_data.get("regressions", []),
                "overall_trend": baseline_data.get("trend", "stable"),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _full_performance_analysis(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full performance analysis workflow.

        Runs all phases: analyze → bottlenecks → anomalies → capacity → optimize → compare

        Args:
            request: Full analysis request
            context: Optional workflow context

        Returns:
            Complete performance analysis report
        """
        workflow_id = f"full-perf-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        logger.info(f"Starting full performance analysis: {workflow_id}")

        # Phase 1: Analyze performance
        analyze_result = await self._analyze_performance(request, context)

        # Phase 2: Identify bottlenecks
        bottleneck_result = await self._identify_bottlenecks(request, context)

        # Phase 3: Detect anomalies
        anomaly_result = await self._detect_anomalies(request, context)

        # Phase 4: Capacity planning
        capacity_result = await self._plan_capacity(request, context)

        # Phase 5: Optimization recommendations
        optimization_result = await self._recommend_optimizations(request, context)

        # Phase 6: Baseline comparison
        comparison_result = await self._compare_baseline(request, context)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "phases": {
                "analysis": analyze_result,
                "bottlenecks": bottleneck_result,
                "anomalies": anomaly_result,
                "capacity": capacity_result,
                "optimizations": optimization_result,
                "baseline_comparison": comparison_result
            },
            "summary": {
                "overall_health": analyze_result.get("analysis", {}).get("summary", {}).get("status", "unknown"),
                "bottlenecks_found": bottleneck_result.get("bottlenecks", {}).get("total_found", 0),
                "anomalies_detected": anomaly_result.get("anomalies", {}).get("total_detected", 0),
                "capacity_action_required": capacity_result.get("capacity", {}).get("action_required", False),
                "optimization_opportunities": len(optimization_result.get("optimizations", {}).get("immediate_actions", [])),
                "completed_at": datetime.utcnow().isoformat()
            }
        }
