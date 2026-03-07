"""
CVE Alert Rules API

API endpoints for managing CVE alert rules.
Provides CRUD operations and test alert functionality.
"""

from fastapi import APIRouter, Query
from typing import Dict, Any
from datetime import datetime, timezone

from utils.response_models import StandardResponse
from utils.cve_alert_rule_manager import get_cve_alert_rule_manager
from utils.cve_alert_dispatcher import get_cve_alert_dispatcher
from models.cve_alert_models import CVEAlertRule, CVEAlertItem, CVEDelta
from utils.logger import get_logger
from utils.config import config


router = APIRouter()
logger = get_logger(__name__, config.app.log_level)


@router.get("/alerts")
async def list_alert_rules(enabled_only: bool = Query(False)) -> StandardResponse:
    """
    List all CVE alert rules.

    Args:
        enabled_only: If true, only return enabled rules

    Returns:
        List of alert rules
    """
    rule_manager = get_cve_alert_rule_manager()
    rules = await rule_manager.list_rules(enabled_only=enabled_only)

    return StandardResponse(
        status="success",
        message=f"Retrieved {len(rules)} alert rules",
        data={
            "rules": [rule.to_dict() for rule in rules],
            "count": len(rules)
        }
    )


@router.post("/alerts")
async def create_alert_rule(rule_data: Dict[str, Any]) -> StandardResponse:
    """
    Create new CVE alert rule.

    Body:
        name: Rule name (required)
        description: Rule description
        enabled: Enable rule (default: true)
        severity_levels: List of severities to alert on
        min_cvss_score: Minimum CVSS score
        vm_resource_groups: Filter by resource groups
        vm_tags: Filter by VM tags
        email_recipients: Email addresses
        teams_enabled: Enable Teams alerts
        scan_schedule_cron: Custom cron schedule
        enable_escalation: Enable escalation
        escalation_timeout_hours: Hours before escalation

    Returns:
        Created alert rule
    """
    try:
        # Validate required fields
        if "name" not in rule_data or not rule_data["name"]:
            return StandardResponse(
                status="error",
                message="Rule name is required"
            )

        # Create rule object
        rule = CVEAlertRule(**rule_data)

        # Persist via manager
        rule_manager = get_cve_alert_rule_manager()
        created_rule = await rule_manager.create_rule(rule)

        return StandardResponse(
            status="success",
            message=f"Alert rule '{created_rule.name}' created",
            data={"rule": created_rule.to_dict()}
        )

    except ValueError as e:
        return StandardResponse(
            status="error",
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}")
        return StandardResponse(
            status="error",
            message="Failed to create alert rule"
        )


@router.get("/alerts/{rule_id}")
async def get_alert_rule(rule_id: str) -> StandardResponse:
    """Get alert rule by ID"""
    rule_manager = get_cve_alert_rule_manager()
    rule = await rule_manager.get_rule(rule_id)

    if not rule:
        return StandardResponse(
            status="error",
            message=f"Alert rule {rule_id} not found"
        )

    return StandardResponse(
        status="success",
        message="Alert rule retrieved",
        data={"rule": rule.to_dict()}
    )


@router.put("/alerts/{rule_id}")
async def update_alert_rule(rule_id: str, rule_data: Dict[str, Any]) -> StandardResponse:
    """
    Update existing alert rule.

    Body: Same fields as create, all optional
    """
    try:
        rule_manager = get_cve_alert_rule_manager()

        # Fetch existing rule
        existing = await rule_manager.get_rule(rule_id)
        if not existing:
            return StandardResponse(
                status="error",
                message=f"Alert rule {rule_id} not found"
            )

        # Update fields
        for key, value in rule_data.items():
            if hasattr(existing, key) and key not in ["id", "created_at", "created_by"]:
                setattr(existing, key, value)

        # Persist changes
        updated_rule = await rule_manager.update_rule(existing)

        return StandardResponse(
            status="success",
            message=f"Alert rule '{updated_rule.name}' updated",
            data={"rule": updated_rule.to_dict()}
        )

    except ValueError as e:
        return StandardResponse(
            status="error",
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update alert rule: {e}")
        return StandardResponse(
            status="error",
            message="Failed to update alert rule"
        )


@router.delete("/alerts/{rule_id}")
async def delete_alert_rule(rule_id: str) -> StandardResponse:
    """Delete alert rule by ID"""
    rule_manager = get_cve_alert_rule_manager()
    success = await rule_manager.delete_rule(rule_id)

    if not success:
        return StandardResponse(
            status="error",
            message=f"Alert rule {rule_id} not found"
        )

    return StandardResponse(
        status="success",
        message="Alert rule deleted"
    )


@router.post("/alerts/{rule_id}/test")
async def test_alert_rule(rule_id: str) -> StandardResponse:
    """
    Send test alert using rule configuration.

    Generates sample CVE alert and sends via configured channels.
    """
    try:
        rule_manager = get_cve_alert_rule_manager()
        rule = await rule_manager.get_rule(rule_id)

        if not rule:
            return StandardResponse(
                status="error",
                message=f"Alert rule {rule_id} not found"
            )

        # Create mock CVE alert item
        mock_cve = CVEAlertItem(
            cve_id="CVE-2024-TEST",
            severity="HIGH",
            cvss_score=8.5,
            affected_vms=["vm-test-001"],
            affected_vm_names=["test-vm"],
            published_date=datetime.now(timezone.utc).isoformat(),
            patch_available=True,
            description="Test alert for rule validation"
        )

        # Send via alert dispatcher
        alert_dispatcher = get_cve_alert_dispatcher()
        mock_delta = CVEDelta(
            new_cves=[mock_cve],
            resolved_cves=[],
            severity_changes=[],
            is_first_scan=False,
            current_scan_id="test-scan"
        )

        result = await alert_dispatcher.send_cve_alerts(
            delta=mock_delta,
            severity_threshold=rule.severity_levels[0] if rule.severity_levels else "HIGH",
            rule=rule  # Pass rule for custom recipients/channels
        )

        return StandardResponse(
            status="success",
            message="Test alert sent",
            data={"result": result}
        )

    except Exception as e:
        logger.error(f"Failed to send test alert: {e}")
        return StandardResponse(
            status="error",
            message=f"Failed to send test alert: {str(e)}"
        )
