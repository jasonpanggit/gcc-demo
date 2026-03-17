"""
CVE Alert Rules API

API endpoints for managing CVE alert rules.
Provides CRUD operations and test alert functionality.
"""

from fastapi import APIRouter, Query, Request
from typing import Dict, Any
from datetime import datetime, timezone

from utils.response_models import StandardResponse
from utils.cve_alert_dispatcher import get_cve_alert_dispatcher
from models.cve_alert_models import CVEAlertRule, CVEAlertItem, CVEDelta
from utils.logger import get_logger
from utils.config import config


router = APIRouter()
logger = get_logger(__name__, config.app.log_level)


@router.get("/alerts")
async def list_alert_rules(request: Request, enabled_only: bool = Query(False)) -> StandardResponse:
    """
    List all CVE alert rules.

    Args:
        enabled_only: If true, only return enabled rules

    Returns:
        List of alert rules
    """
    alert_repo = request.app.state.alert_repo
    rules = await alert_repo.list_rules(enabled_only=enabled_only)

    return StandardResponse(
        success=True,
        message=f"Retrieved {len(rules)} alert rules",
        data={
            "rules": rules,
            "count": len(rules)
        }
    )


@router.post("/alerts")
async def create_alert_rule(request: Request, rule_data: Dict[str, Any]) -> StandardResponse:
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
                success=False,
                message="Rule name is required"
            )

        # Create rule object for validation
        rule = CVEAlertRule(**rule_data)

        # Persist via repository
        alert_repo = request.app.state.alert_repo
        created_rule = await alert_repo.create_rule(rule.to_dict())

        return StandardResponse(
            success=True,
            message=f"Alert rule '{rule.name}' created",
            data={"rule": created_rule}
        )

    except ValueError as e:
        return StandardResponse(
            success=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}")
        return StandardResponse(
            success=False,
            message="Failed to create alert rule"
        )


@router.get("/alerts/{rule_id}")
async def get_alert_rule(request: Request, rule_id: str) -> StandardResponse:
    """Get alert rule by ID"""
    alert_repo = request.app.state.alert_repo
    rule = await alert_repo.get_rule(rule_id)

    if not rule:
        return StandardResponse(
            success=False,
            message=f"Alert rule {rule_id} not found"
        )

    return StandardResponse(
        success=True,
        message="Alert rule retrieved",
        data={"rule": rule}
    )


@router.put("/alerts/{rule_id}")
async def update_alert_rule(request: Request, rule_id: str, rule_data: Dict[str, Any]) -> StandardResponse:
    """
    Update existing alert rule.

    Body: Same fields as create, all optional
    """
    try:
        alert_repo = request.app.state.alert_repo

        # Fetch existing rule
        existing = await alert_repo.get_rule(rule_id)
        if not existing:
            return StandardResponse(
                success=False,
                message=f"Alert rule {rule_id} not found"
            )

        # Update fields (merge new data into existing)
        for key, value in rule_data.items():
            if key not in ["id", "created_at", "created_by"]:
                existing[key] = value

        # Persist changes
        updated_rule = await alert_repo.update_rule(existing)

        return StandardResponse(
            success=True,
            message=f"Alert rule '{existing.get('name', rule_id)}' updated",
            data={"rule": updated_rule}
        )

    except ValueError as e:
        return StandardResponse(
            success=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update alert rule: {e}")
        return StandardResponse(
            success=False,
            message="Failed to update alert rule"
        )


@router.delete("/alerts/{rule_id}")
async def delete_alert_rule(request: Request, rule_id: str) -> StandardResponse:
    """Delete alert rule by ID"""
    alert_repo = request.app.state.alert_repo
    success = await alert_repo.delete_rule(rule_id)

    if not success:
        return StandardResponse(
            success=False,
            message=f"Alert rule {rule_id} not found"
        )

    return StandardResponse(
        success=True,
        message="Alert rule deleted"
    )


@router.post("/alerts/{rule_id}/test")
async def test_alert_rule(request: Request, rule_id: str) -> StandardResponse:
    """
    Send test alert using rule configuration.

    Generates sample CVE alert and sends via configured channels.
    """
    try:
        alert_repo = request.app.state.alert_repo
        rule = await alert_repo.get_rule(rule_id)

        if not rule:
            return StandardResponse(
                success=False,
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

        severity_levels = rule.get("severity_levels", ["HIGH"])
        if isinstance(severity_levels, str):
            import json as _json
            severity_levels = _json.loads(severity_levels)

        result = await alert_dispatcher.send_cve_alerts(
            delta=mock_delta,
            severity_threshold=severity_levels[0] if severity_levels else "HIGH",
        )

        return StandardResponse(
            success=True,
            message="Test alert sent",
            data={"result": result}
        )

    except Exception as e:
        logger.error(f"Failed to send test alert: {e}")
        return StandardResponse(
            success=False,
            message=f"Failed to send test alert: {str(e)}"
        )
