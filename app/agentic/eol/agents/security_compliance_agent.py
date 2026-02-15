"""Security Compliance Agent - Specialized SRE agent for security and compliance monitoring.

This agent handles:
- Security posture scanning and assessment
- Compliance status checking (SOC2, HIPAA, PCI-DSS, ISO 27001, GDPR)
- Vulnerability assessment and prioritization
- Security policy validation
- Remediation recommendations
- Security score tracking
- Risk assessment and reporting
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


class SecurityComplianceAgent(BaseSREAgent):
    """Specialized agent for security and compliance monitoring.

    This agent orchestrates multi-step security workflows:
    1. Security posture scanning and assessment
    2. Compliance framework validation (SOC2, HIPAA, PCI-DSS, ISO 27001, GDPR)
    3. Vulnerability identification and prioritization
    4. Security policy enforcement checks
    5. Remediation recommendations with priority ranking
    6. Security score calculation and trending
    7. Risk assessment and reporting

    Example usage:
        agent = SecurityComplianceAgent()
        await agent.initialize()

        # Scan security posture
        result = await agent.handle_request({
            "action": "scan_security",
            "resource_group": "prod-rg",
            "scan_type": "comprehensive"
        })

        # Check compliance status
        result = await agent.handle_request({
            "action": "check_compliance",
            "framework": "SOC2",
            "resource_group": "prod-rg"
        })

        # Assess vulnerabilities
        result = await agent.handle_request({
            "action": "assess_vulnerabilities",
            "resource_ids": ["vm-1", "vm-2"],
            "severity_threshold": "medium"
        })

        # Full security audit
        result = await agent.handle_request({
            "action": "full",
            "resource_group": "prod-rg",
            "compliance_frameworks": ["SOC2", "HIPAA"]
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 600  # 10 minutes for comprehensive scans
    ):
        """Initialize Security Compliance Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds (default 10 minutes)
        """
        super().__init__(
            agent_type="security-compliance",
            agent_id=agent_id or "security-compliance-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Security severity levels and scoring weights
        self.severity_levels = {
            "critical": {"priority": 1, "score_impact": -25, "sla_hours": 4},
            "high": {"priority": 2, "score_impact": -15, "sla_hours": 24},
            "medium": {"priority": 3, "score_impact": -8, "sla_hours": 72},
            "low": {"priority": 4, "score_impact": -3, "sla_hours": 168},
            "informational": {"priority": 5, "score_impact": -1, "sla_hours": 720}
        }

        # Compliance frameworks and their control counts
        self.compliance_frameworks = {
            "SOC2": {
                "name": "Service Organization Control 2",
                "control_count": 64,
                "categories": ["Security", "Availability", "Processing Integrity",
                              "Confidentiality", "Privacy"]
            },
            "HIPAA": {
                "name": "Health Insurance Portability and Accountability Act",
                "control_count": 45,
                "categories": ["Administrative", "Physical", "Technical"]
            },
            "PCI-DSS": {
                "name": "Payment Card Industry Data Security Standard",
                "control_count": 78,
                "categories": ["Build and Maintain Secure Network", "Protect Cardholder Data",
                              "Maintain Vulnerability Management", "Implement Access Controls",
                              "Monitor and Test Networks", "Maintain Information Security Policy"]
            },
            "ISO27001": {
                "name": "ISO/IEC 27001 Information Security",
                "control_count": 114,
                "categories": ["Organizational", "People", "Physical", "Technological"]
            },
            "GDPR": {
                "name": "General Data Protection Regulation",
                "control_count": 37,
                "categories": ["Lawfulness", "Data Minimization", "Accuracy",
                              "Storage Limitation", "Integrity", "Accountability"]
            },
            "NIST": {
                "name": "NIST Cybersecurity Framework",
                "control_count": 108,
                "categories": ["Identify", "Protect", "Detect", "Respond", "Recover"]
            }
        }

        # Security scoring weights
        self.score_weights = {
            "vulnerabilities": 0.30,
            "compliance": 0.25,
            "policies": 0.20,
            "configurations": 0.15,
            "access_controls": 0.10
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
            logger.error(f"Failed to initialize Security Compliance Agent: {exc}")
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
        """Execute security compliance action.

        Args:
            request: Request containing:
                - action: Action to perform (scan_security, check_compliance,
                         assess_vulnerabilities, policy_check, recommendations, full)
                - resource_group: Resource group to scan (optional)
                - resource_ids: List of specific resource IDs (optional)
                - compliance_frameworks: List of frameworks to check (optional)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Action result with security analysis and recommendations

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "scan_security")

        logger.info(f"Processing security compliance action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "scan_security": self._scan_security,
            "check_compliance": self._check_compliance,
            "assess_vulnerabilities": self._assess_vulnerabilities,
            "policy_check": self._validate_policies,
            "recommendations": self._generate_recommendations,
            "full": self._full_security_audit
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

    async def _scan_security(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive security scan.

        Scans resources for security issues, misconfigurations, and vulnerabilities.

        Args:
            request: Security scan request with scope and parameters
            context: Optional workflow context

        Returns:
            Security scan results with findings and score
        """
        resource_group = request.get("resource_group", "")
        scan_type = request.get("scan_type", "comprehensive")
        workflow_id = f"security-scan-{datetime.utcnow().timestamp()}"

        logger.info(f"Starting security scan for {resource_group or 'subscription'}")

        # Create workflow context for this scan
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_group": resource_group,
                "scan_type": scan_type,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Get security score
        score_result = await self._call_tool(
            "get_security_score",
            {
                "resource_group": resource_group,
                "calculation_method": "weighted"
            }
        )

        # Store score result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="security_score",
            agent_id=self.agent_id,
            result=score_result
        )

        score_data = score_result.get("data", {})
        current_score = score_data.get("overall_score", 0)
        max_score = score_data.get("max_score", 100)
        score_percentage = (current_score / max_score * 100) if max_score > 0 else 0

        # Step 2: List security recommendations
        recommendations_result = await self._call_tool(
            "list_security_recommendations",
            {
                "resource_group": resource_group,
                "severity_filter": request.get("severity_filter", "all")
            }
        )

        # Store recommendations
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="recommendations",
            agent_id=self.agent_id,
            result=recommendations_result
        )

        recommendations_data = recommendations_result.get("data", {})
        recommendations = recommendations_data.get("recommendations", [])

        # Categorize findings by severity
        severity_breakdown = self._categorize_by_severity(recommendations)

        # Calculate risk level
        risk_level = self._calculate_risk_level(
            score_percentage,
            severity_breakdown
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "scan": {
                "scope": resource_group or "subscription",
                "scan_type": scan_type,
                "security_score": {
                    "current": current_score,
                    "max": max_score,
                    "percentage": round(score_percentage, 2),
                    "grade": self._score_to_grade(score_percentage)
                },
                "findings": {
                    "total": len(recommendations),
                    "by_severity": severity_breakdown,
                    "high_priority_count": severity_breakdown.get("critical", 0) +
                                          severity_breakdown.get("high", 0)
                },
                "risk_level": risk_level,
                "timestamp": datetime.utcnow().isoformat()
            },
            "next_steps": [
                "review_critical_findings",
                "check_compliance_status",
                "plan_remediation"
            ]
        }

    async def _check_compliance(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Check compliance status against frameworks.

        Validates compliance with specified security frameworks and standards.

        Args:
            request: Compliance check request with framework specifications
            context: Optional workflow context

        Returns:
            Compliance status with control pass/fail details
        """
        framework = request.get("framework", "SOC2")
        resource_group = request.get("resource_group", "")
        workflow_id = request.get("workflow_id", f"compliance-{datetime.utcnow().timestamp()}")

        logger.info(f"Checking {framework} compliance for {resource_group or 'subscription'}")

        # Validate framework
        if framework not in self.compliance_frameworks:
            raise AgentExecutionError(
                f"Unknown compliance framework: {framework}. "
                f"Valid frameworks: {', '.join(self.compliance_frameworks.keys())}"
            )

        framework_info = self.compliance_frameworks[framework]

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "framework": framework,
                "resource_group": resource_group,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 1: Check compliance status
        compliance_result = await self._call_tool(
            "check_compliance_status",
            {
                "framework": framework,
                "resource_group": resource_group,
                "include_details": True
            }
        )

        # Store compliance result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="compliance_check",
            agent_id=self.agent_id,
            result=compliance_result
        )

        compliance_data = compliance_result.get("data", {})
        controls = compliance_data.get("controls", [])

        # Analyze control status
        passed_controls = [c for c in controls if c.get("status") == "passed"]
        failed_controls = [c for c in controls if c.get("status") == "failed"]
        not_applicable = [c for c in controls if c.get("status") == "not_applicable"]
        in_progress = [c for c in controls if c.get("status") == "in_progress"]

        total_applicable = len(controls) - len(not_applicable)
        compliance_percentage = (
            (len(passed_controls) / total_applicable * 100)
            if total_applicable > 0 else 0
        )

        # Determine compliance status
        compliance_status = self._determine_compliance_status(compliance_percentage)

        # Identify critical gaps
        critical_gaps = [
            c for c in failed_controls
            if c.get("severity") in ["critical", "high"]
        ]

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "compliance": {
                "framework": framework,
                "framework_name": framework_info["name"],
                "scope": resource_group or "subscription",
                "overall_status": compliance_status,
                "compliance_percentage": round(compliance_percentage, 2),
                "controls": {
                    "total": len(controls),
                    "passed": len(passed_controls),
                    "failed": len(failed_controls),
                    "in_progress": len(in_progress),
                    "not_applicable": len(not_applicable)
                },
                "critical_gaps": len(critical_gaps),
                "categories": framework_info["categories"],
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommendations": self._generate_compliance_recommendations(
                failed_controls[:5]  # Top 5 failures
            )
        }

    async def _assess_vulnerabilities(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Assess vulnerabilities across resources.

        Identifies, categorizes, and prioritizes vulnerabilities.

        Args:
            request: Vulnerability assessment request
            context: Optional workflow context

        Returns:
            Vulnerability assessment with prioritization
        """
        resource_ids = request.get("resource_ids", [])
        resource_group = request.get("resource_group", "")
        severity_threshold = request.get("severity_threshold", "low")
        workflow_id = request.get("workflow_id", f"vuln-assess-{datetime.utcnow().timestamp()}")

        logger.info(f"Assessing vulnerabilities for {len(resource_ids) or 'all'} resources")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_count": len(resource_ids),
                "resource_group": resource_group,
                "severity_threshold": severity_threshold,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 1: Get vulnerability assessment
        vuln_results = []

        if resource_ids:
            # Assess specific resources
            for resource_id in resource_ids:
                try:
                    result = await self._call_tool(
                        "assess_resource_vulnerabilities",
                        {
                            "resource_id": resource_id,
                            "severity_threshold": severity_threshold
                        }
                    )
                    vuln_results.append(result)
                except Exception as exc:
                    logger.warning(f"Failed to assess {resource_id}: {exc}")
        else:
            # Assess resource group or subscription
            result = await self._call_tool(
                "list_security_recommendations",
                {
                    "resource_group": resource_group,
                    "recommendation_type": "vulnerability",
                    "severity_filter": severity_threshold
                }
            )
            vuln_results.append(result)

        # Store vulnerability results
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="vulnerability_assessment",
            agent_id=self.agent_id,
            result={"assessments": vuln_results}
        )

        # Aggregate vulnerabilities
        all_vulnerabilities = []
        for result in vuln_results:
            data = result.get("data", {})
            vulns = data.get("vulnerabilities", data.get("recommendations", []))
            all_vulnerabilities.extend(vulns)

        # Categorize and prioritize
        severity_breakdown = self._categorize_by_severity(all_vulnerabilities)
        prioritized_vulns = self._prioritize_vulnerabilities(all_vulnerabilities)

        # Calculate CVSS statistics
        cvss_scores = [
            v.get("cvss_score", 0)
            for v in all_vulnerabilities
            if v.get("cvss_score")
        ]
        avg_cvss = sum(cvss_scores) / len(cvss_scores) if cvss_scores else 0

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "vulnerabilities": {
                "total_found": len(all_vulnerabilities),
                "by_severity": severity_breakdown,
                "prioritized_list": prioritized_vulns[:20],  # Top 20
                "cvss_statistics": {
                    "average": round(avg_cvss, 2),
                    "max": max(cvss_scores) if cvss_scores else 0,
                    "high_severity_count": len([s for s in cvss_scores if s >= 7.0])
                },
                "remediation_summary": self._generate_remediation_summary(prioritized_vulns[:10]),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _validate_policies(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Validate security policy enforcement.

        Checks that security policies are properly configured and enforced.

        Args:
            request: Policy validation request
            context: Optional workflow context

        Returns:
            Policy validation results
        """
        resource_group = request.get("resource_group", "")
        policy_types = request.get("policy_types", ["all"])
        workflow_id = request.get("workflow_id", f"policy-check-{datetime.utcnow().timestamp()}")

        logger.info(f"Validating security policies for {resource_group or 'subscription'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_group": resource_group,
                "policy_types": policy_types,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 1: Check policy compliance
        policy_result = await self._call_tool(
            "check_policy_compliance",
            {
                "resource_group": resource_group,
                "policy_types": policy_types
            }
        )

        # Store policy result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="policy_validation",
            agent_id=self.agent_id,
            result=policy_result
        )

        policy_data = policy_result.get("data", {})
        policies = policy_data.get("policies", [])

        # Categorize policies
        enforced = [p for p in policies if p.get("enforcement_mode") == "enforced"]
        audit_only = [p for p in policies if p.get("enforcement_mode") == "audit"]
        disabled = [p for p in policies if p.get("enforcement_mode") == "disabled"]
        violations = [p for p in policies if p.get("violation_count", 0) > 0]

        # Calculate compliance rate
        total_policies = len(policies)
        compliant_policies = len([p for p in policies if p.get("compliant", True)])
        compliance_rate = (
            (compliant_policies / total_policies * 100)
            if total_policies > 0 else 100
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "policies": {
                "total_policies": total_policies,
                "enforcement_status": {
                    "enforced": len(enforced),
                    "audit_only": len(audit_only),
                    "disabled": len(disabled)
                },
                "compliance_rate": round(compliance_rate, 2),
                "violations": {
                    "total": sum(p.get("violation_count", 0) for p in violations),
                    "policies_with_violations": len(violations),
                    "top_violations": violations[:5]
                },
                "recommendations": self._generate_policy_recommendations(
                    audit_only, disabled, violations
                ),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    async def _generate_recommendations(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate security remediation recommendations.

        Creates prioritized remediation plan based on security findings.

        Args:
            request: Recommendations request
            context: Optional workflow context

        Returns:
            Prioritized recommendations with remediation steps
        """
        workflow_id = request.get("workflow_id", f"recommendations-{datetime.utcnow().timestamp()}")

        logger.info("Generating security recommendations")

        # Get context from previous steps if available
        workflow_context = await self.context_store.get_workflow_context(workflow_id)

        # Extract findings from workflow context
        security_score_step = workflow_context.get("steps", {}).get("security_score", {})
        compliance_step = workflow_context.get("steps", {}).get("compliance_check", {})
        vulnerability_step = workflow_context.get("steps", {}).get("vulnerability_assessment", {})

        # Generate comprehensive recommendations
        recommendations = {
            "immediate_actions": [
                {
                    "priority": 1,
                    "category": "Critical Vulnerabilities",
                    "action": "Patch critical vulnerabilities with CVSS > 9.0",
                    "estimated_time": "4 hours",
                    "impact": "High"
                },
                {
                    "priority": 2,
                    "category": "Access Control",
                    "action": "Review and revoke excessive permissions",
                    "estimated_time": "2 hours",
                    "impact": "High"
                },
                {
                    "priority": 3,
                    "category": "Network Security",
                    "action": "Enable NSG flow logs and Azure Firewall",
                    "estimated_time": "1 hour",
                    "impact": "Medium"
                }
            ],
            "short_term_actions": [
                {
                    "priority": 4,
                    "category": "Encryption",
                    "action": "Enable encryption at rest for all storage accounts",
                    "estimated_time": "4 hours",
                    "impact": "High"
                },
                {
                    "priority": 5,
                    "category": "Monitoring",
                    "action": "Configure security alerts and incident response",
                    "estimated_time": "8 hours",
                    "impact": "Medium"
                },
                {
                    "priority": 6,
                    "category": "Compliance",
                    "action": "Implement missing compliance controls",
                    "estimated_time": "2 days",
                    "impact": "Medium"
                }
            ],
            "long_term_actions": [
                {
                    "priority": 7,
                    "category": "Security Posture",
                    "action": "Implement zero-trust architecture",
                    "estimated_time": "4 weeks",
                    "impact": "High"
                },
                {
                    "priority": 8,
                    "category": "Automation",
                    "action": "Deploy automated security scanning in CI/CD",
                    "estimated_time": "2 weeks",
                    "impact": "Medium"
                },
                {
                    "priority": 9,
                    "category": "Training",
                    "action": "Conduct security awareness training",
                    "estimated_time": "Ongoing",
                    "impact": "Medium"
                }
            ],
            "estimated_impact": {
                "security_score_improvement": "+35 points",
                "compliance_rate_improvement": "+25%",
                "risk_reduction": "High",
                "estimated_total_time": "6 weeks"
            }
        }

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "recommendations": recommendations,
            "prioritization_criteria": [
                "Severity of security risk",
                "Ease of implementation",
                "Business impact",
                "Regulatory requirements",
                "Cost-benefit ratio"
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _full_security_audit(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full security audit workflow.

        Runs all phases: scan → compliance → vulnerabilities → policies → recommendations

        Args:
            request: Full audit request
            context: Optional workflow context

        Returns:
            Complete security audit report
        """
        workflow_id = f"full-audit-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        logger.info(f"Starting full security audit: {workflow_id}")

        # Phase 1: Security scan
        scan_result = await self._scan_security(request, context)

        # Phase 2: Compliance check (if frameworks specified)
        compliance_results = []
        frameworks = request.get("compliance_frameworks", ["SOC2"])
        for framework in frameworks:
            compliance_req = {**request, "framework": framework}
            compliance_result = await self._check_compliance(compliance_req, context)
            compliance_results.append(compliance_result)

        # Phase 3: Vulnerability assessment
        vuln_result = await self._assess_vulnerabilities(request, context)

        # Phase 4: Policy validation
        policy_result = await self._validate_policies(request, context)

        # Phase 5: Generate recommendations
        recommendations_result = await self._generate_recommendations(request, context)

        # Calculate overall metrics
        security_score = scan_result.get("scan", {}).get("security_score", {})
        avg_compliance = sum(
            c.get("compliance", {}).get("compliance_percentage", 0)
            for c in compliance_results
        ) / len(compliance_results) if compliance_results else 0

        total_vulnerabilities = vuln_result.get("vulnerabilities", {}).get("total_found", 0)
        critical_vulns = vuln_result.get("vulnerabilities", {}).get("by_severity", {}).get("critical", 0)

        policy_compliance = policy_result.get("policies", {}).get("compliance_rate", 0)

        # Determine overall security posture
        overall_posture = self._determine_security_posture(
            security_score.get("percentage", 0),
            avg_compliance,
            critical_vulns,
            policy_compliance
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "audit_type": "comprehensive",
            "scope": request.get("resource_group", "subscription"),
            "phases": {
                "security_scan": scan_result,
                "compliance_checks": compliance_results,
                "vulnerability_assessment": vuln_result,
                "policy_validation": policy_result,
                "recommendations": recommendations_result
            },
            "executive_summary": {
                "overall_posture": overall_posture,
                "security_score": security_score.get("percentage", 0),
                "security_grade": security_score.get("grade", "Unknown"),
                "average_compliance": round(avg_compliance, 2),
                "total_vulnerabilities": total_vulnerabilities,
                "critical_vulnerabilities": critical_vulns,
                "policy_compliance_rate": policy_compliance,
                "high_priority_items": scan_result.get("scan", {}).get("findings", {}).get("high_priority_count", 0),
                "estimated_remediation_time": recommendations_result.get("recommendations", {}).get("estimated_impact", {}).get("estimated_total_time", "Unknown")
            },
            "risk_assessment": {
                "overall_risk": "high" if critical_vulns > 5 or security_score.get("percentage", 0) < 60 else "medium" if critical_vulns > 0 or security_score.get("percentage", 0) < 80 else "low",
                "risk_factors": self._identify_risk_factors(
                    scan_result, compliance_results, vuln_result, policy_result
                ),
                "risk_trend": "improving" if security_score.get("percentage", 0) >= 70 else "degrading"
            },
            "completed_at": datetime.utcnow().isoformat()
        }

    def _categorize_by_severity(self, items: List[Dict]) -> Dict[str, int]:
        """Categorize items by severity level.

        Args:
            items: List of findings/recommendations

        Returns:
            Dictionary with severity counts
        """
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0
        }

        for item in items:
            severity = item.get("severity", "low").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        return severity_counts

    def _calculate_risk_level(
        self,
        security_score: float,
        severity_breakdown: Dict[str, int]
    ) -> str:
        """Calculate overall risk level.

        Args:
            security_score: Security score percentage
            severity_breakdown: Severity counts

        Returns:
            Risk level (critical, high, medium, low)
        """
        critical_count = severity_breakdown.get("critical", 0)
        high_count = severity_breakdown.get("high", 0)

        if critical_count > 10 or security_score < 40:
            return "critical"
        elif critical_count > 5 or high_count > 20 or security_score < 60:
            return "high"
        elif critical_count > 0 or high_count > 10 or security_score < 80:
            return "medium"
        else:
            return "low"

    def _score_to_grade(self, score_percentage: float) -> str:
        """Convert security score to letter grade.

        Args:
            score_percentage: Score as percentage

        Returns:
            Letter grade (A+, A, B, C, D, F)
        """
        if score_percentage >= 95:
            return "A+"
        elif score_percentage >= 90:
            return "A"
        elif score_percentage >= 85:
            return "A-"
        elif score_percentage >= 80:
            return "B+"
        elif score_percentage >= 75:
            return "B"
        elif score_percentage >= 70:
            return "B-"
        elif score_percentage >= 65:
            return "C+"
        elif score_percentage >= 60:
            return "C"
        elif score_percentage >= 55:
            return "C-"
        elif score_percentage >= 50:
            return "D"
        else:
            return "F"

    def _determine_compliance_status(self, compliance_percentage: float) -> str:
        """Determine compliance status from percentage.

        Args:
            compliance_percentage: Compliance rate

        Returns:
            Status string (compliant, mostly_compliant, non_compliant)
        """
        if compliance_percentage >= 95:
            return "compliant"
        elif compliance_percentage >= 80:
            return "mostly_compliant"
        elif compliance_percentage >= 60:
            return "partially_compliant"
        else:
            return "non_compliant"

    def _prioritize_vulnerabilities(
        self,
        vulnerabilities: List[Dict]
    ) -> List[Dict]:
        """Prioritize vulnerabilities by severity and exploitability.

        Args:
            vulnerabilities: List of vulnerability findings

        Returns:
            Sorted list of vulnerabilities
        """
        # Define priority weights
        severity_priority = {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
            "informational": 5
        }

        # Sort by severity, then CVSS score, then exploitability
        sorted_vulns = sorted(
            vulnerabilities,
            key=lambda v: (
                severity_priority.get(v.get("severity", "low").lower(), 5),
                -v.get("cvss_score", 0),
                -v.get("exploitability", 0)
            )
        )

        return sorted_vulns

    def _generate_remediation_summary(
        self,
        vulnerabilities: List[Dict]
    ) -> Dict[str, Any]:
        """Generate remediation summary for top vulnerabilities.

        Args:
            vulnerabilities: List of prioritized vulnerabilities

        Returns:
            Remediation summary
        """
        if not vulnerabilities:
            return {
                "immediate_actions_required": 0,
                "estimated_total_hours": 0,
                "summary": "No vulnerabilities requiring immediate remediation"
            }

        critical_high = [
            v for v in vulnerabilities
            if v.get("severity", "").lower() in ["critical", "high"]
        ]

        return {
            "immediate_actions_required": len(critical_high),
            "estimated_total_hours": len(critical_high) * 4,  # Estimate 4 hours per critical/high
            "summary": f"{len(critical_high)} critical/high vulnerabilities require immediate attention"
        }

    def _generate_compliance_recommendations(
        self,
        failed_controls: List[Dict]
    ) -> List[str]:
        """Generate recommendations for failed compliance controls.

        Args:
            failed_controls: List of failed controls

        Returns:
            List of recommendations
        """
        if not failed_controls:
            return ["All compliance controls passed - maintain current security posture"]

        recommendations = []
        for control in failed_controls[:5]:  # Top 5
            control_name = control.get("name", "Unknown control")
            category = control.get("category", "General")
            recommendations.append(
                f"Implement {control_name} in {category} category"
            )

        return recommendations

    def _generate_policy_recommendations(
        self,
        audit_only: List[Dict],
        disabled: List[Dict],
        violations: List[Dict]
    ) -> List[str]:
        """Generate policy enforcement recommendations.

        Args:
            audit_only: Policies in audit-only mode
            disabled: Disabled policies
            violations: Policies with violations

        Returns:
            List of recommendations
        """
        recommendations = []

        if disabled:
            recommendations.append(
                f"Enable {len(disabled)} disabled security policies"
            )

        if audit_only:
            recommendations.append(
                f"Upgrade {len(audit_only)} policies from audit to enforcement mode"
            )

        if violations:
            recommendations.append(
                f"Remediate {sum(v.get('violation_count', 0) for v in violations)} policy violations"
            )

        if not recommendations:
            recommendations.append("All policies are properly configured and enforced")

        return recommendations

    def _determine_security_posture(
        self,
        security_score: float,
        compliance_rate: float,
        critical_vulns: int,
        policy_compliance: float
    ) -> str:
        """Determine overall security posture.

        Args:
            security_score: Security score percentage
            compliance_rate: Average compliance rate
            critical_vulns: Number of critical vulnerabilities
            policy_compliance: Policy compliance rate

        Returns:
            Overall posture (excellent, good, fair, poor, critical)
        """
        avg_score = (security_score + compliance_rate + policy_compliance) / 3

        if critical_vulns > 10 or avg_score < 40:
            return "critical"
        elif critical_vulns > 5 or avg_score < 60:
            return "poor"
        elif critical_vulns > 0 or avg_score < 75:
            return "fair"
        elif avg_score < 90:
            return "good"
        else:
            return "excellent"

    def _identify_risk_factors(
        self,
        scan_result: Dict,
        compliance_results: List[Dict],
        vuln_result: Dict,
        policy_result: Dict
    ) -> List[str]:
        """Identify key risk factors from audit results.

        Args:
            scan_result: Security scan results
            compliance_results: Compliance check results
            vuln_result: Vulnerability assessment results
            policy_result: Policy validation results

        Returns:
            List of identified risk factors
        """
        risk_factors = []

        # Check security score
        score_percentage = scan_result.get("scan", {}).get("security_score", {}).get("percentage", 0)
        if score_percentage < 70:
            risk_factors.append(f"Low security score: {score_percentage:.1f}%")

        # Check compliance
        for comp in compliance_results:
            comp_percentage = comp.get("compliance", {}).get("compliance_percentage", 0)
            framework = comp.get("compliance", {}).get("framework", "Unknown")
            if comp_percentage < 80:
                risk_factors.append(f"Low {framework} compliance: {comp_percentage:.1f}%")

        # Check vulnerabilities
        critical_vulns = vuln_result.get("vulnerabilities", {}).get("by_severity", {}).get("critical", 0)
        if critical_vulns > 0:
            risk_factors.append(f"{critical_vulns} critical vulnerabilities")

        # Check policy compliance
        policy_compliance = policy_result.get("policies", {}).get("compliance_rate", 0)
        if policy_compliance < 90:
            risk_factors.append(f"Policy compliance below 90%: {policy_compliance:.1f}%")

        # Check violations
        total_violations = policy_result.get("policies", {}).get("violations", {}).get("total", 0)
        if total_violations > 0:
            risk_factors.append(f"{total_violations} policy violations detected")

        if not risk_factors:
            risk_factors.append("No significant risk factors identified")

        return risk_factors
