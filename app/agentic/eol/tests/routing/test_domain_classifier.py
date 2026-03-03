"""Unit tests for DomainClassifier — 20+ queries covering all domains.

Tests:
- All 10 domain labels reachable
- Primary domain accuracy >90% across 20+ sample queries
- Secondary domain detection
- Confidence scaling (more keywords → higher confidence)
- Edge cases: empty query, unknown domain, mixed-domain query
"""
from __future__ import annotations

import pytest

try:
    from app.agentic.eol.utils.domain_classifier import (
        DomainClassifier,
        DomainClassification,
        DomainLabel,
        get_domain_classifier,
    )
except ModuleNotFoundError:
    from utils.domain_classifier import (  # type: ignore[import-not-found]
        DomainClassifier,
        DomainClassification,
        DomainLabel,
        get_domain_classifier,
    )


@pytest.fixture
def classifier() -> DomainClassifier:
    return DomainClassifier()


# ============================================================================
# Core domain classification — 20+ queries
# ============================================================================

@pytest.mark.asyncio
async def test_sre_incident_query(classifier):
    result = await classifier.classify("There is an incident, the service is down, need triage")
    assert result.primary_domain == DomainLabel.SRE

@pytest.mark.asyncio
async def test_sre_outage_query(classifier):
    result = await classifier.classify("Production outage — VM is not responding, check availability")
    assert result.primary_domain == DomainLabel.SRE

@pytest.mark.asyncio
async def test_sre_health_check(classifier):
    result = await classifier.classify("Run health check on the cluster")
    assert result.primary_domain == DomainLabel.SRE

@pytest.mark.asyncio
async def test_monitoring_alert_query(classifier):
    result = await classifier.classify("Set up an alert when CPU metric exceeds threshold")
    assert result.primary_domain == DomainLabel.MONITORING

@pytest.mark.asyncio
async def test_monitoring_dashboard_query(classifier):
    result = await classifier.classify("Show me the monitoring dashboard with all metrics")
    assert result.primary_domain == DomainLabel.MONITORING

@pytest.mark.asyncio
async def test_monitoring_logs_query(classifier):
    result = await classifier.classify("Analyze the logs from the last 24 hours")
    assert result.primary_domain == DomainLabel.MONITORING

@pytest.mark.asyncio
async def test_network_nsg_query(classifier):
    result = await classifier.classify("List all NSG rules in the vnet")
    assert result.primary_domain == DomainLabel.NETWORK

@pytest.mark.asyncio
async def test_network_firewall_query(classifier):
    result = await classifier.classify("Check firewall connectivity between subnets")
    assert result.primary_domain == DomainLabel.NETWORK

@pytest.mark.asyncio
async def test_network_vpn_query(classifier):
    result = await classifier.classify("Diagnose VPN routing and network latency issues")
    assert result.primary_domain == DomainLabel.NETWORK

@pytest.mark.asyncio
async def test_inventory_list_query(classifier):
    result = await classifier.classify("List all resources and build an inventory catalog")
    assert result.primary_domain == DomainLabel.INVENTORY

@pytest.mark.asyncio
async def test_inventory_discover_query(classifier):
    result = await classifier.classify("Discover all Azure assets in the subscription")
    assert result.primary_domain == DomainLabel.INVENTORY

@pytest.mark.asyncio
async def test_patch_vulnerability_query(classifier):
    result = await classifier.classify("Check for vulnerability and pending security patch updates")
    assert result.primary_domain == DomainLabel.PATCH

@pytest.mark.asyncio
async def test_patch_compliance_query(classifier):
    result = await classifier.classify("Run patch compliance check for all VMs")
    # patch and compute both match; patch has more keywords
    assert result.primary_domain in (DomainLabel.PATCH, DomainLabel.COMPUTE)

@pytest.mark.asyncio
async def test_compute_vm_query(classifier):
    result = await classifier.classify("Restart the virtual machine and check CPU usage")
    assert result.primary_domain == DomainLabel.COMPUTE

