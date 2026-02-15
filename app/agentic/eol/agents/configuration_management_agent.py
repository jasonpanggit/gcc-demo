"""Configuration Management Agent - Specialized SRE agent for configuration tracking and compliance.

This agent handles:
- Configuration scanning across resources
- Configuration drift detection
- Policy compliance checking
- Configuration remediation
- Baseline management
- Configuration change tracking
- Compliance reporting
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


class ConfigurationManagementAgent(BaseSREAgent):
    """Specialized agent for configuration management and compliance.

    This agent orchestrates configuration management workflows:
    1. Configuration scanning (inventory and settings)
    2. Drift detection (comparison against baseline)
    3. Policy compliance checking (security, governance)
    4. Configuration remediation (apply fixes)
    5. Baseline management (create/update standards)
    6. Change tracking (audit trail)
    7. Compliance reporting (violations, trends)

    Example usage:
        agent = ConfigurationManagementAgent()
        await agent.initialize()

        # Scan resource configuration
        result = await agent.handle_request({
            "action": "scan",
            "resource_id": "/subscriptions/.../resourceGroups/rg/providers/...",
            "include_settings": True
        })

        # Detect configuration drift
        result = await agent.handle_request({
            "action": "drift",
            "resource_id": "...",
            "baseline_id": "baseline-prod-2024"
        })

        # Check compliance
        result = await agent.handle_request({
            "action": "compliance",
            "resource_group": "prod-rg",
            "policies": ["security", "tagging", "encryption"]
        })

        # Remediate configuration issues
        result = await agent.handle_request({
            "action": "remediate",
            "resource_id": "...",
            "drift_items": ["encryption", "network_rules"],
            "dry_run": True
        })

        # Create configuration baseline
        result = await agent.handle_request({
            "action": "baseline",
            "baseline_name": "prod-baseline-v2",
            "resource_group": "prod-rg",
            "include_tags": True
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Configuration Management Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="configuration-management",
            agent_id=agent_id or "configuration-management-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Configuration compliance levels
        self.compliance_levels = {
            "critical": {"priority": 1, "remediation_required": True},
            "high": {"priority": 2, "remediation_required": True},
            "medium": {"priority": 3, "remediation_required": False},
            "low": {"priority": 4, "remediation_required": False},
            "informational": {"priority": 5, "remediation_required": False}
        }

        # Drift severity thresholds
        self.drift_thresholds = {
            "critical": 0.0,    # Any critical setting changed
            "high": 0.1,        # >10% of high-impact settings changed
            "medium": 0.25,     # >25% of medium-impact settings changed
            "low": 0.5          # >50% of low-impact settings changed
        }

        # Configuration categories
        self.config_categories = [
            "security",
            "networking",
            "storage",
            "compute",
            "monitoring",
            "tagging",
            "access_control",
            "encryption",
            "backup",
            "disaster_recovery"
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
            logger.error(f"Failed to initialize Configuration Management Agent: {exc}")
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
        """Execute configuration management action.

        Args:
            request: Request containing:
                - action: Action to perform (scan, drift, compliance, remediate, baseline, full)
                - resource_id: Azure resource ID (optional)
                - resource_group: Resource group name (optional)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Action result with configuration analysis and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "scan")

        logger.info(f"Processing configuration management action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "scan": self._scan_configuration,
            "drift": self._detect_drift,
            "compliance": self._check_compliance,
            "remediate": self._remediate_configuration,
            "baseline": self._manage_baseline,
            "full": self._full_configuration_analysis
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

    async def _scan_configuration(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Scan resource configuration.

        Retrieves current configuration settings for specified resources.

        Args:
            request: Scan request with resource identifiers
            context: Optional workflow context

        Returns:
            Configuration scan results
        """
        resource_id = request.get("resource_id", "")
        resource_group = request.get("resource_group", "")
        include_settings = request.get("include_settings", True)
        workflow_id = request.get("workflow_id", f"config-scan-{datetime.utcnow().timestamp()}")

        logger.info(f"Scanning configuration for {resource_id or resource_group or 'all resources'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "resource_group": resource_group,
                "include_settings": include_settings,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Check resource configuration
        config_result = await self._call_tool(
            "check_resource_configuration",
            {
                "resource_id": resource_id,
                "resource_group": resource_group,
                "include_security_settings": True,
                "include_network_settings": True,
                "include_tags": True
            }
        )

        # Store configuration scan result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="scan",
            agent_id=self.agent_id,
            result=config_result
        )

        # Extract and categorize configuration data
        config_data = config_result.get("data", {})
        categorized_config = self._categorize_configuration(config_data)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "resource_group": resource_group,
            "scan": {
                "configuration": categorized_config,
                "total_settings": len(config_data.get("settings", {})),
                "categories": list(categorized_config.keys()),
                "scan_timestamp": datetime.utcnow().isoformat(),
                "raw_data": config_data
            }
        }

    def _categorize_configuration(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Categorize configuration settings by type.

        Args:
            config_data: Raw configuration data

        Returns:
            Categorized configuration dictionary
        """
        categorized = {category: {} for category in self.config_categories}

        settings = config_data.get("settings", {})

        # Categorize based on setting names/patterns
        for key, value in settings.items():
            key_lower = key.lower()

            if any(term in key_lower for term in ["encrypt", "ssl", "tls", "certificate"]):
                categorized["encryption"][key] = value
            elif any(term in key_lower for term in ["network", "subnet", "vnet", "ip", "firewall"]):
                categorized["networking"][key] = value
            elif any(term in key_lower for term in ["security", "auth", "access", "permission"]):
                categorized["security"][key] = value
            elif any(term in key_lower for term in ["storage", "disk", "volume"]):
                categorized["storage"][key] = value
            elif any(term in key_lower for term in ["compute", "cpu", "memory", "vm"]):
                categorized["compute"][key] = value
            elif any(term in key_lower for term in ["monitor", "log", "diagnostic", "alert"]):
                categorized["monitoring"][key] = value
            elif any(term in key_lower for term in ["tag", "label", "metadata"]):
                categorized["tagging"][key] = value
            elif any(term in key_lower for term in ["backup", "snapshot", "restore"]):
                categorized["backup"][key] = value
            elif any(term in key_lower for term in ["disaster", "recovery", "dr", "failover"]):
                categorized["disaster_recovery"][key] = value
            elif any(term in key_lower for term in ["role", "rbac", "identity", "principal"]):
                categorized["access_control"][key] = value

        # Remove empty categories
        return {k: v for k, v in categorized.items() if v}

    async def _detect_drift(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Detect configuration drift from baseline.

        Compares current configuration against established baseline to identify changes.

        Args:
            request: Drift detection request
            context: Optional workflow context

        Returns:
            Drift detection results with changes identified
        """
        resource_id = request.get("resource_id", "")
        baseline_id = request.get("baseline_id", "")
        resource_group = request.get("resource_group", "")
        workflow_id = request.get("workflow_id", f"config-drift-{datetime.utcnow().timestamp()}")

        logger.info(f"Detecting configuration drift for {resource_id or resource_group}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "baseline_id": baseline_id,
                "resource_group": resource_group,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 2: Detect configuration drift
        drift_result = await self._call_tool(
            "detect_configuration_drift",
            {
                "resource_id": resource_id,
                "resource_group": resource_group,
                "baseline_id": baseline_id,
                "threshold": request.get("threshold", 0.0)
            }
        )

        # Store drift detection result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="drift",
            agent_id=self.agent_id,
            result=drift_result
        )

        # Analyze drift severity
        drift_data = drift_result.get("data", {})
        drift_items = drift_data.get("drift_items", [])
        severity = self._calculate_drift_severity(drift_items)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "baseline_id": baseline_id,
            "drift": {
                "detected": len(drift_items) > 0,
                "total_changes": len(drift_items),
                "severity": severity,
                "drift_items": drift_items,
                "drift_percentage": drift_data.get("drift_percentage", 0.0),
                "categories_affected": self._categorize_drift_items(drift_items),
                "requires_remediation": severity in ["critical", "high"],
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_drift_recommendations(drift_items, severity)
        }

    def _calculate_drift_severity(self, drift_items: List[Dict]) -> str:
        """Calculate overall drift severity.

        Args:
            drift_items: List of configuration drift items

        Returns:
            Severity level (critical, high, medium, low)
        """
        if not drift_items:
            return "none"

        # Check for critical security changes
        critical_patterns = ["encryption", "authentication", "firewall", "access"]
        for item in drift_items:
            setting_name = item.get("setting", "").lower()
            if any(pattern in setting_name for pattern in critical_patterns):
                if item.get("impact", "medium") == "critical":
                    return "critical"

        # Count items by impact
        high_impact = sum(1 for item in drift_items if item.get("impact") == "high")
        medium_impact = sum(1 for item in drift_items if item.get("impact") == "medium")

        total_items = len(drift_items)
        high_ratio = high_impact / total_items if total_items > 0 else 0

        if high_ratio >= self.drift_thresholds["high"]:
            return "high"
        elif high_ratio >= self.drift_thresholds["medium"]:
            return "medium"
        else:
            return "low"

    def _categorize_drift_items(self, drift_items: List[Dict]) -> List[str]:
        """Categorize drift items by configuration category.

        Args:
            drift_items: List of drift items

        Returns:
            List of affected categories
        """
        affected_categories = set()

        for item in drift_items:
            setting = item.get("setting", "").lower()

            for category in self.config_categories:
                if category in setting:
                    affected_categories.add(category)

        return sorted(list(affected_categories))

    def _generate_drift_recommendations(
        self,
        drift_items: List[Dict],
        severity: str
    ) -> List[str]:
        """Generate recommendations based on detected drift.

        Args:
            drift_items: List of drift items
            severity: Overall drift severity

        Returns:
            List of recommendations
        """
        recommendations = []

        if severity == "critical":
            recommendations.append("⚠️ Critical configuration drift detected - immediate remediation required")
            recommendations.append("Review security settings and access controls")
            recommendations.append("Verify encryption and network security configurations")
        elif severity == "high":
            recommendations.append("High-priority configuration drift detected - remediation recommended")
            recommendations.append("Schedule configuration review and update")
        elif severity == "medium":
            recommendations.append("Medium-priority drift detected - review during next maintenance window")
        elif severity == "low":
            recommendations.append("Low-priority drift detected - monitor for trends")

        # Category-specific recommendations
        categories = self._categorize_drift_items(drift_items)
        if "security" in categories:
            recommendations.append("Update security baseline and policies")
        if "networking" in categories:
            recommendations.append("Review network configuration and firewall rules")
        if "tagging" in categories:
            recommendations.append("Standardize resource tagging across environment")

        return recommendations

    async def _check_compliance(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check policy compliance.

        Validates resources against defined compliance policies.

        Args:
            request: Compliance check request
            context: Optional workflow context

        Returns:
            Compliance check results with violations
        """
        resource_id = request.get("resource_id", "")
        resource_group = request.get("resource_group", "")
        policies = request.get("policies", [])
        workflow_id = request.get("workflow_id", f"config-compliance-{datetime.utcnow().timestamp()}")

        logger.info(f"Checking compliance for {resource_id or resource_group}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "resource_group": resource_group,
                "policies": policies,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 3: Get policy compliance status
        compliance_result = await self._call_tool(
            "get_policy_compliance_status",
            {
                "resource_id": resource_id,
                "resource_group": resource_group,
                "policy_names": policies
            }
        )

        # Store compliance result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="compliance",
            agent_id=self.agent_id,
            result=compliance_result
        )

        # Analyze compliance data
        compliance_data = compliance_result.get("data", {})
        violations = compliance_data.get("violations", [])
        compliance_summary = self._analyze_compliance_data(compliance_data)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "resource_group": resource_group,
            "compliance": {
                "compliant": len(violations) == 0,
                "total_policies_checked": len(policies) if policies else compliance_data.get("total_policies", 0),
                "violations_found": len(violations),
                "violations": violations,
                "compliance_score": compliance_summary["score"],
                "severity_breakdown": compliance_summary["severity_breakdown"],
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_compliance_recommendations(violations)
        }

    def _analyze_compliance_data(self, compliance_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze compliance data and calculate score.

        Args:
            compliance_data: Raw compliance data

        Returns:
            Compliance analysis summary
        """
        violations = compliance_data.get("violations", [])
        total_policies = compliance_data.get("total_policies", 1)

        # Count violations by severity
        severity_breakdown = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0
        }

        for violation in violations:
            severity = violation.get("severity", "medium")
            severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1

        # Calculate compliance score (0-100)
        # Critical violations weigh heavily
        violations_count = len(violations)
        critical_weight = severity_breakdown["critical"] * 10
        high_weight = severity_breakdown["high"] * 5
        medium_weight = severity_breakdown["medium"] * 2
        low_weight = severity_breakdown["low"] * 1

        total_weight = critical_weight + high_weight + medium_weight + low_weight
        max_possible_weight = total_policies * 10  # Assuming all could be critical

        compliance_score = max(0, 100 - (total_weight / max(max_possible_weight, 1) * 100))

        return {
            "score": round(compliance_score, 2),
            "severity_breakdown": severity_breakdown,
            "total_violations": violations_count
        }

    def _generate_compliance_recommendations(self, violations: List[Dict]) -> List[str]:
        """Generate recommendations based on compliance violations.

        Args:
            violations: List of compliance violations

        Returns:
            List of recommendations
        """
        recommendations = []

        if not violations:
            recommendations.append("✓ All compliance checks passed")
            return recommendations

        # Count by severity
        critical_count = sum(1 for v in violations if v.get("severity") == "critical")
        high_count = sum(1 for v in violations if v.get("severity") == "high")

        if critical_count > 0:
            recommendations.append(f"⚠️ {critical_count} critical compliance violation(s) require immediate attention")
            recommendations.append("Address critical violations before proceeding with deployments")

        if high_count > 0:
            recommendations.append(f"⚠️ {high_count} high-priority compliance violation(s) detected")
            recommendations.append("Schedule remediation during next maintenance window")

        # Policy-specific recommendations
        policy_types = set(v.get("policy_type", "") for v in violations)
        if "security" in policy_types:
            recommendations.append("Review and update security policies")
        if "encryption" in policy_types:
            recommendations.append("Enable encryption for non-compliant resources")
        if "tagging" in policy_types:
            recommendations.append("Apply required tags to all resources")
        if "networking" in policy_types:
            recommendations.append("Review and remediate network security configurations")

        return recommendations

    async def _remediate_configuration(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Apply configuration fixes.

        Remediates configuration drift or compliance violations.

        Args:
            request: Remediation request
            context: Optional workflow context

        Returns:
            Remediation results
        """
        resource_id = request.get("resource_id", "")
        configuration_fixes = request.get("configuration_fixes", {})
        dry_run = request.get("dry_run", True)
        workflow_id = request.get("workflow_id", f"config-remediate-{datetime.utcnow().timestamp()}")

        logger.info(f"Remediating configuration for {resource_id} (dry_run={dry_run})")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_id": resource_id,
                "configuration_fixes": configuration_fixes,
                "dry_run": dry_run,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 4: Apply configuration fix
        remediation_result = await self._call_tool(
            "apply_configuration_fix",
            {
                "resource_id": resource_id,
                "configuration_fixes": configuration_fixes,
                "dry_run": dry_run,
                "validate_before_apply": True
            }
        )

        # Store remediation result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="remediate",
            agent_id=self.agent_id,
            result=remediation_result
        )

        remediation_data = remediation_result.get("data", {})

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "resource_id": resource_id,
            "remediation": {
                "dry_run": dry_run,
                "applied": not dry_run,
                "changes_planned": len(configuration_fixes),
                "changes_applied": remediation_data.get("changes_applied", 0),
                "changes_failed": remediation_data.get("changes_failed", 0),
                "validation_passed": remediation_data.get("validation_passed", False),
                "details": remediation_data.get("details", []),
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": [
                "Verify configuration changes",
                "Run compliance check",
                "Update configuration baseline"
            ] if not dry_run else [
                "Review planned changes",
                "Execute remediation with dry_run=False",
                "Monitor for drift recurrence"
            ]
        }

    async def _manage_baseline(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create or update configuration baseline.

        Establishes a baseline configuration for drift detection.

        Args:
            request: Baseline management request
            context: Optional workflow context

        Returns:
            Baseline management results
        """
        baseline_name = request.get("baseline_name", "")
        resource_group = request.get("resource_group", "")
        resource_ids = request.get("resource_ids", [])
        baseline_id = request.get("baseline_id", "")
        operation = request.get("operation", "create")  # create or update
        workflow_id = request.get("workflow_id", f"config-baseline-{datetime.utcnow().timestamp()}")

        logger.info(f"Managing baseline: {operation} {baseline_name or baseline_id}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "baseline_name": baseline_name,
                "baseline_id": baseline_id,
                "resource_group": resource_group,
                "operation": operation,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 5: Create or update configuration baseline
        baseline_result = await self._call_tool(
            "create_configuration_baseline",
            {
                "baseline_name": baseline_name,
                "baseline_id": baseline_id,
                "resource_group": resource_group,
                "resource_ids": resource_ids,
                "include_tags": request.get("include_tags", True),
                "include_security_settings": request.get("include_security_settings", True),
                "description": request.get("description", "")
            }
        )

        # Store baseline result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="baseline",
            agent_id=self.agent_id,
            result=baseline_result
        )

        baseline_data = baseline_result.get("data", {})

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "baseline": {
                "baseline_id": baseline_data.get("baseline_id", baseline_id),
                "baseline_name": baseline_name,
                "operation": operation,
                "resources_included": len(resource_ids) if resource_ids else baseline_data.get("resource_count", 0),
                "settings_captured": baseline_data.get("settings_count", 0),
                "categories": baseline_data.get("categories", []),
                "created_at": baseline_data.get("created_at", datetime.utcnow().isoformat()),
                "version": baseline_data.get("version", "1.0")
            },
            "next_steps": [
                "Use baseline for drift detection",
                "Schedule periodic compliance checks",
                "Update baseline as environment evolves"
            ]
        }

    async def _full_configuration_analysis(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full configuration management workflow.

        Runs all phases: scan → drift → compliance → remediate (if needed) → baseline update

        Args:
            request: Full analysis request
            context: Optional workflow context

        Returns:
            Complete configuration analysis report
        """
        workflow_id = f"full-config-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        logger.info(f"Starting full configuration analysis: {workflow_id}")

        # Phase 1: Scan configuration
        scan_result = await self._scan_configuration(request, context)

        # Phase 2: Detect drift (if baseline exists)
        drift_result = None
        if request.get("baseline_id"):
            drift_result = await self._detect_drift(request, context)

        # Phase 3: Check compliance
        compliance_result = await self._check_compliance(request, context)

        # Phase 4: Remediate (if violations found and auto_remediate enabled)
        remediation_result = None
        if compliance_result["compliance"]["violations_found"] > 0:
            if request.get("auto_remediate", False):
                # Extract fixes from violations
                violations = compliance_result["compliance"]["violations"]
                configuration_fixes = self._extract_fixes_from_violations(violations)

                remediation_request = {
                    **request,
                    "configuration_fixes": configuration_fixes,
                    "dry_run": request.get("dry_run", True)
                }
                remediation_result = await self._remediate_configuration(
                    remediation_request,
                    context
                )

        # Phase 5: Update baseline (if requested)
        baseline_result = None
        if request.get("update_baseline", False):
            baseline_result = await self._manage_baseline(request, context)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "phases": {
                "scan": scan_result,
                "drift": drift_result,
                "compliance": compliance_result,
                "remediation": remediation_result,
                "baseline": baseline_result
            },
            "summary": {
                "total_settings_scanned": scan_result.get("scan", {}).get("total_settings", 0),
                "drift_detected": drift_result.get("drift", {}).get("detected", False) if drift_result else None,
                "drift_severity": drift_result.get("drift", {}).get("severity", "none") if drift_result else None,
                "compliance_score": compliance_result.get("compliance", {}).get("compliance_score", 0),
                "violations_found": compliance_result.get("compliance", {}).get("violations_found", 0),
                "remediation_applied": remediation_result.get("remediation", {}).get("applied", False) if remediation_result else False,
                "baseline_updated": baseline_result is not None,
                "overall_health": self._calculate_overall_health(
                    scan_result,
                    drift_result,
                    compliance_result
                ),
                "completed_at": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_overall_recommendations(
                scan_result,
                drift_result,
                compliance_result,
                remediation_result
            )
        }

    def _extract_fixes_from_violations(self, violations: List[Dict]) -> Dict[str, Any]:
        """Extract configuration fixes from compliance violations.

        Args:
            violations: List of compliance violations

        Returns:
            Dictionary of configuration fixes
        """
        fixes = {}

        for violation in violations:
            setting = violation.get("setting", "")
            recommended_value = violation.get("recommended_value")

            if setting and recommended_value is not None:
                fixes[setting] = recommended_value

        return fixes

    def _calculate_overall_health(
        self,
        scan_result: Dict[str, Any],
        drift_result: Optional[Dict[str, Any]],
        compliance_result: Dict[str, Any]
    ) -> str:
        """Calculate overall configuration health.

        Args:
            scan_result: Configuration scan results
            drift_result: Drift detection results (optional)
            compliance_result: Compliance check results

        Returns:
            Overall health status (excellent, good, fair, poor, critical)
        """
        compliance_score = compliance_result.get("compliance", {}).get("compliance_score", 0)
        violations_count = compliance_result.get("compliance", {}).get("violations_found", 0)

        drift_severity = "none"
        if drift_result:
            drift_severity = drift_result.get("drift", {}).get("severity", "none")

        # Determine health based on compliance and drift
        if compliance_score >= 95 and drift_severity in ["none", "low"]:
            return "excellent"
        elif compliance_score >= 85 and drift_severity in ["none", "low", "medium"]:
            return "good"
        elif compliance_score >= 70 and drift_severity != "critical":
            return "fair"
        elif drift_severity == "critical" or compliance_score < 50:
            return "critical"
        else:
            return "poor"

    def _generate_overall_recommendations(
        self,
        scan_result: Dict[str, Any],
        drift_result: Optional[Dict[str, Any]],
        compliance_result: Dict[str, Any],
        remediation_result: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate overall recommendations from all analysis phases.

        Args:
            scan_result: Configuration scan results
            drift_result: Drift detection results (optional)
            compliance_result: Compliance check results
            remediation_result: Remediation results (optional)

        Returns:
            List of prioritized recommendations
        """
        recommendations = []

        # Compliance recommendations
        violations_count = compliance_result.get("compliance", {}).get("violations_found", 0)
        if violations_count > 0:
            recommendations.extend(compliance_result.get("recommendations", []))

        # Drift recommendations
        if drift_result and drift_result.get("drift", {}).get("detected"):
            recommendations.extend(drift_result.get("recommendations", []))

        # Remediation follow-up
        if remediation_result:
            dry_run = remediation_result.get("remediation", {}).get("dry_run", True)
            if dry_run:
                recommendations.append("Execute remediation to apply configuration fixes")
            else:
                recommendations.append("Verify remediation changes and monitor for stability")

        # General best practices
        recommendations.extend([
            "Schedule regular configuration audits",
            "Implement automated drift detection",
            "Maintain up-to-date configuration baselines",
            "Document configuration standards and policies"
        ])

        return recommendations
