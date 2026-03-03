"""
Unit tests for NetworkSecurityPostureEngine.

All tests are unit-level with no live Azure dependencies.
Azure SDK calls are replaced with pre-built mock objects passed via
the keyword-only `_*` injection parameters on each check method.

Markers:
    unit: No external dependencies required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

try:
    from app.agentic.eol.utils.network_security_posture import (
        NetworkSecurityPostureEngine,
        ComplianceRule,
        ComplianceFinding,
        PostureReport,
        SEVERITY_WEIGHTS,
    )
except ModuleNotFoundError:
    from utils.network_security_posture import (  # type: ignore[import-not-found]
        NetworkSecurityPostureEngine,
        ComplianceRule,
        ComplianceFinding,
        PostureReport,
        SEVERITY_WEIGHTS,
    )


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_nsg(
    name: str = "test-nsg",
    resource_id: str = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/networkSecurityGroups/test-nsg",
    location: str = "eastus",
    security_rules: List[Any] = None,
) -> MagicMock:
    nsg = MagicMock()
    nsg.name = name
    nsg.id = resource_id
    nsg.location = location
    nsg.security_rules = security_rules or []
    return nsg


def _make_rule(
    name: str = "allow-ssh",
    direction: str = "Inbound",
    access: str = "Allow",
    source_prefix: str = "0.0.0.0/0",
    dest_port: str = "22",
    dest_ports: List[str] = None,
) -> MagicMock:
    rule = MagicMock()
    rule.name = name
    rule.direction = direction
    rule.access = access
    rule.source_address_prefix = source_prefix
    rule.source_address_prefixes = []
    rule.destination_port_range = dest_port
    rule.destination_port_ranges = dest_ports or []
    return rule


def _make_vnet(
    name: str = "test-vnet",
    resource_id: str = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/test-vnet",
    subnets: List[Any] = None,
    dns_servers: List[str] = None,
) -> MagicMock:
    vnet = MagicMock()
    vnet.name = name
    vnet.id = resource_id
    dhcp = MagicMock()
    dhcp.dns_servers = dns_servers or []
    vnet.dhcp_options = dhcp
    vnet.subnets = subnets or []
    return vnet


def _make_subnet(
    name: str = "default",
    resource_id: str = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/test-vnet/subnets/default",
    nsg=None,
) -> MagicMock:
    subnet = MagicMock()
    subnet.name = name
    subnet.id = resource_id
    subnet.network_security_group = nsg
    return subnet


def _make_route_table(
    name: str = "test-rt",
    resource_id: str = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Network/routeTables/test-rt",
    routes: List[Any] = None,
) -> MagicMock:
    rt = MagicMock()
    rt.name = name
    rt.id = resource_id
    rt.routes = routes or []
    return rt


def _make_route(
    name: str = "default",
    address_prefix: str = "0.0.0.0/0",
    next_hop_type: str = "Internet",
) -> MagicMock:
    route = MagicMock()
    route.name = name
    route.address_prefix = address_prefix
    route.next_hop_type = next_hop_type
    return route


def _make_paas_resource(
    name: str = "myaccount",
    res_type: str = "Microsoft.Storage/storageAccounts",
    resource_group: str = "rg-1",
    public_access: bool = True,
    has_private_endpoint: bool = False,
) -> Dict[str, Any]:
    return {
        "id": f"/subscriptions/sub-1/resourceGroups/{resource_group}/providers/{res_type}/{name}",
        "name": name,
        "type": res_type,
        "resource_group": resource_group,
        "public_access": public_access,
        "has_private_endpoint": has_private_endpoint,
    }


# ---------------------------------------------------------------------------
# NSG-001: Management port exposure
# ---------------------------------------------------------------------------

class TestNsgManagementPorts:
    """Tests for NSG-001: No unrestricted access to management ports."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_with_open_ssh_fails(self):
        """NSG that allows 0.0.0.0/0 on port 22 should fail."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="0.0.0.0/0", dest_port="22")
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )

        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "NSG-001"
        assert findings[0].severity == "Critical"
        assert "allow-ssh" in findings[0].description

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_with_open_rdp_fails(self):
        """NSG that allows 0.0.0.0/0 on port 3389 should fail."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(name="allow-rdp", source_prefix="0.0.0.0/0", dest_port="3389")
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert findings[0].status == "failed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_with_wildcard_port_fails(self):
        """NSG that allows 0.0.0.0/0 on '*' (all ports) should fail."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="0.0.0.0/0", dest_port="*")
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert findings[0].status == "failed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_restricted_source_passes(self):
        """NSG with SSH restricted to a specific IP range should pass."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="10.0.0.0/8", dest_port="22")
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_with_deny_rule_passes(self):
        """NSG with Deny rule for 0.0.0.0/0 on management port should pass (deny != allow)."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(
            source_prefix="0.0.0.0/0",
            dest_port="22",
            access="Deny",
        )
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_nsgs_returns_empty(self):
        """When there are no NSGs, no findings should be returned."""
        engine = NetworkSecurityPostureEngine()
        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[]
        )
        assert findings == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remediation_contains_nsg_name(self):
        """Remediation text should reference the specific NSG name."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="0.0.0.0/0", dest_port="22")
        nsg = _make_nsg(name="prod-nsg", security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert "prod-nsg" in findings[0].remediation

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_port_range_overlapping_management_fails(self):
        """NSG with a port range that includes port 22 should fail."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="0.0.0.0/0", dest_port="20-25")
        nsg = _make_nsg(security_rules=[rule])

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert findings[0].status == "failed"


# ---------------------------------------------------------------------------
# NSG-002: Subnet NSG association
# ---------------------------------------------------------------------------

class TestSubnetNsgAssociation:
    """Tests for NSG-002: All subnets must have an associated NSG."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subnet_without_nsg_fails(self):
        """Subnet without an NSG should produce a failed finding."""
        engine = NetworkSecurityPostureEngine()
        subnet = _make_subnet(nsg=None)
        vnet = _make_vnet(subnets=[subnet])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "NSG-002"
        assert findings[0].severity == "High"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subnet_with_nsg_passes(self):
        """Subnet with an NSG attached should produce a passed finding."""
        engine = NetworkSecurityPostureEngine()
        mock_nsg = MagicMock()
        subnet = _make_subnet(nsg=mock_nsg)
        vnet = _make_vnet(subnets=[subnet])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_subnets_mixed_results(self):
        """Multiple subnets should each get their own finding."""
        engine = NetworkSecurityPostureEngine()
        subnet_with_nsg = _make_subnet(name="secured", nsg=MagicMock())
        subnet_no_nsg = _make_subnet(name="exposed", nsg=None)
        vnet = _make_vnet(subnets=[subnet_with_nsg, subnet_no_nsg])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert len(findings) == 2
        statuses = {f.description: f.status for f in findings}
        passed = sum(1 for f in findings if f.status == "passed")
        failed = sum(1 for f in findings if f.status == "failed")
        assert passed == 1
        assert failed == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vnet_without_subnets_returns_empty(self):
        """VNet with no subnets should return no findings."""
        engine = NetworkSecurityPostureEngine()
        vnet = _make_vnet(subnets=[])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert findings == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remediation_contains_subnet_and_vnet_name(self):
        """Remediation should include both subnet and VNet names."""
        engine = NetworkSecurityPostureEngine()
        subnet = _make_subnet(name="app-subnet", nsg=None)
        vnet = _make_vnet(name="app-vnet", subnets=[subnet])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert "app-subnet" in findings[0].remediation
        assert "app-vnet" in findings[0].remediation


# ---------------------------------------------------------------------------
# NSG-003: Flow logs
# ---------------------------------------------------------------------------

class TestNsgFlowLogs:
    """Tests for NSG-003: Flow logs enabled on all NSGs."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_without_flow_log_fails(self):
        """NSG with no flow log should produce a failed finding."""
        engine = NetworkSecurityPostureEngine()
        nsg = _make_nsg(name="nolog-nsg", resource_id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/nolog-nsg")

        findings = await engine._check_nsg_flow_logs(
            "sub-1", "all",
            _nsgs=[nsg],
            _flow_log_nsg_ids=[],
        )
        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "NSG-003"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg_with_flow_log_passes(self):
        """NSG with flow log enabled should produce a passed finding."""
        engine = NetworkSecurityPostureEngine()
        nsg_id = "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/logged-nsg"
        nsg = _make_nsg(name="logged-nsg", resource_id=nsg_id)

        findings = await engine._check_nsg_flow_logs(
            "sub-1", "all",
            _nsgs=[nsg],
            _flow_log_nsg_ids=[nsg_id],
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_flow_log_id_case_insensitive(self):
        """Flow log matching should be case-insensitive for resource IDs."""
        engine = NetworkSecurityPostureEngine()
        nsg_id = "/subscriptions/S/resourceGroups/RG/providers/Microsoft.Network/networkSecurityGroups/NSG"
        nsg = _make_nsg(name="NSG", resource_id=nsg_id)
        flow_log_id = nsg_id.lower()

        findings = await engine._check_nsg_flow_logs(
            "sub-1", "all",
            _nsgs=[nsg],
            _flow_log_nsg_ids=[flow_log_id],
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remediation_contains_location(self):
        """Remediation should include the NSG's location."""
        engine = NetworkSecurityPostureEngine()
        nsg = _make_nsg(name="nolog-nsg", location="westeurope")

        findings = await engine._check_nsg_flow_logs(
            "sub-1", "all",
            _nsgs=[nsg],
            _flow_log_nsg_ids=[],
        )
        assert "westeurope" in findings[0].remediation


# ---------------------------------------------------------------------------
# ROUTE-001: Default route to firewall
# ---------------------------------------------------------------------------

class TestDefaultRouteToFirewall:
    """Tests for ROUTE-001: Default route must not point to Internet."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_internet_default_route_fails(self):
        """Route table with 0.0.0.0/0 -> Internet should fail."""
        engine = NetworkSecurityPostureEngine()
        route = _make_route(address_prefix="0.0.0.0/0", next_hop_type="Internet")
        rt = _make_route_table(routes=[route])

        findings = await engine._check_default_route_to_firewall(
            "sub-1", "all", _route_tables=[rt]
        )
        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "ROUTE-001"
        assert findings[0].severity == "High"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_virtual_appliance_route_passes(self):
        """Route table with 0.0.0.0/0 -> VirtualAppliance should pass."""
        engine = NetworkSecurityPostureEngine()
        route = _make_route(address_prefix="0.0.0.0/0", next_hop_type="VirtualAppliance")
        rt = _make_route_table(routes=[route])

        findings = await engine._check_default_route_to_firewall(
            "sub-1", "all", _route_tables=[rt]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_default_route_passes(self):
        """Route table without a 0.0.0.0/0 route should pass (no Internet bypass)."""
        engine = NetworkSecurityPostureEngine()
        route = _make_route(address_prefix="10.0.0.0/8", next_hop_type="VirtualAppliance")
        rt = _make_route_table(routes=[route])

        findings = await engine._check_default_route_to_firewall(
            "sub-1", "all", _route_tables=[rt]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_route_tables_returns_empty(self):
        """No route tables → no findings."""
        engine = NetworkSecurityPostureEngine()
        findings = await engine._check_default_route_to_firewall(
            "sub-1", "all", _route_tables=[]
        )
        assert findings == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remediation_contains_route_table_name(self):
        """Remediation should include the route table name."""
        engine = NetworkSecurityPostureEngine()
        route = _make_route(address_prefix="0.0.0.0/0", next_hop_type="Internet")
        rt = _make_route_table(name="prod-rt", routes=[route])

        findings = await engine._check_default_route_to_firewall(
            "sub-1", "all", _route_tables=[rt]
        )
        assert "prod-rt" in findings[0].remediation


# ---------------------------------------------------------------------------
# VNET-001: Custom DNS
# ---------------------------------------------------------------------------

class TestVnetCustomDns:
    """Tests for VNET-001: VNet should use custom DNS."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vnet_with_no_dns_fails(self):
        """VNet without custom DNS servers should fail."""
        engine = NetworkSecurityPostureEngine()
        vnet = _make_vnet(dns_servers=[])

        findings = await engine._check_vnet_custom_dns(
            "sub-1", "all", _vnets=[vnet]
        )
        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "VNET-001"
        assert findings[0].severity == "Low"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vnet_with_custom_dns_passes(self):
        """VNet with custom DNS servers should pass."""
        engine = NetworkSecurityPostureEngine()
        vnet = _make_vnet(dns_servers=["10.0.0.4", "10.0.0.5"])

        findings = await engine._check_vnet_custom_dns(
            "sub-1", "all", _vnets=[vnet]
        )
        assert findings[0].status == "passed"
        assert "10.0.0.4" in findings[0].description

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_vnet_without_dhcp_options_fails(self):
        """VNet with dhcp_options=None should be treated as no custom DNS."""
        engine = NetworkSecurityPostureEngine()
        vnet = _make_vnet()
        vnet.dhcp_options = None

        findings = await engine._check_vnet_custom_dns(
            "sub-1", "all", _vnets=[vnet]
        )
        assert findings[0].status == "failed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_vnets_returns_empty(self):
        """No VNets → no findings."""
        engine = NetworkSecurityPostureEngine()
        findings = await engine._check_vnet_custom_dns(
            "sub-1", "all", _vnets=[]
        )
        assert findings == []


# ---------------------------------------------------------------------------
# PE-001: Private endpoints
# ---------------------------------------------------------------------------

class TestPrivateEndpoints:
    """Tests for PE-001: PaaS services should use private endpoints."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_public_storage_without_pe_fails(self):
        """Storage account with public access and no PE should fail."""
        engine = NetworkSecurityPostureEngine()
        res = _make_paas_resource(
            name="mystorage",
            res_type="Microsoft.Storage/storageAccounts",
            public_access=True,
            has_private_endpoint=False,
        )

        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[res]
        )
        assert len(findings) == 1
        assert findings[0].status == "failed"
        assert findings[0].rule_id == "PE-001"
        assert findings[0].severity == "High"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_with_pe_passes(self):
        """Storage account with private endpoint should pass even if public access enabled."""
        engine = NetworkSecurityPostureEngine()
        res = _make_paas_resource(
            public_access=True,
            has_private_endpoint=True,
        )

        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[res]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storage_with_public_disabled_passes(self):
        """Storage account with public access disabled should pass."""
        engine = NetworkSecurityPostureEngine()
        res = _make_paas_resource(
            public_access=False,
            has_private_endpoint=False,
        )

        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[res]
        )
        assert findings[0].status == "passed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remediation_contains_resource_name(self):
        """Remediation should include the resource name."""
        engine = NetworkSecurityPostureEngine()
        res = _make_paas_resource(name="prod-storage", public_access=True, has_private_endpoint=False)

        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[res]
        )
        assert "prod-storage" in findings[0].remediation

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_resources_returns_empty(self):
        """No PaaS resources → no findings."""
        engine = NetworkSecurityPostureEngine()
        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[]
        )
        assert findings == []


# ---------------------------------------------------------------------------
# Compliance score calculation
# ---------------------------------------------------------------------------

class TestComplianceScoreCalculation:
    """Tests for _calculate_score scoring logic."""

    def test_all_passed_gives_100(self):
        engine = NetworkSecurityPostureEngine()
        findings = [
            ComplianceFinding(
                rule_id="NSG-001", severity="Critical", resource_id="id-1",
                resource_type="Microsoft.Network/networkSecurityGroups",
                status="passed", description="", remediation="", risk_description=""
            ),
            ComplianceFinding(
                rule_id="NSG-002", severity="High", resource_id="id-2",
                resource_type="Microsoft.Network/virtualNetworks/subnets",
                status="passed", description="", remediation="", risk_description=""
            ),
        ]
        score, pct = engine._calculate_score(findings)
        assert score == 100.0
        assert pct == 100.0

    def test_all_failed_gives_0(self):
        engine = NetworkSecurityPostureEngine()
        findings = [
            ComplianceFinding(
                rule_id="NSG-001", severity="Critical", resource_id="id-1",
                resource_type="t", status="failed", description="",
                remediation="", risk_description=""
            ),
        ]
        score, pct = engine._calculate_score(findings)
        assert score == 0.0
        assert pct == 0.0

    def test_empty_findings_gives_100(self):
        engine = NetworkSecurityPostureEngine()
        score, pct = engine._calculate_score([])
        assert score == 100.0
        assert pct == 100.0

    def test_severity_weighted_score(self):
        """Critical failures should penalise more than Low failures."""
        engine = NetworkSecurityPostureEngine()
        # 1 passed Critical (weight=4) + 1 failed Low (weight=1)
        # passed_weight=4, total_weight=5 -> score = 80.0
        findings = [
            ComplianceFinding(
                rule_id="NSG-001", severity="Critical", resource_id="id-1",
                resource_type="t", status="passed", description="",
                remediation="", risk_description=""
            ),
            ComplianceFinding(
                rule_id="VNET-001", severity="Low", resource_id="id-2",
                resource_type="t", status="failed", description="",
                remediation="", risk_description=""
            ),
        ]
        score, pct = engine._calculate_score(findings)
        assert score == 80.0
        # simple pct = 1/2 = 50%
        assert pct == 50.0

    def test_mixed_severities_weighted_correctly(self):
        """Validate weighted scoring across all four severity levels."""
        engine = NetworkSecurityPostureEngine()
        # 1 passed Critical(4) + 1 passed High(3) + 1 failed Medium(2) + 1 failed Low(1)
        # passed_weight = 7, total_weight = 10 -> score = 70.0
        findings = [
            ComplianceFinding("NSG-001", "Critical", "id-1", "t", "passed", "", "", ""),
            ComplianceFinding("NSG-002", "High", "id-2", "t", "passed", "", "", ""),
            ComplianceFinding("NSG-003", "Medium", "id-3", "t", "failed", "", "", ""),
            ComplianceFinding("VNET-001", "Low", "id-4", "t", "failed", "", "", ""),
        ]
        score, pct = engine._calculate_score(findings)
        assert score == 70.0
        assert pct == 50.0


# ---------------------------------------------------------------------------
# Framework filtering
# ---------------------------------------------------------------------------

class TestFrameworkFiltering:
    """Verify that assess_posture only runs rules for the selected framework."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cis_azure_rules_run(self):
        """Assessing cis_azure framework should return rule IDs from that framework."""
        engine = NetworkSecurityPostureEngine()

        # Patch each check to return a single passed finding
        async def _empty(*args, **kwargs):
            return []

        for rule in engine._rules["cis_azure"]:
            rule.check_function = _empty

        report = await engine.assess_posture(
            subscription_id="sub-1",
            framework="cis_azure",
            scope="all",
        )
        # All checks return empty → score perfect, no findings
        assert isinstance(report, PostureReport)
        assert report.framework == "cis_azure"
        assert report.compliance_percentage == 100.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_framework_raises(self):
        """Requesting an unsupported framework should raise ValueError."""
        engine = NetworkSecurityPostureEngine()
        with pytest.raises(ValueError, match="Unsupported framework"):
            await engine.assess_posture(
                subscription_id="sub-1",
                framework="made_up_framework",
                scope="all",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nist_framework_returns_empty_findings(self):
        """NIST framework has no rules yet — expect perfect score with no findings."""
        engine = NetworkSecurityPostureEngine()
        report = await engine.assess_posture(
            subscription_id="sub-1",
            framework="nist",
            scope="all",
        )
        assert report.findings == []
        assert report.compliance_percentage == 100.0


# ---------------------------------------------------------------------------
# Severity filtering
# ---------------------------------------------------------------------------

class TestSeverityFiltering:
    """Verify severity_filter parameter narrows rules evaluated."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_critical_only_filter(self):
        """Only Critical rules should be evaluated when severity_filter=['Critical']."""
        engine = NetworkSecurityPostureEngine()

        # Replace check functions so we can verify which rules run
        executed_rules: List[str] = []

        for rule in engine._rules["cis_azure"]:
            rule_id = rule.id

            async def _track(sub, scope, _rule_id=rule_id, **kwargs):
                executed_rules.append(_rule_id)
                return []

            rule.check_function = _track

        await engine.assess_posture(
            subscription_id="sub-1",
            framework="cis_azure",
            scope="all",
            severity_filter=["Critical"],
        )

        # Only NSG-001 (Critical) should have run
        assert "NSG-001" in executed_rules
        for rule_id in executed_rules:
            rule = next(r for r in engine._rules["cis_azure"] if r.id == rule_id)
            assert rule.severity == "Critical"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_critical_and_high_filter(self):
        """With severity_filter=['Critical','High'], only those rules run."""
        engine = NetworkSecurityPostureEngine()
        executed_rules: List[str] = []

        for rule in engine._rules["cis_azure"]:
            rule_id = rule.id

            async def _track(sub, scope, _rule_id=rule_id, **kwargs):
                executed_rules.append(_rule_id)
                return []

            rule.check_function = _track

        await engine.assess_posture(
            subscription_id="sub-1",
            framework="cis_azure",
            scope="all",
            severity_filter=["Critical", "High"],
        )

        expected_rule_ids = {
            r.id for r in engine._rules["cis_azure"]
            if r.severity in ("Critical", "High")
        }
        assert set(executed_rules) == expected_rule_ids

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_severity_filter_runs_all_rules(self):
        """Without severity_filter, all rules for the framework should run."""
        engine = NetworkSecurityPostureEngine()
        executed_rules: List[str] = []

        for rule in engine._rules["cis_azure"]:
            rule_id = rule.id

            async def _track(sub, scope, _rule_id=rule_id, **kwargs):
                executed_rules.append(_rule_id)
                return []

            rule.check_function = _track

        await engine.assess_posture(
            subscription_id="sub-1",
            framework="cis_azure",
            scope="all",
        )

        all_rule_ids = {r.id for r in engine._rules["cis_azure"]}
        assert set(executed_rules) == all_rule_ids


# ---------------------------------------------------------------------------
# Remediation generation
# ---------------------------------------------------------------------------

class TestRemediationGeneration:
    """Tests for remediation template population."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg001_remediation_includes_az_cli_command(self):
        """NSG-001 remediation should include an Azure CLI command."""
        engine = NetworkSecurityPostureEngine()
        rule = _make_rule(source_prefix="0.0.0.0/0", dest_port="22")
        nsg = _make_nsg(
            name="my-nsg",
            resource_id="/subscriptions/s/resourceGroups/prod-rg/providers/Microsoft.Network/networkSecurityGroups/my-nsg",
            security_rules=[rule],
        )

        findings = await engine._check_nsg_management_ports(
            "sub-1", "all", _nsgs=[nsg]
        )
        assert "az network nsg rule update" in findings[0].remediation

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nsg002_remediation_includes_subnet_update(self):
        """NSG-002 remediation should include subnet update command."""
        engine = NetworkSecurityPostureEngine()
        subnet = _make_subnet(name="web-subnet", nsg=None)
        vnet = _make_vnet(name="prod-vnet", subnets=[subnet])

        findings = await engine._check_subnet_nsg_association(
            "sub-1", "all", _vnets=[vnet]
        )
        assert "az network vnet subnet update" in findings[0].remediation

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pe001_remediation_includes_private_endpoint_create(self):
        """PE-001 remediation should include private-endpoint create command."""
        engine = NetworkSecurityPostureEngine()
        res = _make_paas_resource(
            name="mystorage",
            public_access=True,
            has_private_endpoint=False,
        )

        findings = await engine._check_private_endpoints(
            "sub-1", "all", _paas_resources=[res]
        )
        assert "az network private-endpoint create" in findings[0].remediation

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passed_finding_has_empty_remediation(self):
        """Passed findings should have empty remediation strings."""
        engine = NetworkSecurityPostureEngine()
        vnet = _make_vnet(dns_servers=["10.0.0.4"])

        findings = await engine._check_vnet_custom_dns(
            "sub-1", "all", _vnets=[vnet]
        )
        assert findings[0].status == "passed"
        assert findings[0].remediation == ""


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary and edge-case tests."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assess_posture_all_passed(self):
        """End-to-end: when all checks pass the score should be 100."""
        engine = NetworkSecurityPostureEngine()

        async def _all_passed(sub, scope, **kwargs):
            return [
                ComplianceFinding(
                    rule_id="TEST", severity="High", resource_id="id-1",
                    resource_type="t", status="passed", description="ok",
                    remediation="", risk_description=""
                )
            ]

        for rule in engine._rules["cis_azure"]:
            rule.check_function = _all_passed

        report = await engine.assess_posture("sub-1", "cis_azure", "all")
        assert report.overall_score == 100.0
        assert report.compliance_percentage == 100.0
        assert all(f.status == "passed" for f in report.findings)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assess_posture_all_failed(self):
        """End-to-end: when all checks fail the score should be 0."""
        engine = NetworkSecurityPostureEngine()

        async def _all_failed(sub, scope, **kwargs):
            return [
                ComplianceFinding(
                    rule_id="TEST", severity="High", resource_id="id-1",
                    resource_type="t", status="failed", description="bad",
                    remediation="fix it", risk_description="risk"
                )
            ]

        for rule in engine._rules["cis_azure"]:
            rule.check_function = _all_failed

        report = await engine.assess_posture("sub-1", "cis_azure", "all")
        assert report.overall_score == 0.0
        assert report.compliance_percentage == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assess_posture_no_resources(self):
        """End-to-end: if every check returns empty findings score is 100."""
        engine = NetworkSecurityPostureEngine()

        async def _no_findings(sub, scope, **kwargs):
            return []

        for rule in engine._rules["cis_azure"]:
            rule.check_function = _no_findings

        report = await engine.assess_posture("sub-1", "cis_azure", "all")
        assert report.findings == []
        assert report.overall_score == 100.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_error_is_silently_skipped(self):
        """If a check function raises, it should be silently skipped (returns [])."""
        engine = NetworkSecurityPostureEngine()

        async def _raises(sub, scope, **kwargs):
            raise RuntimeError("Azure SDK unavailable in test")

        for rule in engine._rules["cis_azure"]:
            rule.check_function = _raises

        # Should not raise; just returns empty
        report = await engine.assess_posture("sub-1", "cis_azure", "all")
        assert report.findings == []
        assert report.overall_score == 100.0

    def test_posture_report_dataclass_fields(self):
        """PostureReport should be a proper dataclass with expected fields."""
        report = PostureReport(
            overall_score=75.0,
            findings=[],
            summary_by_severity={"High": {"passed": 1, "failed": 1}},
            summary_by_category={"NSG": {"passed": 1, "failed": 1}},
            compliance_percentage=50.0,
        )
        assert report.overall_score == 75.0
        assert report.compliance_percentage == 50.0
        assert "assessed_at" in report.__dataclass_fields__

    def test_compliance_finding_dataclass_fields(self):
        """ComplianceFinding should store all required fields."""
        finding = ComplianceFinding(
            rule_id="NSG-001",
            severity="Critical",
            resource_id="/subscriptions/sub/...",
            resource_type="Microsoft.Network/networkSecurityGroups",
            status="failed",
            description="Open SSH",
            remediation="Restrict IP",
            risk_description="Brute force risk",
        )
        assert finding.rule_id == "NSG-001"
        assert finding.status == "failed"

    def test_summary_by_severity_structure(self):
        """_summarise_by_severity should return nested dict keyed by severity."""
        engine = NetworkSecurityPostureEngine()
        findings = [
            ComplianceFinding("R1", "Critical", "id-1", "t", "failed", "", "", ""),
            ComplianceFinding("R2", "Critical", "id-2", "t", "passed", "", "", ""),
            ComplianceFinding("R3", "High", "id-3", "t", "failed", "", "", ""),
        ]
        summary = engine._summarise_by_severity(findings)
        assert summary["Critical"]["failed"] == 1
        assert summary["Critical"]["passed"] == 1
        assert summary["High"]["failed"] == 1

    def test_summary_by_category_structure(self):
        """_summarise_by_category should group by rule ID prefix."""
        engine = NetworkSecurityPostureEngine()
        findings = [
            ComplianceFinding("NSG-001", "Critical", "id-1", "t", "failed", "", "", ""),
            ComplianceFinding("NSG-002", "High", "id-2", "t", "passed", "", "", ""),
            ComplianceFinding("ROUTE-001", "High", "id-3", "t", "failed", "", "", ""),
        ]
        summary = engine._summarise_by_category(findings)
        assert summary["NSG"]["failed"] == 1
        assert summary["NSG"]["passed"] == 1
        assert summary["ROUTE"]["failed"] == 1

    def test_parse_resource_group_from_id(self):
        """_parse_resource_group should extract RG from a full resource ID."""
        engine = NetworkSecurityPostureEngine()
        resource_id = "/subscriptions/sub-1/resourceGroups/my-prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-1"
        assert engine._parse_resource_group(resource_id) == "my-prod-rg"

    def test_parse_resource_group_missing_returns_unknown(self):
        """_parse_resource_group should return 'unknown' for malformed IDs."""
        engine = NetworkSecurityPostureEngine()
        assert engine._parse_resource_group("") == "unknown"
        assert engine._parse_resource_group("/some/random/path") == "unknown"
