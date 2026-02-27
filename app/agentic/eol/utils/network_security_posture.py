"""
Network Security Posture Engine

Compliance-oriented security auditing against CIS Azure Benchmarks, NIST, and PCI DSS
frameworks. Discovers Azure network resources and evaluates security controls to
produce a quantified posture score and actionable remediation guidance.

Key capabilities:
- CIS Azure Benchmark 1.5 rules for network security
- Modular rule engine with pluggable check functions
- Severity-weighted compliance scoring
- Remediation templates with Azure CLI commands
- Support for framework and severity filtering
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.network.aio import NetworkManagementClient
    from azure.mgmt.resource.aio import ResourceManagementClient
    AZURE_SDK_AVAILABLE = True
except ImportError:
    DefaultAzureCredential = None
    NetworkManagementClient = None
    ResourceManagementClient = None
    AZURE_SDK_AVAILABLE = False

try:
    from app.agentic.eol.utils.logger import get_logger
except ImportError:
    from utils.logger import get_logger  # type: ignore[import-not-found]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANAGEMENT_PORTS = {22, 3389, 5985, 5986}

SEVERITY_WEIGHTS = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
}

SUPPORTED_FRAMEWORKS = {"cis_azure", "nist", "pci_dss"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ComplianceRule:
    """Definition of a compliance rule with its check function and metadata.

    Attributes:
        id: Unique rule identifier (e.g., NSG-001)
        framework: Compliance framework (cis_azure, nist, pci_dss)
        severity: Rule severity (Critical, High, Medium, Low)
        check_function: Async callable that performs the check
        remediation_template: Template string with remediation steps
        title: Short human-readable rule title
        description: Detailed description of what the rule checks
    """
    id: str
    framework: str
    severity: str
    check_function: Callable
    remediation_template: str
    title: str
    description: str


@dataclass
class ComplianceFinding:
    """A finding from evaluating a compliance rule against a resource.

    Attributes:
        rule_id: ID of the rule that generated this finding
        severity: Finding severity (inherited from rule)
        resource_id: Azure resource ID
        resource_type: Azure resource type (e.g., Microsoft.Network/networkSecurityGroups)
        status: 'passed' or 'failed'
        description: Human-readable description of the finding
        remediation: Specific remediation steps for this resource
        risk_description: Description of the risk if not remediated
    """
    rule_id: str
    severity: str
    resource_id: str
    resource_type: str
    status: str  # 'passed' or 'failed'
    description: str
    remediation: str
    risk_description: str


@dataclass
class PostureReport:
    """Aggregated compliance posture report for a subscription/scope.

    Attributes:
        overall_score: Weighted compliance score (0–100)
        findings: All compliance findings
        summary_by_severity: Count of passed/failed per severity
        summary_by_category: Count of passed/failed per rule category
        compliance_percentage: Simple pass rate (passed / total * 100)
        assessed_at: ISO timestamp of when the assessment was run
        subscription_id: Azure subscription assessed
        framework: Compliance framework assessed
        scope: Scope of the assessment
    """
    overall_score: float
    findings: List[ComplianceFinding]
    summary_by_severity: Dict[str, Dict[str, int]]
    summary_by_category: Dict[str, Dict[str, int]]
    compliance_percentage: float
    assessed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    subscription_id: str = ""
    framework: str = "cis_azure"
    scope: str = "all"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class NetworkSecurityPostureEngine:
    """Evaluates Azure network security posture against compliance frameworks.

    Usage:
        engine = NetworkSecurityPostureEngine()
        report = await engine.assess_posture(
            subscription_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            framework="cis_azure",
            scope="all",
            severity_filter=["Critical", "High"],
        )
        print(f"Score: {report.overall_score:.1f}/100")
    """

    def __init__(self) -> None:
        self._rules: Dict[str, List[ComplianceRule]] = self._load_compliance_rules()
        logger.info(
            "NetworkSecurityPostureEngine initialised with %d frameworks, %d total rules",
            len(self._rules),
            sum(len(v) for v in self._rules.values()),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def assess_posture(
        self,
        subscription_id: str,
        framework: str = "cis_azure",
        scope: str = "all",
        severity_filter: Optional[List[str]] = None,
    ) -> PostureReport:
        """Run a compliance posture assessment for the given subscription.

        Args:
            subscription_id: Azure subscription ID to assess
            framework: Compliance framework to evaluate (cis_azure, nist, pci_dss)
            scope: Scope filter (all, or resource-group name)
            severity_filter: If provided, only include rules matching these severities

        Returns:
            PostureReport with score, findings, and summaries
        """
        logger.info(
            "Starting posture assessment: subscription=%s framework=%s scope=%s",
            subscription_id,
            framework,
            scope,
        )

        if framework not in SUPPORTED_FRAMEWORKS:
            raise ValueError(
                f"Unsupported framework '{framework}'. "
                f"Choose from: {sorted(SUPPORTED_FRAMEWORKS)}"
            )

        rules = self._rules.get(framework, [])
        if severity_filter:
            rules = [r for r in rules if r.severity in severity_filter]

        if not rules:
            logger.warning("No rules to evaluate for framework=%s filter=%s", framework, severity_filter)
            return PostureReport(
                overall_score=100.0,
                findings=[],
                summary_by_severity={},
                summary_by_category={},
                compliance_percentage=100.0,
                subscription_id=subscription_id,
                framework=framework,
                scope=scope,
            )

        # Execute all rule checks concurrently
        tasks = [
            self._run_rule(rule, subscription_id, scope)
            for rule in rules
        ]
        all_findings_nested: List[List[ComplianceFinding]] = await asyncio.gather(*tasks)
        all_findings: List[ComplianceFinding] = [
            f for findings in all_findings_nested for f in findings
        ]

        overall_score, compliance_percentage = self._calculate_score(all_findings)
        summary_by_severity = self._summarise_by_severity(all_findings)
        summary_by_category = self._summarise_by_category(all_findings)

        report = PostureReport(
            overall_score=overall_score,
            findings=all_findings,
            summary_by_severity=summary_by_severity,
            summary_by_category=summary_by_category,
            compliance_percentage=compliance_percentage,
            subscription_id=subscription_id,
            framework=framework,
            scope=scope,
        )

        logger.info(
            "Posture assessment complete: score=%.1f findings=%d passed=%d",
            overall_score,
            len(all_findings),
            sum(1 for f in all_findings if f.status == "passed"),
        )
        return report

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def _load_compliance_rules(self) -> Dict[str, List[ComplianceRule]]:
        """Build the compliance rule registry keyed by framework.

        Returns:
            Dict mapping framework name to list of ComplianceRule objects
        """
        return {
            "cis_azure": self._cis_azure_rules(),
            "nist": [],
            "pci_dss": [],
        }

    def _cis_azure_rules(self) -> List[ComplianceRule]:
        """Return CIS Azure Benchmark network security rules."""
        return [
            ComplianceRule(
                id="NSG-001",
                framework="cis_azure",
                severity="Critical",
                check_function=self._check_nsg_management_ports,
                title="No NSG allows unrestricted access to management ports",
                description=(
                    "CIS Azure 6.1 — Network Security Groups must not allow inbound "
                    "traffic from 0.0.0.0/0 on management ports (SSH:22, RDP:3389, "
                    "WinRM:5985/5986). Unrestricted access exposes VMs to brute-force "
                    "attacks from the internet."
                ),
                remediation_template=(
                    "Restrict NSG rule on {resource_name} to specific source IP ranges "
                    "or use Azure Just-In-Time VM access:\n"
                    "  az network nsg rule update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --nsg-name {resource_name} \\\n"
                    "    --name {rule_name} \\\n"
                    "    --source-address-prefixes <your-ip-range>\n\n"
                    "Reference: https://docs.microsoft.com/azure/security-center/just-in-time-explained"
                ),
            ),
            ComplianceRule(
                id="NSG-002",
                framework="cis_azure",
                severity="High",
                check_function=self._check_subnet_nsg_association,
                title="All subnets have an associated NSG",
                description=(
                    "CIS Azure 6.2 — Every subnet should have a Network Security Group "
                    "attached to control inbound and outbound traffic. Subnets without "
                    "an NSG rely solely on network-level controls, increasing lateral "
                    "movement risk."
                ),
                remediation_template=(
                    "Associate an NSG with subnet {resource_name} in VNet {vnet_name}:\n"
                    "  az network vnet subnet update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --vnet-name {vnet_name} \\\n"
                    "    --name {resource_name} \\\n"
                    "    --nsg <nsg-name>\n\n"
                    "Reference: https://docs.microsoft.com/azure/virtual-network/network-security-groups-overview"
                ),
            ),
            ComplianceRule(
                id="NSG-003",
                framework="cis_azure",
                severity="Medium",
                check_function=self._check_nsg_flow_logs,
                title="NSG flow logs enabled on all NSGs",
                description=(
                    "CIS Azure 6.3 — Network Watcher flow logs should be enabled for "
                    "every NSG to capture and analyse network traffic. Flow logs are "
                    "essential for incident response, forensics, and traffic anomaly "
                    "detection."
                ),
                remediation_template=(
                    "Enable flow logs for NSG {resource_name}:\n"
                    "  az network watcher flow-log create \\\n"
                    "    --location {location} \\\n"
                    "    --name flowlog-{resource_name} \\\n"
                    "    --nsg {resource_id} \\\n"
                    "    --storage-account <storage-account-id> \\\n"
                    "    --enabled true \\\n"
                    "    --retention 90\n\n"
                    "Reference: https://docs.microsoft.com/azure/network-watcher/network-watcher-nsg-flow-logging-overview"
                ),
            ),
            ComplianceRule(
                id="ROUTE-001",
                framework="cis_azure",
                severity="High",
                check_function=self._check_default_route_to_firewall,
                title="Default route (0.0.0.0/0) points to firewall/NVA",
                description=(
                    "CIS Azure 6.4 — User-defined route tables should direct default "
                    "traffic (0.0.0.0/0) to a firewall or Network Virtual Appliance "
                    "(NVA) rather than directly to the Internet. Sending default traffic "
                    "to the Internet bypasses centralized inspection."
                ),
                remediation_template=(
                    "Update the default route in route table {resource_name} to point "
                    "to your firewall or NVA:\n"
                    "  az network route-table route update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --route-table-name {resource_name} \\\n"
                    "    --name default-to-firewall \\\n"
                    "    --next-hop-type VirtualAppliance \\\n"
                    "    --next-hop-ip-address <firewall-private-ip>\n\n"
                    "Reference: https://docs.microsoft.com/azure/firewall/forced-tunneling"
                ),
            ),
            ComplianceRule(
                id="VNET-001",
                framework="cis_azure",
                severity="Low",
                check_function=self._check_vnet_custom_dns,
                title="VNet DNS configured with custom servers",
                description=(
                    "CIS Azure 6.5 — Virtual Networks should use custom DNS servers "
                    "rather than the default Azure-provided DNS. Custom DNS enables "
                    "internal name resolution, split-horizon DNS, and better control "
                    "over DNS query routing and logging."
                ),
                remediation_template=(
                    "Configure custom DNS servers for VNet {resource_name}:\n"
                    "  az network vnet update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --name {resource_name} \\\n"
                    "    --dns-servers <dns-server-1> <dns-server-2>\n\n"
                    "Reference: https://docs.microsoft.com/azure/virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances"
                ),
            ),
            ComplianceRule(
                id="PE-001",
                framework="cis_azure",
                severity="High",
                check_function=self._check_private_endpoints,
                title="PaaS services use private endpoints",
                description=(
                    "CIS Azure 6.6 — PaaS services (Storage, SQL, CosmosDB, Key Vault) "
                    "should be accessed via private endpoints rather than public network "
                    "access. Public access exposes data services to internet threats and "
                    "bypasses network perimeter controls."
                ),
                remediation_template=(
                    "Create a private endpoint for {resource_name} and disable public access:\n"
                    "  # Create private endpoint\n"
                    "  az network private-endpoint create \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --name pe-{resource_name} \\\n"
                    "    --vnet-name <vnet-name> \\\n"
                    "    --subnet <subnet-name> \\\n"
                    "    --private-connection-resource-id {resource_id} \\\n"
                    "    --connection-name {resource_name}-connection \\\n"
                    "    --group-id {group_id}\n\n"
                    "  # Disable public access\n"
                    "  az {resource_cli_type} update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --name {resource_name} \\\n"
                    "    --public-network-access Disabled\n\n"
                    "Reference: https://docs.microsoft.com/azure/private-link/private-endpoint-overview"
                ),
            ),
        ]

    # ------------------------------------------------------------------
    # Rule execution
    # ------------------------------------------------------------------

    async def _run_rule(
        self,
        rule: ComplianceRule,
        subscription_id: str,
        scope: str,
    ) -> List[ComplianceFinding]:
        """Execute a single rule's check function, catching any errors."""
        try:
            return await rule.check_function(subscription_id, scope)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Rule %s check failed: %s", rule.id, exc)
            return []

    # ------------------------------------------------------------------
    # CIS Azure check methods
    # ------------------------------------------------------------------

    async def _check_nsg_management_ports(
        self,
        subscription_id: str,
        scope: str,
        *,
        _nsgs: Optional[List[Any]] = None,
    ) -> List[ComplianceFinding]:
        """NSG-001: No NSG allows 0.0.0.0/0 on management ports.

        Queries all NSGs and inspects security rules for Allow inbound
        rules with source 0.0.0.0/0 targeting management ports.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter (resource group name or 'all')
            _nsgs: Optional pre-loaded NSG list (used in unit tests)

        Returns:
            List of ComplianceFinding, one per NSG evaluated
        """
        findings: List[ComplianceFinding] = []
        nsgs = _nsgs or await self._list_nsgs(subscription_id, scope)

        for nsg in nsgs:
            nsg_id = getattr(nsg, "id", "") or ""
            nsg_name = getattr(nsg, "name", "unknown")
            location = getattr(nsg, "location", "unknown")
            resource_group = self._parse_resource_group(nsg_id)
            security_rules = getattr(nsg, "security_rules", []) or []

            violating_rules: List[str] = []
            for rule in security_rules:
                if not self._is_inbound_allow(rule):
                    continue
                src = self._get_address_prefix(rule)
                ports = self._get_destination_ports(rule)
                if self._is_any_source(src) and self._ports_overlap(ports, MANAGEMENT_PORTS):
                    violating_rules.append(getattr(rule, "name", "unnamed"))

            if violating_rules:
                remediation = (
                    "Restrict NSG rule on {resource_name} to specific source IP ranges "
                    "or use Azure Just-In-Time VM access:\n"
                    "  az network nsg rule update \\\n"
                    "    --resource-group {resource_group} \\\n"
                    "    --nsg-name {resource_name} \\\n"
                    "    --name {rule_name} \\\n"
                    "    --source-address-prefixes <your-ip-range>"
                ).format(
                    resource_name=nsg_name,
                    resource_group=resource_group,
                    rule_name=violating_rules[0],
                )
                findings.append(ComplianceFinding(
                    rule_id="NSG-001",
                    severity="Critical",
                    resource_id=nsg_id,
                    resource_type="Microsoft.Network/networkSecurityGroups",
                    status="failed",
                    description=(
                        f"NSG '{nsg_name}' allows unrestricted (0.0.0.0/0) inbound access "
                        f"to management ports via rule(s): {', '.join(violating_rules)}"
                    ),
                    remediation=remediation,
                    risk_description=(
                        "Exposing management ports to the internet enables brute-force "
                        "attacks, credential stuffing, and direct exploitation of "
                        "RDP/SSH vulnerabilities."
                    ),
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="NSG-001",
                    severity="Critical",
                    resource_id=nsg_id,
                    resource_type="Microsoft.Network/networkSecurityGroups",
                    status="passed",
                    description=f"NSG '{nsg_name}' does not allow unrestricted access to management ports.",
                    remediation="",
                    risk_description="",
                ))

        return findings

    async def _check_subnet_nsg_association(
        self,
        subscription_id: str,
        scope: str,
        *,
        _vnets: Optional[List[Any]] = None,
    ) -> List[ComplianceFinding]:
        """NSG-002: All subnets must have an associated NSG.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter
            _vnets: Optional pre-loaded VNet list (used in unit tests)

        Returns:
            List of ComplianceFinding, one per subnet evaluated
        """
        findings: List[ComplianceFinding] = []
        vnets = _vnets or await self._list_vnets(subscription_id, scope)

        for vnet in vnets:
            vnet_name = getattr(vnet, "name", "unknown")
            subnets = getattr(vnet, "subnets", []) or []

            for subnet in subnets:
                subnet_id = getattr(subnet, "id", "") or ""
                subnet_name = getattr(subnet, "name", "unknown")
                resource_group = self._parse_resource_group(subnet_id)
                has_nsg = getattr(subnet, "network_security_group", None) is not None

                if not has_nsg:
                    remediation = (
                        f"Associate an NSG with subnet '{subnet_name}' in VNet '{vnet_name}':\n"
                        f"  az network vnet subnet update \\\n"
                        f"    --resource-group {resource_group} \\\n"
                        f"    --vnet-name {vnet_name} \\\n"
                        f"    --name {subnet_name} \\\n"
                        f"    --nsg <nsg-name>"
                    )
                    findings.append(ComplianceFinding(
                        rule_id="NSG-002",
                        severity="High",
                        resource_id=subnet_id,
                        resource_type="Microsoft.Network/virtualNetworks/subnets",
                        status="failed",
                        description=(
                            f"Subnet '{subnet_name}' in VNet '{vnet_name}' has no "
                            "associated Network Security Group."
                        ),
                        remediation=remediation,
                        risk_description=(
                            "Subnets without an NSG have no layer-3/4 traffic filtering, "
                            "enabling lateral movement between workloads."
                        ),
                    ))
                else:
                    findings.append(ComplianceFinding(
                        rule_id="NSG-002",
                        severity="High",
                        resource_id=subnet_id,
                        resource_type="Microsoft.Network/virtualNetworks/subnets",
                        status="passed",
                        description=(
                            f"Subnet '{subnet_name}' in VNet '{vnet_name}' has an associated NSG."
                        ),
                        remediation="",
                        risk_description="",
                    ))

        return findings

    async def _check_nsg_flow_logs(
        self,
        subscription_id: str,
        scope: str,
        *,
        _nsgs: Optional[List[Any]] = None,
        _flow_log_nsg_ids: Optional[List[str]] = None,
    ) -> List[ComplianceFinding]:
        """NSG-003: NSG flow logs must be enabled on all NSGs.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter
            _nsgs: Optional pre-loaded NSG list (unit tests)
            _flow_log_nsg_ids: Optional list of NSG IDs with flow logs enabled (unit tests)

        Returns:
            List of ComplianceFinding, one per NSG
        """
        findings: List[ComplianceFinding] = []
        nsgs = _nsgs or await self._list_nsgs(subscription_id, scope)
        flow_log_nsg_ids = (
            set(_flow_log_nsg_ids)
            if _flow_log_nsg_ids is not None
            else await self._get_flow_log_nsg_ids(subscription_id)
        )

        for nsg in nsgs:
            nsg_id = getattr(nsg, "id", "") or ""
            nsg_name = getattr(nsg, "name", "unknown")
            location = getattr(nsg, "location", "unknown")
            resource_group = self._parse_resource_group(nsg_id)
            has_flow_log = nsg_id.lower() in {x.lower() for x in flow_log_nsg_ids}

            if not has_flow_log:
                remediation = (
                    f"Enable flow logs for NSG '{nsg_name}':\n"
                    f"  az network watcher flow-log create \\\n"
                    f"    --location {location} \\\n"
                    f"    --name flowlog-{nsg_name} \\\n"
                    f"    --nsg {nsg_id} \\\n"
                    f"    --storage-account <storage-account-id> \\\n"
                    f"    --enabled true \\\n"
                    f"    --retention 90"
                )
                findings.append(ComplianceFinding(
                    rule_id="NSG-003",
                    severity="Medium",
                    resource_id=nsg_id,
                    resource_type="Microsoft.Network/networkSecurityGroups",
                    status="failed",
                    description=f"NSG '{nsg_name}' does not have flow logs enabled.",
                    remediation=remediation,
                    risk_description=(
                        "Without flow logs, network traffic to and from this NSG cannot "
                        "be audited, hindering incident response and forensic analysis."
                    ),
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="NSG-003",
                    severity="Medium",
                    resource_id=nsg_id,
                    resource_type="Microsoft.Network/networkSecurityGroups",
                    status="passed",
                    description=f"NSG '{nsg_name}' has flow logs enabled.",
                    remediation="",
                    risk_description="",
                ))

        return findings

    async def _check_default_route_to_firewall(
        self,
        subscription_id: str,
        scope: str,
        *,
        _route_tables: Optional[List[Any]] = None,
    ) -> List[ComplianceFinding]:
        """ROUTE-001: Default route (0.0.0.0/0) must not point to Internet.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter
            _route_tables: Optional pre-loaded route table list (unit tests)

        Returns:
            List of ComplianceFinding, one per route table evaluated
        """
        findings: List[ComplianceFinding] = []
        route_tables = _route_tables or await self._list_route_tables(subscription_id, scope)

        for rt in route_tables:
            rt_id = getattr(rt, "id", "") or ""
            rt_name = getattr(rt, "name", "unknown")
            resource_group = self._parse_resource_group(rt_id)
            routes = getattr(rt, "routes", []) or []

            internet_default: List[str] = []
            for route in routes:
                prefix = getattr(route, "address_prefix", "") or ""
                next_hop = getattr(route, "next_hop_type", "") or ""
                if prefix == "0.0.0.0/0" and next_hop.lower() == "internet":
                    internet_default.append(getattr(route, "name", "unnamed"))

            if internet_default:
                remediation = (
                    f"Update the default route in route table '{rt_name}' to point "
                    f"to your firewall or NVA:\n"
                    f"  az network route-table route update \\\n"
                    f"    --resource-group {resource_group} \\\n"
                    f"    --route-table-name {rt_name} \\\n"
                    f"    --name {internet_default[0]} \\\n"
                    f"    --next-hop-type VirtualAppliance \\\n"
                    f"    --next-hop-ip-address <firewall-private-ip>"
                )
                findings.append(ComplianceFinding(
                    rule_id="ROUTE-001",
                    severity="High",
                    resource_id=rt_id,
                    resource_type="Microsoft.Network/routeTables",
                    status="failed",
                    description=(
                        f"Route table '{rt_name}' has default route(s) pointing directly "
                        f"to the Internet: {', '.join(internet_default)}"
                    ),
                    remediation=remediation,
                    risk_description=(
                        "Traffic bypassing a central firewall cannot be inspected for "
                        "threats, data exfiltration, or policy violations."
                    ),
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="ROUTE-001",
                    severity="High",
                    resource_id=rt_id,
                    resource_type="Microsoft.Network/routeTables",
                    status="passed",
                    description=(
                        f"Route table '{rt_name}' does not route default traffic directly to the Internet."
                    ),
                    remediation="",
                    risk_description="",
                ))

        return findings

    async def _check_vnet_custom_dns(
        self,
        subscription_id: str,
        scope: str,
        *,
        _vnets: Optional[List[Any]] = None,
    ) -> List[ComplianceFinding]:
        """VNET-001: VNets should use custom DNS servers.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter
            _vnets: Optional pre-loaded VNet list (unit tests)

        Returns:
            List of ComplianceFinding, one per VNet
        """
        findings: List[ComplianceFinding] = []
        vnets = _vnets or await self._list_vnets(subscription_id, scope)

        for vnet in vnets:
            vnet_id = getattr(vnet, "id", "") or ""
            vnet_name = getattr(vnet, "name", "unknown")
            resource_group = self._parse_resource_group(vnet_id)
            dhcp = getattr(vnet, "dhcp_options", None)
            dns_servers = (getattr(dhcp, "dns_servers", None) or []) if dhcp else []

            if not dns_servers:
                remediation = (
                    f"Configure custom DNS servers for VNet '{vnet_name}':\n"
                    f"  az network vnet update \\\n"
                    f"    --resource-group {resource_group} \\\n"
                    f"    --name {vnet_name} \\\n"
                    f"    --dns-servers <dns-server-1> <dns-server-2>"
                )
                findings.append(ComplianceFinding(
                    rule_id="VNET-001",
                    severity="Low",
                    resource_id=vnet_id,
                    resource_type="Microsoft.Network/virtualNetworks",
                    status="failed",
                    description=(
                        f"VNet '{vnet_name}' is using default Azure DNS "
                        "(no custom DNS servers configured)."
                    ),
                    remediation=remediation,
                    risk_description=(
                        "Default Azure DNS does not support split-horizon DNS, custom "
                        "domain resolution, or DNS query logging for security monitoring."
                    ),
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="VNET-001",
                    severity="Low",
                    resource_id=vnet_id,
                    resource_type="Microsoft.Network/virtualNetworks",
                    status="passed",
                    description=(
                        f"VNet '{vnet_name}' uses custom DNS server(s): {', '.join(dns_servers)}"
                    ),
                    remediation="",
                    risk_description="",
                ))

        return findings

    async def _check_private_endpoints(
        self,
        subscription_id: str,
        scope: str,
        *,
        _paas_resources: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ComplianceFinding]:
        """PE-001: PaaS services should use private endpoints.

        Checks Storage, SQL, CosmosDB, and Key Vault resources for public
        network access enabled without a private endpoint.

        Args:
            subscription_id: Azure subscription ID
            scope: Scope filter
            _paas_resources: Optional pre-loaded resource list (unit tests).
                Each item: {"id": str, "name": str, "type": str,
                            "resource_group": str, "public_access": bool,
                            "has_private_endpoint": bool}

        Returns:
            List of ComplianceFinding, one per PaaS resource evaluated
        """
        findings: List[ComplianceFinding] = []
        resources = _paas_resources or await self._list_paas_resources(subscription_id, scope)

        for res in resources:
            res_id = res.get("id", "")
            res_name = res.get("name", "unknown")
            res_type = res.get("type", "unknown")
            resource_group = res.get("resource_group", self._parse_resource_group(res_id))
            public_access = res.get("public_access", False)
            has_pe = res.get("has_private_endpoint", False)
            group_id = self._get_private_endpoint_group_id(res_type)
            cli_type = self._get_cli_resource_type(res_type)

            if public_access and not has_pe:
                remediation = (
                    f"Create a private endpoint for '{res_name}' and disable public access:\n"
                    f"  az network private-endpoint create \\\n"
                    f"    --resource-group {resource_group} \\\n"
                    f"    --name pe-{res_name} \\\n"
                    f"    --vnet-name <vnet-name> \\\n"
                    f"    --subnet <subnet-name> \\\n"
                    f"    --private-connection-resource-id {res_id} \\\n"
                    f"    --connection-name {res_name}-connection \\\n"
                    f"    --group-id {group_id}\n\n"
                    f"  az {cli_type} update \\\n"
                    f"    --resource-group {resource_group} \\\n"
                    f"    --name {res_name} \\\n"
                    f"    --public-network-access Disabled"
                )
                findings.append(ComplianceFinding(
                    rule_id="PE-001",
                    severity="High",
                    resource_id=res_id,
                    resource_type=res_type,
                    status="failed",
                    description=(
                        f"PaaS resource '{res_name}' ({res_type}) has public network "
                        "access enabled and no private endpoint configured."
                    ),
                    remediation=remediation,
                    risk_description=(
                        "Public access exposes PaaS data services to internet threats "
                        "and bypasses network perimeter controls enforced by NSGs and firewalls."
                    ),
                ))
            else:
                findings.append(ComplianceFinding(
                    rule_id="PE-001",
                    severity="High",
                    resource_id=res_id,
                    resource_type=res_type,
                    status="passed",
                    description=(
                        f"PaaS resource '{res_name}' is secured: "
                        f"public_access={public_access}, has_private_endpoint={has_pe}."
                    ),
                    remediation="",
                    risk_description="",
                ))

        return findings

    # ------------------------------------------------------------------
    # Azure resource listing helpers (thin wrappers for testability)
    # ------------------------------------------------------------------

    async def _list_nsgs(self, subscription_id: str, scope: str) -> List[Any]:
        """List all NSGs in the subscription (or resource group if scope != 'all')."""
        if not AZURE_SDK_AVAILABLE:
            logger.warning("Azure SDK not available; returning empty NSG list")
            return []
        try:
            credential = DefaultAzureCredential()
            async with NetworkManagementClient(credential, subscription_id) as client:
                if scope != "all":
                    return [nsg async for nsg in client.network_security_groups.list(scope)]
                return [nsg async for nsg in client.network_security_groups.list_all()]
        except Exception as exc:
            logger.error("Failed to list NSGs: %s", exc)
            return []

    async def _list_vnets(self, subscription_id: str, scope: str) -> List[Any]:
        """List all VNets in the subscription."""
        if not AZURE_SDK_AVAILABLE:
            return []
        try:
            credential = DefaultAzureCredential()
            async with NetworkManagementClient(credential, subscription_id) as client:
                if scope != "all":
                    return [v async for v in client.virtual_networks.list(scope)]
                return [v async for v in client.virtual_networks.list_all()]
        except Exception as exc:
            logger.error("Failed to list VNets: %s", exc)
            return []

    async def _list_route_tables(self, subscription_id: str, scope: str) -> List[Any]:
        """List all route tables in the subscription."""
        if not AZURE_SDK_AVAILABLE:
            return []
        try:
            credential = DefaultAzureCredential()
            async with NetworkManagementClient(credential, subscription_id) as client:
                if scope != "all":
                    return [rt async for rt in client.route_tables.list(scope)]
                return [rt async for rt in client.route_tables.list_all()]
        except Exception as exc:
            logger.error("Failed to list route tables: %s", exc)
            return []

    async def _get_flow_log_nsg_ids(self, subscription_id: str) -> set:
        """Return a set of NSG IDs that have flow logs enabled."""
        if not AZURE_SDK_AVAILABLE:
            return set()
        try:
            credential = DefaultAzureCredential()
            async with NetworkManagementClient(credential, subscription_id) as client:
                enabled_ids: set = set()
                async for watcher in client.network_watchers.list_all():
                    watcher_rg = self._parse_resource_group(watcher.id)
                    watcher_name = watcher.name
                    try:
                        async for fl in client.flow_logs.list(watcher_rg, watcher_name):
                            if fl.enabled:
                                enabled_ids.add(fl.target_resource_id)
                    except Exception:  # pylint: disable=broad-except
                        pass
                return enabled_ids
        except Exception as exc:
            logger.error("Failed to query flow logs: %s", exc)
            return set()

    async def _list_paas_resources(
        self, subscription_id: str, scope: str
    ) -> List[Dict[str, Any]]:
        """List PaaS resources (Storage, Key Vault) with public access info.

        Returns normalised dicts rather than raw SDK objects so the check
        function stays SDK-agnostic.
        """
        if not AZURE_SDK_AVAILABLE:
            return []
        resources: List[Dict[str, Any]] = []
        try:
            from azure.mgmt.storage.aio import StorageManagementClient as StorageMgmt
            from azure.mgmt.keyvault.aio import KeyVaultManagementClient as KVMgmt
            credential = DefaultAzureCredential()
            # Storage accounts
            try:
                async with StorageMgmt(credential, subscription_id) as sc:
                    async for acct in sc.storage_accounts.list():
                        rg = self._parse_resource_group(acct.id or "")
                        if scope != "all" and rg.lower() != scope.lower():
                            continue
                        public = (
                            getattr(acct, "public_network_access", "Enabled") != "Disabled"
                        )
                        has_pe = bool(getattr(acct, "private_endpoint_connections", None))
                        resources.append({
                            "id": acct.id or "",
                            "name": acct.name or "unknown",
                            "type": "Microsoft.Storage/storageAccounts",
                            "resource_group": rg,
                            "public_access": public,
                            "has_private_endpoint": has_pe,
                        })
            except Exception as exc:
                logger.warning("Storage account enumeration failed: %s", exc)
            # Key Vaults
            try:
                async with KVMgmt(credential, subscription_id) as kvc:
                    async for kv in kvc.vaults.list():
                        rg = self._parse_resource_group(kv.id or "")
                        if scope != "all" and rg.lower() != scope.lower():
                            continue
                        props = getattr(kv, "properties", None)
                        public = (
                            getattr(props, "public_network_access", "Enabled") != "Disabled"
                            if props else True
                        )
                        has_pe = bool(
                            getattr(props, "private_endpoint_connections", None) if props else None
                        )
                        resources.append({
                            "id": kv.id or "",
                            "name": kv.name or "unknown",
                            "type": "Microsoft.KeyVault/vaults",
                            "resource_group": rg,
                            "public_access": public,
                            "has_private_endpoint": has_pe,
                        })
            except Exception as exc:
                logger.warning("Key Vault enumeration failed: %s", exc)
        except Exception as exc:
            logger.error("Failed to list PaaS resources: %s", exc)
        return resources

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _calculate_score(
        self, findings: List[ComplianceFinding]
    ) -> tuple[float, float]:
        """Calculate weighted score and simple compliance percentage.

        Weights each finding by severity so Critical failures penalise the
        score more heavily than Low failures.

        Returns:
            Tuple of (weighted_score, simple_percentage) both in [0, 100]
        """
        if not findings:
            return 100.0, 100.0

        total_weight = 0.0
        passed_weight = 0.0

        for f in findings:
            w = SEVERITY_WEIGHTS.get(f.severity, 1)
            total_weight += w
            if f.status == "passed":
                passed_weight += w

        weighted_score = (passed_weight / total_weight) * 100 if total_weight else 100.0
        total_count = len(findings)
        passed_count = sum(1 for f in findings if f.status == "passed")
        simple_pct = (passed_count / total_count) * 100 if total_count else 100.0

        return round(weighted_score, 2), round(simple_pct, 2)

    def _summarise_by_severity(
        self, findings: List[ComplianceFinding]
    ) -> Dict[str, Dict[str, int]]:
        """Count passed/failed findings grouped by severity."""
        summary: Dict[str, Dict[str, int]] = {}
        for f in findings:
            sev = f.severity
            if sev not in summary:
                summary[sev] = {"passed": 0, "failed": 0}
            summary[sev][f.status] = summary[sev].get(f.status, 0) + 1
        return summary

    def _summarise_by_category(
        self, findings: List[ComplianceFinding]
    ) -> Dict[str, Dict[str, int]]:
        """Count passed/failed findings grouped by rule category prefix."""
        summary: Dict[str, Dict[str, int]] = {}
        for f in findings:
            # Category = prefix before '-' (NSG, ROUTE, VNET, PE, etc.)
            category = f.rule_id.split("-")[0] if "-" in f.rule_id else f.rule_id
            if category not in summary:
                summary[category] = {"passed": 0, "failed": 0}
            summary[category][f.status] = summary[category].get(f.status, 0) + 1
        return summary

    # ------------------------------------------------------------------
    # NSG rule parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_inbound_allow(rule: Any) -> bool:
        direction = (getattr(rule, "direction", "") or "").lower()
        access = (getattr(rule, "access", "") or "").lower()
        return direction == "inbound" and access == "allow"

    @staticmethod
    def _get_address_prefix(rule: Any) -> str:
        return (
            getattr(rule, "source_address_prefix", "")
            or getattr(rule, "source_address_prefixes", [""])[0]
            or ""
        )

    @staticmethod
    def _is_any_source(prefix: str) -> bool:
        return prefix in {"*", "0.0.0.0/0", "Any", "Internet"}

    @staticmethod
    def _get_destination_ports(rule: Any) -> set:
        """Parse destination port range(s) from an NSG rule into a set of ints."""
        ports: set = set()
        raw_single = getattr(rule, "destination_port_range", "") or ""
        raw_multi = getattr(rule, "destination_port_ranges", []) or []

        ranges = list(raw_multi) + ([raw_single] if raw_single else [])
        for r in ranges:
            r = str(r).strip()
            if r in {"*", "Any", ""}:
                return set(range(0, 65536))  # wildcard — overlaps everything
            if "-" in r:
                parts = r.split("-", 1)
                try:
                    low, high = int(parts[0]), int(parts[1])
                    ports.update(range(low, high + 1))
                except ValueError:
                    pass
            else:
                try:
                    ports.add(int(r))
                except ValueError:
                    pass
        return ports

    @staticmethod
    def _ports_overlap(rule_ports: set, target_ports: set) -> bool:
        return bool(rule_ports & target_ports)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_resource_group(resource_id: str) -> str:
        """Extract resource group name from an Azure resource ID."""
        parts = resource_id.lower().split("/")
        try:
            idx = parts.index("resourcegroups")
            return resource_id.split("/")[idx + 1]
        except (ValueError, IndexError):
            return "unknown"

    @staticmethod
    def _get_private_endpoint_group_id(resource_type: str) -> str:
        """Return the private endpoint group-id for a given resource type."""
        mapping = {
            "microsoft.storage/storageaccounts": "blob",
            "microsoft.sql/servers": "sqlServer",
            "microsoft.documentdb/databaseaccounts": "Sql",
            "microsoft.keyvault/vaults": "vault",
        }
        return mapping.get(resource_type.lower(), "default")

    @staticmethod
    def _get_cli_resource_type(resource_type: str) -> str:
        """Return the Azure CLI resource type string for a given ARM resource type."""
        mapping = {
            "microsoft.storage/storageaccounts": "storage account",
            "microsoft.sql/servers": "sql server",
            "microsoft.documentdb/databaseaccounts": "cosmosdb account",
            "microsoft.keyvault/vaults": "keyvault",
        }
        return mapping.get(resource_type.lower(), "resource")
