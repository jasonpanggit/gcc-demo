"""
Tests for CVE Escalation Service

Tests escalation logic, notification sending, and alert marking.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from models.cve_alert_models import CVEAlertHistoryRecord
from utils.cve_alert_history_manager import get_cve_alert_history_manager
from utils.cve_escalation_service import check_and_escalate_alerts, send_escalation_notification


@pytest.mark.asyncio
async def test_check_escalations_no_alerts():
    """Test escalation check when no alerts require escalation"""
    with patch('utils.cve_escalation_service.get_cve_alert_history_manager') as mock_manager:
        mock_instance = AsyncMock()
        mock_instance.get_unacknowledged_critical.return_value = []
        mock_manager.return_value = mock_instance

        summary = await check_and_escalate_alerts()

        assert summary["escalations_sent"] == 0
        assert summary["alerts_checked"] == 0


@pytest.mark.asyncio
async def test_check_escalations_with_eligible_alerts():
    """Test escalation check with eligible unacknowledged alerts"""
    manager = get_cve_alert_history_manager()

    # Create old unacknowledged critical alert
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_ids=["CVE-2024-9999"],
        cve_count=1,
        affected_vm_count=1,
        recipients=["admin@example.com"],
        channels_sent=["email"],
        timestamp=old_time
    )
    created = await manager.create_record(record)

    # Mock alert manager to avoid actual notification sending
    with patch('utils.cve_escalation_service.alert_manager') as mock_alert:
        mock_alert.send_email = AsyncMock(return_value={"sent": True})
        mock_alert.send_teams_notification = AsyncMock(return_value={"sent": True})

        summary = await check_and_escalate_alerts()

        assert summary["escalations_sent"] > 0
        assert summary["alerts_checked"] > 0
        assert created.id in summary["escalated_alert_ids"]


@pytest.mark.asyncio
async def test_escalation_skips_acknowledged_alerts():
    """Test that acknowledged alerts are not escalated"""
    manager = get_cve_alert_history_manager()

    # Create old critical alert and acknowledge it
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        timestamp=old_time
    )
    created = await manager.create_record(record)
    await manager.acknowledge(created.id, "test_user", "Already handled")

    # Query for escalation
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    results = await manager.get_unacknowledged_critical(cutoff)

    # Acknowledged alert should not appear
    assert created.id not in [r.id for r in results]


@pytest.mark.asyncio
async def test_escalation_sends_notification():
    """Test that escalation notification is sent"""
    # Create alert
    alert = CVEAlertHistoryRecord(
        id="test-alert-123",
        alert_type="critical",
        cve_ids=["CVE-2024-1111", "CVE-2024-1112"],
        cve_count=2,
        affected_vm_count=3,
        affected_vm_names=["VM-1", "VM-2", "VM-3"],
        recipients=["admin@example.com"],
        channels_sent=["email", "teams"],
        timestamp=(datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    )

    # Mock alert manager
    with patch('utils.cve_escalation_service.alert_manager') as mock_alert:
        mock_alert.send_email = AsyncMock(return_value={"sent": True})
        mock_alert.send_teams_notification = AsyncMock(return_value={"sent": True})

        result = await send_escalation_notification(alert, hours_elapsed=30.5)

        assert result["success"] is True
        mock_alert.send_email.assert_called_once()


@pytest.mark.asyncio
async def test_escalation_marks_alert_as_escalated():
    """Test that alert is marked as escalated after notification"""
    manager = get_cve_alert_history_manager()

    # Create old unacknowledged critical alert
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        recipients=["admin@example.com"],
        channels_sent=["email"],
        timestamp=old_time
    )
    created = await manager.create_record(record)

    # Mock alert manager
    with patch('utils.cve_escalation_service.alert_manager') as mock_alert:
        mock_alert.send_email = AsyncMock(return_value={"sent": True})

        # Run escalation
        await check_and_escalate_alerts()

        # Verify escalation flag
        updated = await manager.get_record(created.id)
        assert updated.escalated is True
        assert updated.escalated_at is not None


@pytest.mark.asyncio
async def test_escalation_handles_send_failure():
    """Test escalation handling when notification send fails"""
    alert = CVEAlertHistoryRecord(
        id="test-alert-456",
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        recipients=["admin@example.com"],
        channels_sent=["email"]
    )

    # Mock alert manager to simulate failure
    with patch('utils.cve_escalation_service.alert_manager') as mock_alert:
        mock_alert.send_email = AsyncMock(side_effect=Exception("Email service unavailable"))

        result = await send_escalation_notification(alert, hours_elapsed=25.0)

        assert result["success"] is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
