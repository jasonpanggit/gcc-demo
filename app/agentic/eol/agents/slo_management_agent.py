"""SLO Management Agent - Specialized SRE agent for SLO/SLI tracking and error budget management.

This agent handles:
- SLO/SLI metric tracking (availability, latency, error rate, throughput)
- Error budget calculation and monitoring
- SLO-based alert configuration
- SLO compliance reporting
- Burn rate forecasting
- Multi-window SLO analysis (28d, 7d, 1d, 1h)
- Target vs actual performance comparison
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


class SLOManagementAgent(BaseSREAgent):
    """Specialized agent for SLO/SLI management and error budget tracking.

    This agent orchestrates SLO management workflows:
    1. Track SLO/SLI metrics across multiple time windows
    2. Calculate error budget consumption and remaining budget
    3. Configure SLO-based alerting policies
    4. Generate SLO compliance reports
    5. Forecast SLO burn rate and predict budget exhaustion
    6. Recommend SLO improvements and adjustments

    Supports multiple SLO types:
    - Availability SLO (e.g., 99.9% uptime)
    - Latency SLO (e.g., p95 < 200ms, p99 < 500ms)
    - Error rate SLO (e.g., < 0.1% errors)
    - Throughput SLO (e.g., > 1000 requests/sec)

    Example usage:
        agent = SLOManagementAgent()
        await agent.initialize()

        # Track SLO metrics
        result = await agent.handle_request({
            "action": "track",
            "service": "api-gateway",
            "slo_type": "availability",
            "time_window": "7d"
        })

        # Calculate error budget
        result = await agent.handle_request({
            "action": "budget",
            "service": "api-gateway",
            "slo_target": 99.9,
            "time_window": "28d"
        })

        # Generate SLO compliance report
        result = await agent.handle_request({
            "action": "report",
            "service": "api-gateway",
            "time_range": "30d"
        })

        # Full SLO analysis
        result = await agent.handle_request({
            "action": "full",
            "service": "api-gateway",
            "slo_types": ["availability", "latency", "error_rate"]
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize SLO Management Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="slo-management",
            agent_id=agent_id or "slo-management-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # SLO targets and thresholds
        self.slo_targets = {
            "availability": 99.9,        # 99.9% uptime target
            "latency_p95_ms": 200,       # p95 < 200ms
            "latency_p99_ms": 500,       # p99 < 500ms
            "error_rate": 0.1,           # < 0.1% error rate
            "throughput_rps": 1000       # > 1000 requests/sec
        }

        # Error budget thresholds
        self.budget_thresholds = {
            "critical": 10.0,   # < 10% budget remaining
            "warning": 25.0,    # < 25% budget remaining
            "healthy": 50.0     # > 50% budget remaining
        }

        # Time windows for SLO analysis
        self.time_windows = {
            "28d": "28-day rolling window",
            "7d": "7-day rolling window",
            "1d": "1-day rolling window",
            "1h": "1-hour rolling window"
        }

        # SLO types
        self.slo_types = [
            "availability",
            "latency",
            "error_rate",
            "throughput"
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
            logger.error(f"Failed to initialize SLO Management Agent: {exc}")
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
        """Execute SLO management action.

        Args:
            request: Request containing:
                - action: Action to perform (track, budget, alert, report, forecast, full)
                - service: Service name to monitor
                - slo_type: Type of SLO (availability, latency, error_rate, throughput)
                - slo_target: Target percentage (e.g., 99.9 for 99.9%)
                - time_window: Time window for analysis (default: 28d)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            SLO analysis results with metrics, budget status, and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "track")
        service = request.get("service")

        if not service:
            raise AgentExecutionError("service parameter is required")

        logger.info(f"Processing SLO management action '{action}' for service: {service}")

        # Route to appropriate handler
        action_handlers = {
            "track": self._track_slo_metrics,
            "budget": self._calculate_error_budget,
            "alert": self._configure_slo_alerts,
            "report": self._generate_slo_report,
            "forecast": self._forecast_burn_rate,
            "full": self._full_slo_analysis
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

    async def _track_slo_metrics(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Track SLO/SLI metrics over time.

        Collects and tracks SLO metrics (availability, latency, error rate, throughput)
        across multiple time windows.

        Args:
            request: Tracking request with service and SLO parameters
            context: Optional workflow context

        Returns:
            SLO metrics with current values and trends
        """
        service = request["service"]
        slo_type = request.get("slo_type", "availability")
        time_window = request.get("time_window", "28d")
        workflow_id = f"slo-track-{service}-{datetime.utcnow().timestamp()}"

        logger.info(f"Tracking {slo_type} SLO metrics for service: {service}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "service": service,
                "slo_type": slo_type,
                "time_window": time_window,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Track SLO metrics
        metrics_result = await self._call_tool(
            "track_slo_metrics",
            {
                "service_name": service,
                "slo_type": slo_type,
                "time_window": time_window
            }
        )

        # Store metrics result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="track_metrics",
            agent_id=self.agent_id,
            result=metrics_result
        )

        # Extract metrics data
        metrics_data = metrics_result.get("data", {})
        current_value = metrics_data.get("current_value", 0)
        target_value = self.slo_targets.get(slo_type, 99.9)

        # Calculate status
        status = self._calculate_slo_status(slo_type, current_value, target_value)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "slo_metrics": {
                "slo_type": slo_type,
                "time_window": time_window,
                "current_value": current_value,
                "target_value": target_value,
                "status": status,
                "trend": metrics_data.get("trend", "stable"),
                "data_points": metrics_data.get("data_points", []),
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": [
                "calculate_error_budget",
                "configure_alerts",
                "forecast_burn_rate"
            ]
        }

    def _calculate_slo_status(
        self,
        slo_type: str,
        current_value: float,
        target_value: float
    ) -> str:
        """Calculate SLO status based on current vs target value.

        Args:
            slo_type: Type of SLO
            current_value: Current metric value
            target_value: Target metric value

        Returns:
            Status: 'meeting', 'at_risk', 'breached'
        """
        # For availability and throughput, higher is better
        if slo_type in ["availability", "throughput"]:
            if current_value >= target_value:
                return "meeting"
            elif current_value >= target_value * 0.95:
                return "at_risk"
            else:
                return "breached"
        # For latency and error_rate, lower is better
        else:
            if current_value <= target_value:
                return "meeting"
            elif current_value <= target_value * 1.1:
                return "at_risk"
            else:
                return "breached"

    async def _calculate_error_budget(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calculate error budget consumption and remaining budget.

        Analyzes SLO compliance to determine how much error budget has been
        consumed and how much remains for the time window.

        Args:
            request: Error budget request with service and target
            context: Optional workflow context

        Returns:
            Error budget analysis with consumption rate and remaining budget
        """
        service = request["service"]
        slo_target = request.get("slo_target", 99.9)
        time_window = request.get("time_window", "28d")
        workflow_id = request.get("workflow_id", f"slo-budget-{service}-{datetime.utcnow().timestamp()}")

        logger.info(f"Calculating error budget for service: {service} (target: {slo_target}%)")

        # Step 2: Calculate error budget
        budget_result = await self._call_tool(
            "calculate_error_budget",
            {
                "service_name": service,
                "slo_target": slo_target,
                "time_window": time_window
            }
        )

        # Store budget result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="calculate_budget",
            agent_id=self.agent_id,
            result=budget_result
        )

        # Extract budget data
        budget_data = budget_result.get("data", {})
        budget_remaining = budget_data.get("budget_remaining_percent", 0)
        budget_consumed = budget_data.get("budget_consumed_percent", 0)
        burn_rate = budget_data.get("current_burn_rate", 0)

        # Determine budget health
        if budget_remaining <= self.budget_thresholds["critical"]:
            budget_health = "critical"
        elif budget_remaining <= self.budget_thresholds["warning"]:
            budget_health = "warning"
        else:
            budget_health = "healthy"

        # Calculate time until budget exhaustion
        time_until_exhaustion = self._calculate_exhaustion_time(
            budget_remaining,
            burn_rate,
            time_window
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "error_budget": {
                "slo_target": slo_target,
                "time_window": time_window,
                "budget_remaining_percent": budget_remaining,
                "budget_consumed_percent": budget_consumed,
                "budget_health": budget_health,
                "current_burn_rate": burn_rate,
                "time_until_exhaustion": time_until_exhaustion,
                "total_budget_minutes": budget_data.get("total_budget_minutes", 0),
                "consumed_budget_minutes": budget_data.get("consumed_budget_minutes", 0),
                "remaining_budget_minutes": budget_data.get("remaining_budget_minutes", 0),
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_budget_recommendations(budget_health, budget_remaining)
        }

    def _calculate_exhaustion_time(
        self,
        budget_remaining: float,
        burn_rate: float,
        time_window: str
    ) -> Optional[str]:
        """Calculate estimated time until error budget exhaustion.

        Args:
            budget_remaining: Remaining budget percentage
            burn_rate: Current burn rate (% per day)
            time_window: Time window for analysis

        Returns:
            Estimated time until exhaustion (human-readable) or None
        """
        if burn_rate <= 0 or budget_remaining >= 100:
            return None

        days_until_exhaustion = budget_remaining / burn_rate

        if days_until_exhaustion < 1:
            hours = int(days_until_exhaustion * 24)
            return f"{hours} hours"
        elif days_until_exhaustion < 7:
            days = int(days_until_exhaustion)
            return f"{days} days"
        else:
            weeks = int(days_until_exhaustion / 7)
            return f"{weeks} weeks"

    def _generate_budget_recommendations(
        self,
        budget_health: str,
        budget_remaining: float
    ) -> List[str]:
        """Generate recommendations based on budget health.

        Args:
            budget_health: Health status (critical, warning, healthy)
            budget_remaining: Remaining budget percentage

        Returns:
            List of recommendations
        """
        recommendations = []

        if budget_health == "critical":
            recommendations.extend([
                "⚠️ CRITICAL: Error budget nearly exhausted",
                "Implement emergency change freeze",
                "Focus on stability - delay non-critical deployments",
                "Investigate recent incidents and degradations",
                "Consider relaxing SLO targets if too aggressive"
            ])
        elif budget_health == "warning":
            recommendations.extend([
                "⚠️ WARNING: Error budget consumption elevated",
                "Review recent deployments and changes",
                "Increase monitoring and alerting sensitivity",
                "Plan capacity improvements if needed",
                "Prepare incident response procedures"
            ])
        else:
            recommendations.extend([
                "✓ Error budget healthy",
                "Continue current operations",
                "Monitor burn rate trends",
                "Consider investing budget in innovation"
            ])

        return recommendations

    async def _configure_slo_alerts(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Configure SLO-based alerting policies.

        Sets up multi-window, multi-burn-rate alerts to detect SLO violations
        early while avoiding false positives.

        Args:
            request: Alert configuration request
            context: Optional workflow context

        Returns:
            Configured alert policies
        """
        service = request["service"]
        slo_target = request.get("slo_target", 99.9)
        alert_windows = request.get("alert_windows", ["1h", "6h", "24h", "7d"])
        workflow_id = request.get("workflow_id", f"slo-alert-{service}-{datetime.utcnow().timestamp()}")

        logger.info(f"Configuring SLO alerts for service: {service}")

        # Step 3: Configure SLO-based alerts
        alert_result = await self._call_tool(
            "configure_slo_alerts",
            {
                "service_name": service,
                "slo_target": slo_target,
                "alert_windows": alert_windows,
                "notification_channels": request.get("notification_channels", ["email", "slack"])
            }
        )

        # Store alert configuration
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="configure_alerts",
            agent_id=self.agent_id,
            result=alert_result
        )

        alert_data = alert_result.get("data", {})
        alert_policies = alert_data.get("alert_policies", [])

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "alert_configuration": {
                "slo_target": slo_target,
                "total_policies": len(alert_policies),
                "alert_policies": alert_policies,
                "alert_windows": alert_windows,
                "burn_rate_thresholds": {
                    "fast_burn": 14.4,   # 1h window - burns entire 28d budget in 2d
                    "medium_burn": 6,    # 6h window - burns budget in 4d
                    "slow_burn": 3       # 24h window - burns budget in 9d
                },
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _generate_slo_report(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive SLO compliance report.

        Creates a detailed report showing SLO compliance across all metrics,
        time windows, and services.

        Args:
            request: Report generation request
            context: Optional workflow context

        Returns:
            SLO compliance report with historical trends
        """
        service = request["service"]
        time_range = request.get("time_range", "30d")
        workflow_id = request.get("workflow_id", f"slo-report-{service}-{datetime.utcnow().timestamp()}")

        logger.info(f"Generating SLO compliance report for service: {service}")

        # Step 4: Get SLO compliance data
        compliance_result = await self._call_tool(
            "get_slo_compliance",
            {
                "service_name": service,
                "time_range": time_range,
                "include_history": True
            }
        )

        # Store compliance data
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="get_compliance",
            agent_id=self.agent_id,
            result=compliance_result
        )

        compliance_data = compliance_result.get("data", {})
        slo_metrics = compliance_data.get("slo_metrics", {})

        # Analyze compliance across all SLO types
        compliance_summary = self._analyze_compliance_data(slo_metrics)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "slo_report": {
                "time_range": time_range,
                "generated_at": datetime.utcnow().isoformat(),
                "summary": compliance_summary,
                "slo_metrics": slo_metrics,
                "historical_trends": compliance_data.get("historical_trends", []),
                "incidents": compliance_data.get("related_incidents", []),
                "recommendations": self._generate_report_recommendations(compliance_summary)
            }
        }

    def _analyze_compliance_data(self, slo_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze compliance data to generate summary.

        Args:
            slo_metrics: SLO metrics data

        Returns:
            Compliance summary
        """
        total_slos = len(slo_metrics)
        meeting_slos = sum(1 for m in slo_metrics.values() if m.get("status") == "meeting")
        at_risk_slos = sum(1 for m in slo_metrics.values() if m.get("status") == "at_risk")
        breached_slos = sum(1 for m in slo_metrics.values() if m.get("status") == "breached")

        if total_slos == 0:
            overall_health = "unknown"
        elif breached_slos > 0:
            overall_health = "critical"
        elif at_risk_slos > 0:
            overall_health = "warning"
        else:
            overall_health = "healthy"

        compliance_percentage = (meeting_slos / total_slos * 100) if total_slos > 0 else 0

        return {
            "overall_health": overall_health,
            "total_slos": total_slos,
            "meeting_slos": meeting_slos,
            "at_risk_slos": at_risk_slos,
            "breached_slos": breached_slos,
            "compliance_percentage": round(compliance_percentage, 2)
        }

    def _generate_report_recommendations(self, compliance_summary: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on compliance report.

        Args:
            compliance_summary: Compliance summary data

        Returns:
            List of recommendations
        """
        recommendations = []
        overall_health = compliance_summary.get("overall_health", "unknown")
        breached = compliance_summary.get("breached_slos", 0)
        at_risk = compliance_summary.get("at_risk_slos", 0)

        if overall_health == "critical":
            recommendations.extend([
                f"⚠️ {breached} SLO(s) breached - immediate action required",
                "Review incidents causing SLO violations",
                "Implement remediation plans",
                "Consider temporary capacity increase"
            ])

        if at_risk > 0:
            recommendations.extend([
                f"⚠️ {at_risk} SLO(s) at risk",
                "Investigate trending issues",
                "Proactive monitoring recommended"
            ])

        if overall_health == "healthy":
            recommendations.append("✓ All SLOs meeting targets")

        return recommendations

    async def _forecast_burn_rate(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Forecast SLO error budget burn rate.

        Uses historical data to predict future error budget consumption
        and identify potential SLO violations before they occur.

        Args:
            request: Forecast request
            context: Optional workflow context

        Returns:
            Burn rate forecast with predictions
        """
        service = request["service"]
        forecast_days = request.get("forecast_days", 7)
        workflow_id = request.get("workflow_id", f"slo-forecast-{service}-{datetime.utcnow().timestamp()}")

        logger.info(f"Forecasting burn rate for service: {service}")

        # Step 5: Forecast SLO burn rate
        forecast_result = await self._call_tool(
            "forecast_slo_burn_rate",
            {
                "service_name": service,
                "forecast_days": forecast_days,
                "confidence_level": request.get("confidence_level", 0.95)
            }
        )

        # Store forecast
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="forecast_burn",
            agent_id=self.agent_id,
            result=forecast_result
        )

        forecast_data = forecast_result.get("data", {})
        predictions = forecast_data.get("predictions", [])

        # Analyze forecast for risk
        risk_analysis = self._analyze_forecast_risk(predictions)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "forecast": {
                "forecast_days": forecast_days,
                "predictions": predictions,
                "risk_analysis": risk_analysis,
                "confidence_intervals": forecast_data.get("confidence_intervals", {}),
                "trending": forecast_data.get("trending", "stable"),
                "predicted_exhaustion_date": forecast_data.get("predicted_exhaustion_date"),
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_forecast_recommendations(risk_analysis)
        }

    def _analyze_forecast_risk(self, predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze forecast predictions for risk.

        Args:
            predictions: List of forecast predictions

        Returns:
            Risk analysis
        """
        if not predictions:
            return {"risk_level": "unknown", "confidence": "low"}

        # Check if any predictions show budget exhaustion
        exhaustion_predicted = any(
            p.get("budget_remaining", 100) <= 0
            for p in predictions
        )

        # Check burn rate trend
        burn_rates = [p.get("burn_rate", 0) for p in predictions]
        avg_burn_rate = sum(burn_rates) / len(burn_rates) if burn_rates else 0

        if exhaustion_predicted:
            risk_level = "critical"
        elif avg_burn_rate > 2.0:
            risk_level = "high"
        elif avg_burn_rate > 1.0:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "avg_burn_rate": round(avg_burn_rate, 2),
            "exhaustion_predicted": exhaustion_predicted,
            "confidence": "high" if len(predictions) >= 7 else "medium"
        }

    def _generate_forecast_recommendations(self, risk_analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on forecast.

        Args:
            risk_analysis: Risk analysis data

        Returns:
            List of recommendations
        """
        recommendations = []
        risk_level = risk_analysis.get("risk_level", "unknown")

        if risk_level == "critical":
            recommendations.extend([
                "⚠️ CRITICAL: Budget exhaustion predicted",
                "Implement immediate stability measures",
                "Defer non-critical changes",
                "Increase monitoring frequency",
                "Prepare incident response team"
            ])
        elif risk_level == "high":
            recommendations.extend([
                "⚠️ High burn rate detected",
                "Review recent changes",
                "Increase alerting sensitivity",
                "Plan capacity improvements"
            ])
        elif risk_level == "medium":
            recommendations.extend([
                "Monitor burn rate trends closely",
                "Continue normal operations with caution"
            ])
        else:
            recommendations.append("✓ Burn rate within expected range")

        return recommendations

    async def _full_slo_analysis(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full SLO analysis workflow.

        Runs all phases: track → budget → alert → report → forecast

        Args:
            request: Full analysis request
            context: Optional workflow context

        Returns:
            Complete SLO analysis with all metrics and recommendations
        """
        service = request["service"]
        slo_types = request.get("slo_types", self.slo_types)
        workflow_id = f"slo-full-{service}-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        logger.info(f"Starting full SLO analysis for service: {service}")

        # Create master workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "service": service,
                "slo_types": slo_types,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        results = {}

        # Phase 1: Track metrics for each SLO type
        track_results = []
        for slo_type in slo_types:
            try:
                track_req = request.copy()
                track_req["slo_type"] = slo_type
                track_result = await self._track_slo_metrics(track_req, context)
                track_results.append(track_result)
            except Exception as exc:
                logger.warning(f"Failed to track {slo_type} SLO: {exc}")

        results["tracking"] = track_results

        # Phase 2: Calculate error budget
        budget_result = await self._calculate_error_budget(request, context)
        results["budget"] = budget_result

        # Phase 3: Configure alerts
        alert_result = await self._configure_slo_alerts(request, context)
        results["alerts"] = alert_result

        # Phase 4: Generate compliance report
        report_result = await self._generate_slo_report(request, context)
        results["report"] = report_result

        # Phase 5: Forecast burn rate
        forecast_result = await self._forecast_burn_rate(request, context)
        results["forecast"] = forecast_result

        # Generate executive summary
        summary = self._generate_executive_summary(results)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "service": service,
            "phases": results,
            "executive_summary": summary,
            "completed_at": datetime.utcnow().isoformat()
        }

    def _generate_executive_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary from full analysis.

        Args:
            results: All phase results

        Returns:
            Executive summary
        """
        budget_data = results.get("budget", {}).get("error_budget", {})
        report_data = results.get("report", {}).get("slo_report", {}).get("summary", {})
        forecast_data = results.get("forecast", {}).get("forecast", {}).get("risk_analysis", {})

        # Determine overall status
        budget_health = budget_data.get("budget_health", "unknown")
        overall_health = report_data.get("overall_health", "unknown")
        risk_level = forecast_data.get("risk_level", "unknown")

        if budget_health == "critical" or overall_health == "critical" or risk_level == "critical":
            overall_status = "critical"
        elif budget_health == "warning" or overall_health == "warning" or risk_level == "high":
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return {
            "overall_status": overall_status,
            "slo_compliance": report_data.get("compliance_percentage", 0),
            "error_budget_remaining": budget_data.get("budget_remaining_percent", 0),
            "budget_health": budget_health,
            "risk_level": risk_level,
            "meeting_slos": report_data.get("meeting_slos", 0),
            "breached_slos": report_data.get("breached_slos", 0),
            "key_findings": self._generate_key_findings(results),
            "priority_actions": self._generate_priority_actions(overall_status, results)
        }

    def _generate_key_findings(self, results: Dict[str, Any]) -> List[str]:
        """Generate key findings from analysis.

        Args:
            results: All phase results

        Returns:
            List of key findings
        """
        findings = []

        # Budget findings
        budget_data = results.get("budget", {}).get("error_budget", {})
        budget_remaining = budget_data.get("budget_remaining_percent", 100)
        if budget_remaining < 25:
            findings.append(f"Error budget critically low: {budget_remaining:.1f}% remaining")

        # Compliance findings
        report_data = results.get("report", {}).get("slo_report", {}).get("summary", {})
        breached = report_data.get("breached_slos", 0)
        if breached > 0:
            findings.append(f"{breached} SLO(s) currently breached")

        # Forecast findings
        forecast_data = results.get("forecast", {}).get("forecast", {})
        if forecast_data.get("predicted_exhaustion_date"):
            findings.append(f"Budget exhaustion predicted: {forecast_data.get('predicted_exhaustion_date')}")

        if not findings:
            findings.append("All SLOs operating within normal parameters")

        return findings

    def _generate_priority_actions(
        self,
        overall_status: str,
        results: Dict[str, Any]
    ) -> List[str]:
        """Generate priority actions based on analysis.

        Args:
            overall_status: Overall health status
            results: All phase results

        Returns:
            List of priority actions
        """
        actions = []

        if overall_status == "critical":
            actions.extend([
                "1. Implement emergency change freeze",
                "2. Focus all efforts on stability and reliability",
                "3. Investigate and resolve active SLO breaches",
                "4. Increase monitoring and on-call coverage"
            ])
        elif overall_status == "warning":
            actions.extend([
                "1. Review and address SLOs at risk",
                "2. Increase monitoring frequency",
                "3. Defer non-critical deployments",
                "4. Prepare incident response procedures"
            ])
        else:
            actions.extend([
                "1. Continue monitoring SLO metrics",
                "2. Maintain current operational practices",
                "3. Consider investing error budget in innovation"
            ])

        return actions
