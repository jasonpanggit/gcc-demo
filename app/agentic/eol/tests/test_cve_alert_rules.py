"""
Tests for CVE Alert Rules Management

Tests CRUD operations, validation, and API endpoints for CVE alert rules.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest_asyncio

from api.cve_alerts import router as cve_alerts_router
from models.cve_alert_models import CVEAlertRule, CVEAlertItem, CVEDelta
import utils.cve_alert_rule_manager as cve_alert_rule_manager_module
from utils.cve_alert_rule_manager import CVEAlertRuleManager, get_cve_alert_rule_manager


@pytest.fixture
def sample_rule_data() -> Dict[str, Any]:
    """Sample alert rule data for testing"""
    return {
        "name": "Test Production Alerts",
        "description": "Alert on critical CVEs in production VMs",
        "enabled": True,
        "rule_type": "delta",
        "severity_levels": ["CRITICAL", "HIGH"],
        "min_cvss_score": 7.0,
        "vm_resource_groups": ["rg-prod"],
        "email_recipients": ["admin@example.com"],
        "teams_enabled": True,
        "enable_escalation": False
    }


@pytest_asyncio.fixture
async def rule_manager():
    """Get alert rule manager instance"""
    manager = CVEAlertRuleManager()
    cve_alert_rule_manager_module._alert_rule_manager = manager
    yield manager
    manager._store.clear()
    cve_alert_rule_manager_module._alert_rule_manager = None


class FakeAlertRepo:
    def __init__(self):
        self.rules = {}

    async def list_rules(self, enabled_only=False):
        rules = list(self.rules.values())
        if enabled_only:
            rules = [rule for rule in rules if rule.get("enabled")]
        return rules

    async def create_rule(self, rule_data):
        self.rules[rule_data["id"]] = dict(rule_data)
        return self.rules[rule_data["id"]]

    async def get_rule(self, rule_id):
        return self.rules.get(rule_id)

    async def update_rule(self, rule_data):
        self.rules[rule_data["id"]] = dict(rule_data)
        return self.rules[rule_data["id"]]

    async def delete_rule(self, rule_id):
        return self.rules.pop(rule_id, None) is not None


@pytest_asyncio.fixture
async def cve_alert_api_client(monkeypatch):
    app = FastAPI()
    app.include_router(cve_alerts_router, prefix="/api/cve")
    app.state.alert_repo = FakeAlertRepo()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ============================================================================
# Alert Rule Manager Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_alert_rule(rule_manager, sample_rule_data):
    """Test creating an alert rule"""
    rule = CVEAlertRule(**sample_rule_data)
    created_rule = await rule_manager.create_rule(rule)

    assert created_rule.id is not None
    assert created_rule.name == sample_rule_data["name"]
    assert created_rule.enabled is True
    assert "CRITICAL" in created_rule.severity_levels
    assert created_rule.created_at is not None
    assert created_rule.updated_at is not None


@pytest.mark.asyncio
async def test_create_duplicate_rule_fails(rule_manager, sample_rule_data):
    """Test that creating a rule with duplicate name fails"""
    # Create first rule
    rule1 = CVEAlertRule(**sample_rule_data)
    await rule_manager.create_rule(rule1)

    # Attempt to create duplicate
    rule2 = CVEAlertRule(**sample_rule_data)
    with pytest.raises(ValueError, match="already exists"):
        await rule_manager.create_rule(rule2)


@pytest.mark.asyncio
async def test_get_rule_by_id(rule_manager, sample_rule_data):
    """Test fetching rule by ID"""
    rule = CVEAlertRule(**sample_rule_data)
    created_rule = await rule_manager.create_rule(rule)

    fetched_rule = await rule_manager.get_rule(created_rule.id)

    assert fetched_rule is not None
    assert fetched_rule.id == created_rule.id
    assert fetched_rule.name == created_rule.name
    assert fetched_rule.severity_levels == created_rule.severity_levels


@pytest.mark.asyncio
async def test_list_rules_enabled_only(rule_manager):
    """Test listing rules with enabled filter"""
    # Create enabled rule
    rule1_data = {
        "name": "Enabled Rule",
        "enabled": True,
        "severity_levels": ["CRITICAL"]
    }
    rule1 = CVEAlertRule(**rule1_data)
    await rule_manager.create_rule(rule1)

    # Create disabled rule
    rule2_data = {
        "name": "Disabled Rule",
        "enabled": False,
        "severity_levels": ["HIGH"]
    }
    rule2 = CVEAlertRule(**rule2_data)
    await rule_manager.create_rule(rule2)

    # List enabled only
    enabled_rules = await rule_manager.list_rules(enabled_only=True)

    assert len(enabled_rules) >= 1
    assert all(rule.enabled for rule in enabled_rules)
    assert any(rule.name == "Enabled Rule" for rule in enabled_rules)


@pytest.mark.asyncio
async def test_update_rule(rule_manager, sample_rule_data):
    """Test updating an alert rule"""
    rule = CVEAlertRule(**sample_rule_data)
    created_rule = await rule_manager.create_rule(rule)

    # Update rule
    created_rule.name = "Updated Production Alerts"
    created_rule.severity_levels = ["CRITICAL"]

    updated_rule = await rule_manager.update_rule(created_rule)

    assert updated_rule.name == "Updated Production Alerts"
    assert updated_rule.severity_levels == ["CRITICAL"]
    assert updated_rule.updated_at != created_rule.created_at


@pytest.mark.asyncio
async def test_delete_rule(rule_manager, sample_rule_data):
    """Test deleting an alert rule"""
    rule = CVEAlertRule(**sample_rule_data)
    created_rule = await rule_manager.create_rule(rule)

    # Delete rule
    success = await rule_manager.delete_rule(created_rule.id)
    assert success is True

    # Verify rule no longer exists
    fetched_rule = await rule_manager.get_rule(created_rule.id)
    assert fetched_rule is None


@pytest.mark.asyncio
async def test_update_last_triggered(rule_manager, sample_rule_data):
    """Test updating last_triggered timestamp"""
    rule = CVEAlertRule(**sample_rule_data)
    created_rule = await rule_manager.create_rule(rule)

    # Update last_triggered
    timestamp = datetime.now(timezone.utc).isoformat()
    await rule_manager.update_last_triggered(created_rule.id, timestamp)

    # Verify update
    updated_rule = await rule_manager.get_rule(created_rule.id)
    assert updated_rule.last_triggered == timestamp


# ============================================================================
# Rule Validation Tests
# ============================================================================

def test_rule_validation_invalid_severity():
    """Test that invalid severity levels raise error"""
    with pytest.raises(ValueError, match="Invalid severity levels"):
        CVEAlertRule(
            name="Invalid Rule",
            severity_levels=["INVALID", "CRITICAL"]
        )


def test_rule_validation_cvss_range():
    """Test CVSS score range validation"""
    # Min > Max should fail
    with pytest.raises(ValueError, match="min_cvss_score must be"):
        CVEAlertRule(
            name="Invalid Range",
            severity_levels=["HIGH"],
            min_cvss_score=8.0,
            max_cvss_score=5.0
        )


def test_rule_validation_cvss_bounds():
    """Test CVSS score bounds validation"""
    # Score > 10 should fail
    with pytest.raises(ValueError, match="CVSS score must be between 0 and 10"):
        CVEAlertRule(
            name="Invalid Score",
            severity_levels=["HIGH"],
            min_cvss_score=11.0
        )

    # Score < 0 should fail
    with pytest.raises(ValueError, match="CVSS score must be between 0 and 10"):
        CVEAlertRule(
            name="Invalid Score",
            severity_levels=["HIGH"],
            max_cvss_score=-1.0
        )


# ============================================================================
# API Endpoint Tests (Integration)
# ============================================================================

@pytest.mark.asyncio
async def test_api_create_rule(cve_alert_api_client):
    """Test POST /api/cve/alerts"""
    rule_data = {
        "name": "API Test Rule",
        "description": "Created via API",
        "enabled": True,
        "severity_levels": ["CRITICAL"],
        "email_recipients": ["test@example.com"]
    }

    response = await cve_alert_api_client.post("/api/cve/alerts", json=rule_data)
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True
    assert "rule" in result["data"]
    assert result["data"]["rule"]["name"] == "API Test Rule"


@pytest.mark.asyncio
async def test_api_list_rules(cve_alert_api_client):
    """Test GET /api/cve/alerts"""
    response = await cve_alert_api_client.get("/api/cve/alerts")
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True
    assert "rules" in result["data"]
    assert isinstance(result["data"]["rules"], list)


@pytest.mark.asyncio
async def test_api_get_rule(cve_alert_api_client, sample_rule_data):
    """Test GET /api/cve/alerts/{id}"""
    create_response = await cve_alert_api_client.post("/api/cve/alerts", json=sample_rule_data)
    created_rule = create_response.json()["data"]["rule"]

    # Fetch via API
    response = await cve_alert_api_client.get(f"/api/cve/alerts/{created_rule['id']}")
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True
    assert result["data"]["rule"]["id"] == created_rule["id"]


@pytest.mark.asyncio
async def test_api_update_rule(cve_alert_api_client, sample_rule_data):
    """Test PUT /api/cve/alerts/{id}"""
    create_response = await cve_alert_api_client.post("/api/cve/alerts", json=sample_rule_data)
    created_rule = create_response.json()["data"]["rule"]

    # Update via API
    update_data = {"name": "Updated via API"}
    response = await cve_alert_api_client.put(f"/api/cve/alerts/{created_rule['id']}", json=update_data)
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True
    assert result["data"]["rule"]["name"] == "Updated via API"


@pytest.mark.asyncio
async def test_api_delete_rule(cve_alert_api_client, sample_rule_data):
    """Test DELETE /api/cve/alerts/{id}"""
    create_response = await cve_alert_api_client.post("/api/cve/alerts", json=sample_rule_data)
    created_rule = create_response.json()["data"]["rule"]

    # Delete via API
    response = await cve_alert_api_client.delete(f"/api/cve/alerts/{created_rule['id']}")
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True


@pytest.mark.asyncio
async def test_api_test_alert(cve_alert_api_client, sample_rule_data, monkeypatch):
    """Test POST /api/cve/alerts/{id}/test"""
    create_response = await cve_alert_api_client.post("/api/cve/alerts", json=sample_rule_data)
    created_rule = create_response.json()["data"]["rule"]

    # Mock alert dispatcher
    class FakeDispatcher:
        async def send_cve_alerts(self, **_kwargs):
            return {"sent": True}

    monkeypatch.setattr("api.cve_alerts.get_cve_alert_dispatcher", lambda: FakeDispatcher())

    # Send test alert
    response = await cve_alert_api_client.post(f"/api/cve/alerts/{created_rule['id']}/test")
    assert response.status_code == 200

    result = response.json()
    assert result["success"] is True
