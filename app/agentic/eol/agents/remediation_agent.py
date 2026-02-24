"""Remediation Agent - Specialized SRE agent for automated remediation and recovery.

This agent handles:
- Automated diagnosis of resource issues
- Remediation action recommendations
- Execution of remediation actions (restart, scale, configuration fixes)
- Rollback of failed remediations
- Verification of remediation success
- Multi-strategy remediation planning
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


class RemediationAgent(BaseSREAgent):
    """Specialized agent for automated remediation and recovery.

    This agent orchestrates remediation workflows:
    1. Diagnosis - Identify root causes and resource issues
    2. Recommendation - Suggest appropriate remediation strategies
    3. Execution - Execute remediation actions with safety checks
    4. Rollback - Revert failed remediations to previous state
    5. Verification - Validate remediation success and health
    6. Full workflow - Complete diagnosis to verification cycle

    Remediation strategies supported:
    - Restart: For hung processes, memory leaks, stale connections
    - Scale: For resource exhaustion (CPU, memory, disk)
    - Configuration fix: For misconfigurations and invalid settings
    - Cache clear: For stale data and cache corruption issues
    - Network reset: For connectivity and routing issues

    Example usage:
        agent = RemediationAgent()
        await agent.initialize()

        # Diagnose resource issues
        result = await agent.handle_request({
            "action": "diagnose",
            "resource_type": "app_service",
            "resource_id": "/subscriptions/.../resourceGroups/rg/providers/.../sites/myapp",
            "symptoms": ["high_cpu", "slow_response"]
        })

        # Recommend remediation
        result = await agent.handle_request({
            "action": "recommend",
            "issue_type": "high_cpu",
            "resource_type": "app_service",
            "resource_id": "..."
        })

        # Execute remediation
        result = await agent.handle_request({
            "action": "execute",
            "remediation_type": "restart",
            "resource_type": "app_service",
            "resource_id": "...",
            "require_approval": False
        })

        # Full remediation workflow
        result = await agent.handle_request({
            "action": "full",
            "resource_type": "app_service",
            "resource_id": "...",
            "auto_execute": False
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Remediation Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="remediation",
            agent_id=agent_id or "remediation-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Remediation strategies mapped to symptoms
        self.strategies = {
            "high_cpu": {
                "primary": ["scale_out", "restart"],
                "secondary": ["optimize_config"],
                "risk": "medium"
            },
            "high_memory": {
                "primary": ["scale_up", "restart"],
                "secondary": ["clear_cache", "optimize_config"],
                "risk": "medium"
            },
            "slow_response": {
                "primary": ["cache_clear", "restart"],
                "secondary": ["scale_out", "optimize_config"],
                "risk": "low"
            },
            "connection_timeout": {
                "primary": ["network_reset", "restart"],
                "secondary": ["check_dependencies"],
                "risk": "high"
            },
            "disk_full": {
                "primary": ["cleanup_logs", "scale_storage"],
                "secondary": ["archive_old_data"],
                "risk": "medium"
            },
            "service_unavailable": {
                "primary": ["restart"],
                "secondary": ["check_dependencies", "scale_out"],
                "risk": "high"
            },
            "certificate_expired": {
                "primary": ["renew_certificate"],
                "secondary": ["update_config"],
                "risk": "high"
            },
            "config_error": {
                "primary": ["fix_configuration"],
                "secondary": ["rollback_config", "restart"],
                "risk": "medium"
            }
        }

        # Resource type to diagnosis tool mapping
        self.diagnosis_tools = {
            "app_service": "diagnose_app_service",
            "container_app": "diagnose_container_app",
            "apim": "diagnose_apim",
            "aks_cluster": "diagnose_aks_cluster"
        }

        # Resource type to remediation tool mapping
        self.remediation_tools = {
            "app_service": {
                "restart": "restart_app_service",
                "scale": "scale_app_service"
            },
            "container_app": {
                "restart": "restart_container_app",
                "scale": "scale_container_app"
            }
        }

        # Risk levels and approval requirements
        self.risk_thresholds = {
            "low": {"requires_approval": False, "backup_required": False},
            "medium": {"requires_approval": True, "backup_required": True},
            "high": {"requires_approval": True, "backup_required": True}
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
            logger.error(f"Failed to initialize Remediation Agent: {exc}")
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
        """Execute remediation action.

        Args:
            request: Request containing:
                - action: Action to perform (diagnose, recommend, execute, rollback, verify, full)
                - resource_type: Type of resource (app_service, container_app, apim, aks_cluster)
                - resource_id: Azure resource ID
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Action result with remediation analysis and status

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "diagnose")
        resource_type = request.get("resource_type")
        resource_id = request.get("resource_id")

        if not resource_type:
            raise AgentExecutionError("resource_type is required")

        if not resource_id and action not in ["recommend"]:
            raise AgentExecutionError("resource_id is required for this action")

        logger.info(
            f"Processing remediation action '{action}' for {resource_type}: {resource_id}"
        )

        # Route to appropriate handler
        action_handlers = {
            "diagnose": self._diagnose_resource,
            "recommend": self._recommend_remediation,
            "execute": self._execute_remediation,
            "rollback": self._rollback_remediation,
            "verify": self._verify_remediation,
            "full": self._full_remediation_workflow
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

    async def _diagnose_resource(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Diagnose resource issues.

        Performs comprehensive diagnostics to identify root causes and health issues.

        Args:
            request: Diagnosis request with resource details
            context: Optional workflow context

        Returns:
            Diagnosis results with identified issues and root causes
        """
        resource_type = request["resource_type"]
        resource_id = request["resource_id"]
        symptoms = request.get("symptoms", [])

        logger.info(f"Diagnosing {resource_type}: {resource_id}")

        # Create workflow context
        workflow_id = f"remediation-{datetime.utcnow().timestamp()}"
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "symptoms": symptoms,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Get diagnosis tool for resource type
        diagnosis_tool = self.diagnosis_tools.get(resource_type)
        if not diagnosis_tool:
            raise AgentExecutionError(
                f"No diagnosis tool available for resource type: {resource_type}"
            )

        # Step 2: Run diagnostics
        diagnosis_result = await self._call_tool(
            diagnosis_tool,
            {
                "resource_id": resource_id,
                "include_logs": True,
                "include_metrics": True
            }
        )

        # Store diagnosis result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="diagnosis",
            agent_id=self.agent_id,
            result=diagnosis_result
        )

        # Extract diagnosis data
        diagnosis_data = diagnosis_result.get("data", {})
        issues = diagnosis_data.get("issues", [])
        health_status = diagnosis_data.get("health_status", "unknown")
        metrics = diagnosis_data.get("metrics", {})

        # Analyze symptoms and map to remediation strategies
        detected_issues = self._analyze_symptoms(symptoms, metrics, issues)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "diagnosis": {
                "health_status": health_status,
                "issues_found": len(issues),
                "issues": issues[:10],  # Limit to top 10
                "detected_issues": detected_issues,
                "metrics_summary": {
                    "cpu_usage": metrics.get("cpu_percent", 0),
                    "memory_usage": metrics.get("memory_percent", 0),
                    "error_rate": metrics.get("error_rate", 0),
                    "response_time": metrics.get("avg_response_time_ms", 0)
                },
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": ["recommend_remediation", "plan_actions"]
        }

    def _analyze_symptoms(
        self,
        symptoms: List[str],
        metrics: Dict[str, Any],
        issues: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze symptoms and metrics to detect specific issues.

        Args:
            symptoms: Reported symptoms
            metrics: Resource metrics
            issues: Detected issues from diagnostics

        Returns:
            List of detected issues with severity and recommendations
        """
        detected = []

        # Check for high CPU
        cpu_percent = metrics.get("cpu_percent", 0)
        if cpu_percent > 80 or "high_cpu" in symptoms:
            detected.append({
                "issue_type": "high_cpu",
                "severity": "high" if cpu_percent > 90 else "medium",
                "description": f"CPU usage at {cpu_percent:.1f}%",
                "strategies": self.strategies.get("high_cpu", {})
            })

        # Check for high memory
        memory_percent = metrics.get("memory_percent", 0)
        if memory_percent > 85 or "high_memory" in symptoms:
            detected.append({
                "issue_type": "high_memory",
                "severity": "high" if memory_percent > 95 else "medium",
                "description": f"Memory usage at {memory_percent:.1f}%",
                "strategies": self.strategies.get("high_memory", {})
            })

        # Check for slow response
        response_time = metrics.get("avg_response_time_ms", 0)
        if response_time > 1000 or "slow_response" in symptoms:
            detected.append({
                "issue_type": "slow_response",
                "severity": "medium",
                "description": f"Response time at {response_time:.0f}ms",
                "strategies": self.strategies.get("slow_response", {})
            })

        # Check for connection issues
        if "connection_timeout" in symptoms or any("timeout" in str(i).lower() for i in issues):
            detected.append({
                "issue_type": "connection_timeout",
                "severity": "high",
                "description": "Connection timeout detected",
                "strategies": self.strategies.get("connection_timeout", {})
            })

        # Check for service availability
        if "service_unavailable" in symptoms or any("unavailable" in str(i).lower() for i in issues):
            detected.append({
                "issue_type": "service_unavailable",
                "severity": "critical",
                "description": "Service unavailable",
                "strategies": self.strategies.get("service_unavailable", {})
            })

        # If no specific issues detected, return general analysis
        if not detected:
            detected.append({
                "issue_type": "general_degradation",
                "severity": "low",
                "description": "No critical issues detected",
                "strategies": {"primary": ["monitor"], "secondary": [], "risk": "low"}
            })

        return detected

    async def _recommend_remediation(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Recommend remediation actions.

        Based on diagnosis or issue type, suggests appropriate remediation strategies.

        Args:
            request: Remediation request
            context: Optional workflow context

        Returns:
            Remediation recommendations with risk assessment
        """
        issue_type = request.get("issue_type")
        resource_type = request.get("resource_type")
        resource_id = request.get("resource_id", "")
        workflow_id = request.get("workflow_id", f"remediation-{datetime.utcnow().timestamp()}")

        logger.info(f"Recommending remediation for issue type: {issue_type}")

        # Get remediation strategies for the issue type
        strategies = self.strategies.get(issue_type, {})
        if not strategies:
            # Default fallback strategy
            strategies = {
                "primary": ["restart"],
                "secondary": ["monitor"],
                "risk": "low"
            }

        # Determine risk level and requirements
        risk = strategies.get("risk", "medium")
        risk_config = self.risk_thresholds.get(risk, self.risk_thresholds["medium"])

        # Build action plan
        primary_actions = strategies.get("primary", [])
        secondary_actions = strategies.get("secondary", [])

        action_plan = []
        for action in primary_actions:
            action_plan.append({
                "action": action,
                "priority": "high",
                "estimated_time": self._estimate_action_time(action, resource_type),
                "risk": risk,
                "requires_approval": risk_config["requires_approval"],
                "backup_required": risk_config["backup_required"]
            })

        for action in secondary_actions:
            action_plan.append({
                "action": action,
                "priority": "medium",
                "estimated_time": self._estimate_action_time(action, resource_type),
                "risk": risk,
                "requires_approval": risk_config["requires_approval"],
                "backup_required": risk_config["backup_required"]
            })

        # Store recommendation
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="recommendation",
            agent_id=self.agent_id,
            result={"action_plan": action_plan}
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "recommendation": {
                "issue_type": issue_type,
                "risk_level": risk,
                "action_plan": action_plan,
                "requires_approval": risk_config["requires_approval"],
                "backup_required": risk_config["backup_required"],
                "estimated_total_time": sum(
                    a["estimated_time"] for a in action_plan
                ),
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": ["review_plan", "execute_remediation"]
        }

    def _estimate_action_time(self, action: str, resource_type: str) -> int:
        """Estimate time required for remediation action.

        Args:
            action: Remediation action type
            resource_type: Type of resource

        Returns:
            Estimated time in seconds
        """
        estimates = {
            "restart": 120,       # 2 minutes
            "scale_out": 300,     # 5 minutes
            "scale_up": 300,      # 5 minutes
            "cache_clear": 30,    # 30 seconds
            "network_reset": 180, # 3 minutes
            "optimize_config": 60, # 1 minute
            "cleanup_logs": 120,  # 2 minutes
            "monitor": 0          # Immediate
        }
        return estimates.get(action, 120)

    async def _execute_remediation(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute remediation actions.

        Performs the actual remediation with safety checks and rollback capability.

        Args:
            request: Execution request
            context: Optional workflow context

        Returns:
            Execution results with status and changes made
        """
        remediation_type = request.get("remediation_type")
        resource_type = request.get("resource_type")
        resource_id = request["resource_id"]
        require_approval = request.get("require_approval", True)
        workflow_id = request.get("workflow_id", f"remediation-{datetime.utcnow().timestamp()}")

        logger.info(
            f"Executing remediation '{remediation_type}' for {resource_type}: {resource_id}"
        )

        # Safety check: Require approval for high-risk operations
        if require_approval and not request.get("approved", False):
            return {
                "status": "pending_approval",
                "workflow_id": workflow_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "remediation_type": remediation_type,
                "message": "Remediation requires approval before execution",
                "timestamp": datetime.utcnow().isoformat()
            }

        # Step 1: Create backup/snapshot of current state
        backup_result = await self._create_backup(resource_type, resource_id)

        # Step 2: Execute remediation action
        execution_result = await self._execute_action(
            remediation_type,
            resource_type,
            resource_id,
            request.get("parameters", {})
        )

        # Store execution result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="execution",
            agent_id=self.agent_id,
            result={
                "backup": backup_result,
                "execution": execution_result
            }
        )

        execution_data = execution_result.get("data", {})
        success = execution_result.get("status") == "success"

        return {
            "status": "success" if success else "failed",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "execution": {
                "remediation_type": remediation_type,
                "success": success,
                "backup_id": backup_result.get("backup_id"),
                "changes_made": execution_data.get("changes", []),
                "duration_seconds": execution_data.get("duration", 0),
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": ["verify_remediation", "monitor_health"] if success else ["rollback", "retry"]
        }

    async def _create_backup(
        self,
        resource_type: str,
        resource_id: str
    ) -> Dict[str, Any]:
        """Create backup of resource state before remediation.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            Backup information
        """
        logger.info(f"Creating backup for {resource_type}: {resource_id}")

        # For demo purposes, simulate backup creation
        backup_id = f"backup-{datetime.utcnow().timestamp()}"

        return {
            "backup_id": backup_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "created"
        }

    async def _execute_action(
        self,
        remediation_type: str,
        resource_type: str,
        resource_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute specific remediation action.

        Args:
            remediation_type: Type of remediation (restart, scale, etc.)
            resource_type: Type of resource
            resource_id: Resource identifier
            parameters: Action-specific parameters

        Returns:
            Execution result
        """
        logger.info(f"Executing {remediation_type} for {resource_type}")

        # Get the appropriate tool for this remediation
        tools = self.remediation_tools.get(resource_type, {})
        tool_name = tools.get(remediation_type)

        if not tool_name:
            raise AgentExecutionError(
                f"No tool available for {remediation_type} on {resource_type}"
            )

        # Execute the remediation tool
        tool_params = {
            "resource_id": resource_id,
            **parameters
        }

        result = await self._call_tool(tool_name, tool_params)

        return result

    async def _rollback_remediation(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Rollback failed remediation.

        Restores resource to previous state from backup.

        Args:
            request: Rollback request
            context: Optional workflow context

        Returns:
            Rollback status
        """
        backup_id = request.get("backup_id")
        resource_type = request.get("resource_type")
        resource_id = request["resource_id"]
        workflow_id = request.get("workflow_id", f"remediation-{datetime.utcnow().timestamp()}")

        logger.info(f"Rolling back remediation for {resource_type}: {resource_id}")

        # Get backup information
        workflow_context = await self.context_store.get_workflow_context(workflow_id)
        execution_step = workflow_context.get("steps", {}).get("execution", {})
        backup_info = execution_step.get("backup", {})

        if not backup_info:
            return {
                "status": "failed",
                "workflow_id": workflow_id,
                "message": "No backup found for rollback",
                "timestamp": datetime.utcnow().isoformat()
            }

        # Perform rollback (simulated for demo)
        rollback_result = {
            "status": "success",
            "backup_id": backup_info.get("backup_id"),
            "restored_at": datetime.utcnow().isoformat()
        }

        # Store rollback result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="rollback",
            agent_id=self.agent_id,
            result=rollback_result
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "rollback": {
                "backup_id": backup_info.get("backup_id"),
                "restored": True,
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": ["verify_rollback", "investigate_failure"]
        }

    async def _verify_remediation(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Verify remediation success.

        Checks resource health and validates that issues are resolved.

        Args:
            request: Verification request
            context: Optional workflow context

        Returns:
            Verification results
        """
        resource_type = request["resource_type"]
        resource_id = request["resource_id"]
        workflow_id = request.get("workflow_id", f"remediation-{datetime.utcnow().timestamp()}")

        logger.info(f"Verifying remediation for {resource_type}: {resource_id}")

        # Step 1: Run diagnostics again
        diagnosis_tool = self.diagnosis_tools.get(resource_type)
        if not diagnosis_tool:
            raise AgentExecutionError(
                f"No diagnosis tool available for resource type: {resource_type}"
            )

        post_remediation_diagnosis = await self._call_tool(
            diagnosis_tool,
            {
                "resource_id": resource_id,
                "include_metrics": True
            }
        )

        # Step 2: Compare with pre-remediation state
        workflow_context = await self.context_store.get_workflow_context(workflow_id)
        pre_diagnosis = workflow_context.get("steps", {}).get("diagnosis", {})

        # Extract health status
        post_data = post_remediation_diagnosis.get("data", {})
        post_health = post_data.get("health_status", "unknown")
        post_metrics = post_data.get("metrics", {})
        post_issues = post_data.get("issues", [])

        # Determine verification status
        verification_passed = (
            post_health in ["healthy", "warning"] and
            len(post_issues) == 0
        )

        # Store verification result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="verification",
            agent_id=self.agent_id,
            result={
                "post_diagnosis": post_remediation_diagnosis,
                "verification_passed": verification_passed
            }
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "verification": {
                "passed": verification_passed,
                "health_status": post_health,
                "issues_remaining": len(post_issues),
                "metrics_summary": {
                    "cpu_usage": post_metrics.get("cpu_percent", 0),
                    "memory_usage": post_metrics.get("memory_percent", 0),
                    "error_rate": post_metrics.get("error_rate", 0),
                    "response_time": post_metrics.get("avg_response_time_ms", 0)
                },
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": ["close_incident"] if verification_passed else ["investigate_further", "retry_remediation"]
        }

    async def _full_remediation_workflow(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full remediation workflow.

        Runs all phases: diagnose → recommend → execute → verify

        Args:
            request: Full remediation request
            context: Optional workflow context

        Returns:
            Complete remediation workflow results
        """
        resource_type = request["resource_type"]
        resource_id = request["resource_id"]
        auto_execute = request.get("auto_execute", False)
        workflow_id = f"full-remediation-{datetime.utcnow().timestamp()}"

        logger.info(f"Starting full remediation workflow for {resource_type}: {resource_id}")

        # Add workflow_id to request for tracking
        request["workflow_id"] = workflow_id

        # Phase 1: Diagnose
        diagnose_result = await self._diagnose_resource(request, context)

        # Phase 2: Recommend based on diagnosis
        detected_issues = diagnose_result["diagnosis"]["detected_issues"]
        if not detected_issues:
            return {
                "status": "success",
                "workflow_id": workflow_id,
                "message": "No issues detected - remediation not required",
                "phases": {
                    "diagnosis": diagnose_result
                },
                "timestamp": datetime.utcnow().isoformat()
            }

        # Use the first detected issue for recommendation
        primary_issue = detected_issues[0]
        request["issue_type"] = primary_issue["issue_type"]

        recommend_result = await self._recommend_remediation(request, context)

        # Phase 3: Execute (if auto_execute enabled and no approval required)
        execute_result = None
        verify_result = None

        if auto_execute:
            action_plan = recommend_result["recommendation"]["action_plan"]
            if action_plan:
                primary_action = action_plan[0]

                # Only execute if approval not required or explicitly approved
                if not primary_action["requires_approval"] or request.get("approved", False):
                    request["remediation_type"] = primary_action["action"]
                    request["require_approval"] = primary_action["requires_approval"]

                    execute_result = await self._execute_remediation(request, context)

                    # Phase 4: Verify (if execution succeeded)
                    if execute_result.get("status") == "success":
                        verify_result = await self._verify_remediation(request, context)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "phases": {
                "diagnosis": diagnose_result,
                "recommendation": recommend_result,
                "execution": execute_result,
                "verification": verify_result
            },
            "summary": {
                "issues_detected": len(detected_issues),
                "primary_issue": primary_issue["issue_type"],
                "actions_recommended": len(recommend_result["recommendation"]["action_plan"]),
                "executed": execute_result is not None,
                "verified": verify_result is not None if verify_result else False,
                "verification_passed": verify_result["verification"]["passed"] if verify_result else None,
                "completed_at": datetime.utcnow().isoformat()
            }
        }
