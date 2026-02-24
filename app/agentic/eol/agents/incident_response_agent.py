"""Incident Response Agent - Specialized SRE agent for automated incident handling.

This agent handles:
- Automated incident triage
- Alert correlation and pattern detection
- Root cause analysis (RCA)
- Impact assessment
- Postmortem generation
- MTTR tracking
- Integration with incident management systems
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


class IncidentResponseAgent(BaseSREAgent):
    """Specialized agent for automated incident response.

    This agent orchestrates multi-step incident response workflows:
    1. Initial triage and severity assessment
    2. Alert correlation and pattern detection
    3. Impact analysis (affected resources, users)
    4. Root cause analysis
    5. Remediation recommendation
    6. Postmortem generation
    7. MTTR metric tracking

    Example usage:
        agent = IncidentResponseAgent()
        await agent.initialize()

        # Triage new incident
        result = await agent.handle_request({
            "action": "triage",
            "incident_id": "INC-123",
            "description": "API gateway returning 500 errors",
            "severity": "high"
        })

        # Generate postmortem
        result = await agent.handle_request({
            "action": "postmortem",
            "incident_id": "INC-123"
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Incident Response Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="incident-response",
            agent_id=agent_id or "incident-response-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Incident severity levels and thresholds
        self.severity_levels = {
            "critical": {"priority": 1, "response_time": 15},  # 15 min
            "high": {"priority": 2, "response_time": 60},      # 1 hour
            "medium": {"priority": 3, "response_time": 240},   # 4 hours
            "low": {"priority": 4, "response_time": 1440}      # 24 hours
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
            logger.error(f"Failed to initialize Incident Response Agent: {exc}")
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
        """Execute incident response action.

        Args:
            request: Request containing:
                - action: Action to perform (triage, correlate, rca, postmortem, etc.)
                - incident_id: Incident identifier
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Action result with incident analysis and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "triage")
        incident_id = request.get("incident_id")

        if not incident_id:
            raise AgentExecutionError("incident_id is required")

        logger.info(f"Processing incident {incident_id} with action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "triage": self._triage_incident,
            "correlate": self._correlate_alerts,
            "rca": self._perform_rca,
            "impact": self._assess_impact,
            "remediate": self._recommend_remediation,
            "postmortem": self._generate_postmortem,
            "full": self._full_incident_response
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

    async def _triage_incident(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform automated incident triage.

        Analyzes incident details, checks logs, identifies affected resources,
        and determines severity and priority.

        Args:
            request: Triage request with incident details
            context: Optional workflow context

        Returns:
            Triage results with severity, priority, and initial analysis
        """
        incident_id = request["incident_id"]
        description = request.get("description", "")
        severity = request.get("severity", "medium")

        logger.info(f"Triaging incident {incident_id}")

        # Create workflow context for this incident
        workflow_id = f"incident-{incident_id}"
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "incident_id": incident_id,
                "description": description,
                "severity": severity,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Call triage tool
        triage_result = await self._call_tool(
            "triage_incident",
            {
                "incident_description": description,
                "severity": severity
            }
        )

        # Store triage result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="triage",
            agent_id=self.agent_id,
            result=triage_result
        )

        # Extract key information
        triage_data = triage_result.get("data", {})

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "triage": {
                "severity": severity,
                "priority": self.severity_levels.get(severity, {}).get("priority", 3),
                "response_time_mins": self.severity_levels.get(severity, {}).get("response_time", 240),
                "analysis": triage_data,
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": [
                "correlate_alerts",
                "assess_impact",
                "perform_rca"
            ]
        }

    async def _correlate_alerts(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Correlate related alerts and events.

        Searches for alerts and events related to the incident across
        different systems and time windows.

        Args:
            request: Correlation request
            context: Optional workflow context

        Returns:
            Correlated alerts and event timeline
        """
        incident_id = request["incident_id"]
        time_window = request.get("time_window", "1h")
        workflow_id = f"incident-{incident_id}"

        logger.info(f"Correlating alerts for incident {incident_id}")

        # Step 2: Correlate alerts
        correlation_result = await self._call_tool(
            "correlate_alerts",
            {
                "time_window": time_window,
                "severity": request.get("severity", "high")
            }
        )

        # Store correlation result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="correlate",
            agent_id=self.agent_id,
            result=correlation_result
        )

        correlation_data = correlation_result.get("data", {})
        alerts = correlation_data.get("related_alerts", [])

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "correlation": {
                "total_alerts": len(alerts),
                "alerts": alerts[:10],  # Limit to top 10
                "time_window": time_window,
                "patterns_detected": correlation_data.get("patterns", []),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _assess_impact(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Assess incident impact.

        Determines which resources, services, and users are affected
        by the incident.

        Args:
            request: Impact assessment request
            context: Optional workflow context

        Returns:
            Impact analysis with affected resources and scope
        """
        incident_id = request["incident_id"]
        resource_ids = request.get("resource_ids", [])
        workflow_id = f"incident-{incident_id}"

        logger.info(f"Assessing impact for incident {incident_id}")

        # Step 3: Get resource dependencies
        impact_results = []

        for resource_id in resource_ids:
            try:
                deps_result = await self._call_tool(
                    "get_resource_dependencies",
                    {
                        "resource_id": resource_id
                    }
                )
                impact_results.append(deps_result)
            except Exception as exc:
                logger.warning(f"Failed to get dependencies for {resource_id}: {exc}")

        # Store impact assessment
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="impact",
            agent_id=self.agent_id,
            result={"dependencies": impact_results}
        )

        # Aggregate impact
        total_affected = len(resource_ids)
        downstream_resources = sum(
            len(r.get("data", {}).get("downstream", []))
            for r in impact_results
        )

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "impact": {
                "directly_affected": total_affected,
                "downstream_affected": downstream_resources,
                "total_resources_impacted": total_affected + downstream_resources,
                "blast_radius": "high" if downstream_resources > 10 else "medium" if downstream_resources > 5 else "low",
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _perform_rca(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform root cause analysis.

        Analyzes logs, metrics, and configuration to identify the
        root cause of the incident.

        Args:
            request: RCA request
            context: Optional workflow context

        Returns:
            Root cause analysis with likely causes and evidence
        """
        incident_id = request["incident_id"]
        workflow_id = f"incident-{incident_id}"

        logger.info(f"Performing RCA for incident {incident_id}")

        # Get context from previous steps
        workflow_context = await self.context_store.get_workflow_context(workflow_id)
        triage_data = workflow_context.get("steps", {}).get("triage", {})

        # Step 4: Search logs for errors
        log_search_result = await self._call_tool(
            "search_logs_by_error",
            {
                "error_pattern": request.get("error_pattern", "error|exception|failed"),
                "time_range": "1h"
            }
        )

        # Step 5: Analyze activity log
        activity_result = await self._call_tool(
            "analyze_activity_log",
            {
                "time_range": "1h",
                "resource_group": request.get("resource_group", "")
            }
        )

        # Store RCA results
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="rca",
            agent_id=self.agent_id,
            result={
                "log_search": log_search_result,
                "activity_log": activity_result
            }
        )

        # Extract potential root causes
        log_data = log_search_result.get("data", {})
        activity_data = activity_result.get("data", {})

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "rca": {
                "likely_causes": [
                    "Configuration change detected in activity log",
                    "Error patterns found in application logs",
                    "Resource constraints or throttling"
                ],
                "evidence": {
                    "log_errors_found": log_data.get("total_errors", 0),
                    "recent_changes": activity_data.get("change_count", 0),
                    "error_samples": log_data.get("samples", [])[:5]
                },
                "confidence": "medium",
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _recommend_remediation(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Recommend remediation actions.

        Based on RCA, suggests specific remediation steps.

        Args:
            request: Remediation request
            context: Optional workflow context

        Returns:
            Remediation recommendations with action plan
        """
        incident_id = request["incident_id"]
        workflow_id = f"incident-{incident_id}"

        logger.info(f"Recommending remediation for incident {incident_id}")

        # Step 6: Plan remediation
        remediation_result = await self._call_tool(
            "plan_remediation",
            {
                "issue_type": request.get("issue_type", "performance_degradation"),
                "affected_resources": request.get("affected_resources", [])
            }
        )

        # Store remediation plan
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="remediation",
            agent_id=self.agent_id,
            result=remediation_result
        )

        remediation_data = remediation_result.get("data", {})

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "remediation": {
                "recommended_actions": remediation_data.get("actions", []),
                "estimated_time": remediation_data.get("estimated_time", "unknown"),
                "risk_level": remediation_data.get("risk", "low"),
                "requires_approval": True,
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _generate_postmortem(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate incident postmortem.

        Creates a comprehensive postmortem document with timeline,
        root cause, impact, and lessons learned.

        Args:
            request: Postmortem request
            context: Optional workflow context

        Returns:
            Structured postmortem document
        """
        incident_id = request["incident_id"]
        workflow_id = f"incident-{incident_id}"

        logger.info(f"Generating postmortem for incident {incident_id}")

        # Get full workflow context
        workflow_context = await self.context_store.get_workflow_context(workflow_id)

        # Step 7: Generate postmortem
        postmortem_result = await self._call_tool(
            "generate_postmortem",
            {
                "incident_id": incident_id,
                "workflow_context": workflow_context
            }
        )

        # Step 8: Calculate MTTR metrics
        mttr_result = await self._call_tool(
            "calculate_mttr_metrics",
            {
                "time_range": "30d"
            }
        )

        postmortem_data = postmortem_result.get("data", {})
        mttr_data = mttr_result.get("data", {})

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": workflow_id,
            "postmortem": {
                "document": postmortem_data,
                "metrics": {
                    "mttr_minutes": mttr_data.get("mttr_minutes", 0),
                    "mttd_minutes": mttr_data.get("mttd_minutes", 0),
                    "incident_count_30d": mttr_data.get("incident_count", 0)
                },
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    async def _full_incident_response(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full incident response workflow.

        Runs all phases: triage → correlate → impact → RCA → remediation → postmortem

        Args:
            request: Full incident response request
            context: Optional workflow context

        Returns:
            Complete incident analysis and response plan
        """
        incident_id = request["incident_id"]

        logger.info(f"Starting full incident response for {incident_id}")

        # Phase 1: Triage
        triage_result = await self._triage_incident(request, context)

        # Phase 2: Correlate alerts
        correlate_result = await self._correlate_alerts(request, context)

        # Phase 3: Assess impact (if resource IDs provided)
        impact_result = None
        if request.get("resource_ids"):
            impact_result = await self._assess_impact(request, context)

        # Phase 4: Root cause analysis
        rca_result = await self._perform_rca(request, context)

        # Phase 5: Remediation recommendation
        remediation_result = await self._recommend_remediation(request, context)

        # Phase 6: Postmortem (if incident is resolved)
        postmortem_result = None
        if request.get("resolved", False):
            postmortem_result = await self._generate_postmortem(request, context)

        return {
            "status": "success",
            "incident_id": incident_id,
            "workflow_id": f"incident-{incident_id}",
            "phases": {
                "triage": triage_result,
                "correlation": correlate_result,
                "impact": impact_result,
                "rca": rca_result,
                "remediation": remediation_result,
                "postmortem": postmortem_result
            },
            "summary": {
                "severity": triage_result["triage"]["severity"],
                "total_alerts": correlate_result["correlation"]["total_alerts"],
                "blast_radius": impact_result["impact"]["blast_radius"] if impact_result else "unknown",
                "recommended_actions": len(remediation_result["remediation"]["recommended_actions"]),
                "completed_at": datetime.utcnow().isoformat()
            }
        }