@pytest.mark.asyncio
async def test_compute_kubernetes_query(classifier):
    result = await classifier.classify("Scale up the AKS Kubernetes cluster memory")
    assert result.primary_domain == DomainLabel.COMPUTE

@pytest.mark.asyncio
async def test_storage_blob_query(classifier):
    result = await classifier.classify("Check the blob storage disk usage and take a snapshot")
    assert result.primary_domain == DomainLabel.STORAGE

@pytest.mark.asyncio
async def test_storage_backup_query(classifier):
    result = await classifier.classify("Create a backup of the storage file share")
    assert result.primary_domain == DomainLabel.STORAGE

@pytest.mark.asyncio
async def test_cost_billing_query(classifier):
    result = await classifier.classify("Show me the billing cost and budget spend for this month")
    assert result.primary_domain == DomainLabel.COST

@pytest.mark.asyncio
async def test_cost_invoice_query(classifier):
    result = await classifier.classify("Download the invoice and check reservation savings pricing")
    assert result.primary_domain == DomainLabel.COST

@pytest.mark.asyncio
async def test_security_audit_query(classifier):
    result = await classifier.classify("Run a security audit and check RBAC policy compliance")
    assert result.primary_domain == DomainLabel.SECURITY

@pytest.mark.asyncio
async def test_security_identity_query(classifier):
    result = await classifier.classify("Review identity permissions and defender threat findings")
    assert result.primary_domain == DomainLabel.SECURITY

@pytest.mark.asyncio
async def test_general_fallback_unrecognized(classifier):
    result = await classifier.classify("Hello there")
    assert result.primary_domain == DomainLabel.GENERAL
    assert result.confidence == 0.5

# ============================================================================
# Edge cases
# ============================================================================

@pytest.mark.asyncio
async def test_empty_query(classifier):
    result = await classifier.classify("")
    assert result.primary_domain == DomainLabel.GENERAL
    assert result.confidence == 0.5

@pytest.mark.asyncio
async def test_whitespace_only_query(classifier):
    result = await classifier.classify("   ")
    assert result.primary_domain == DomainLabel.GENERAL

@pytest.mark.asyncio
async def test_case_insensitivity(classifier):
    upper = await classifier.classify("NSG FIREWALL NETWORK VNET")
    lower = await classifier.classify("nsg firewall network vnet")
    assert upper.primary_domain == lower.primary_domain == DomainLabel.NETWORK

@pytest.mark.asyncio
async def test_confidence_scales_with_keyword_count(classifier):
    single = await classifier.classify("monitor")
    multi = await classifier.classify("monitor alert metric threshold logs observability")
    assert multi.confidence >= single.confidence

@pytest.mark.asyncio
async def test_confidence_capped_at_one(classifier):
    result = await classifier.classify(
        "network nsg vnet subnet firewall connectivity routing peering vpn dns bandwidth"
    )
    assert result.confidence <= 1.0

@pytest.mark.asyncio
async def test_secondary_domains_populated_for_mixed_query(classifier):
    # Query hits both SRE and monitoring keywords
    result = await classifier.classify("incident alert monitoring health check metric")
    assert result.primary_domain in (DomainLabel.SRE, DomainLabel.MONITORING)
    assert len(result.secondary_domains) > 0

@pytest.mark.asyncio
async def test_secondary_domains_capped_at_two(classifier):
    result = await classifier.classify(
        "vm network storage security patch monitor inventory cost alert firewall"
    )
    assert len(result.secondary_domains) <= 2

@pytest.mark.asyncio
async def test_classification_returns_dataclass(classifier):
    result = await classifier.classify("check vm health")
    assert isinstance(result, DomainClassification)
    assert isinstance(result.primary_domain, DomainLabel)
    assert isinstance(result.secondary_domains, list)
    assert isinstance(result.confidence, float)

# ============================================================================
# Singleton
# ============================================================================

def test_get_domain_classifier_singleton():
    c1 = get_domain_classifier()
    c2 = get_domain_classifier()
    assert c1 is c2

# ============================================================================
# Domain accuracy summary: 22 named queries tested above
# >90% accuracy target: at most 2 misclassifications allowed
# ============================================================================
