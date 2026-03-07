"""
End-to-End Tests for CVE Monitoring Workflows

Tests full scan-detect-alert-history-escalate workflows.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock
from models.cve_alert_models import CVEDelta, CVEAlertItem, CVEAlertHistoryRecord
from utils.cve_alert_dispatcher import CVEAlertDispatcher
from utils.cve_alert_history_manager import get_cve_alert_history_manager
from utils.cve_escalation_service import check_and_escalate_alerts


@pytest.mark.asyncio
async def test_full_scan_alert_workflow():
    """Test complete workflow: scan → detect → alert → history"""
    # Mock scan and detection
    delta = CVEDelta(
        new_cves=[
            CVEAlertItem(
                cve_id="CVE-2024-TEST-001",
                severity="CRITICAL",
                cvss_score=9.8,
                affected_vms=["vm1", "vm2"],
                affected_vm_names=["VM-1", "VM-2"],
                published_date="2024-03-08",
                patch_available=True,
                patch_kb_ids=["KB123456"]
            )
        ],
        resolved_cves=[],
        severity_changes=[],
        is_first_scan=False,
        current_scan_id="scan-test-001",
        current_timestamp=datetime.now(timezone.utc).isoformat()
    )

    # Mock alert manager
    with patch('utils.cve_alert_dispatcher.alert_manager') as mock_alert:
        mock_alert.load_configuration = AsyncMock(return_value=MagicMock(email_recipients=["admin@example.com"]))
        mock_alert.send_combined_alert = AsyncMock(return_value={
            "email": {"sent": True},
            "teams": {"sent": True}
        })
        mock_alert.save_notification_record = AsyncMock()

        # Send alerts
        dispatcher = CVEAlertDispatcher()
        result = await dispatcher.send_cve_alerts(delta, severity_threshold="CRITICAL")

        # Verify alert sent
        assert result["alerts_sent"] > 0
        assert len(result["cves_alerted"]) > 0
        assert "CVE-2024-TEST-001" in result["cves_alerted"]

        # Verify history record created
        assert len(result.get("history_records", [])) > 0
        history = result["history_records"][0]
        assert history["cve_count"] == 1
        assert history["alert_type"] == "critical"
        assert "email" in history["channels_sent"]


@pytest.mark.asyncio
async def test_acknowledge_workflow():
    """Test alert acknowledgment workflow"""
    manager = get_cve_alert_history_manager()

    # Create alert history record
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_ids=["CVE-2024-ACK-001"],
        cve_count=1,
        affected_vm_count=2
    )
    created = await manager.create_record(record)

    # Verify initial state
    assert created.acknowledged is False

    # Acknowledge via manager (simulates API call)
    success = await manager.acknowledge(
        created.id,
        user="test_admin",
        note="Patching scheduled for tonight"
    )

    assert success is True

    # Verify updated state
    updated = await manager.get_record(created.id)
    assert updated.acknowledged is True
    assert updated.acknowledged_by == "test_admin"
    assert updated.acknowledged_note == "Patching scheduled for tonight"
    assert updated.acknowledged_at is not None

    # Verify alert no longer appears in unacknowledged queries
    cutoff = datetime.now(timezone.utc).isoformat()
    unack = await manager.get_unacknowledged_critical(cutoff)
    assert created.id not in [r.id for r in unack]


@pytest.mark.asyncio
async def test_escalation_workflow():
    """Test complete escalation workflow: old alert → escalation check → notification → marked"""
    manager = get_cve_alert_history_manager()

    # Create unacknowledged critical alert (backdated 30 hours)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_ids=["CVE-2024-ESC-001", "CVE-2024-ESC-002"],
        cve_count=2,
        affected_vm_count=5,
        affected_vm_names=["VM-1", "VM-2", "VM-3", "VM-4", "VM-5"],
        recipients=["admin@example.com"],
        channels_sent=["email", "teams"],
        status="success",
        scan_id="scan-esc-001",
        timestamp=old_time
    )
    created = await manager.create_record(record)

    # Verify initial state
    assert created.escalated is False

    # Mock alert manager for escalation notification
    with patch('utils.cve_escalation_service.alert_manager') as mock_alert:
        mock_alert.send_email = AsyncMock(return_value={"sent": True})
        mock_alert.send_teams_notification = AsyncMock(return_value={"sent": True})

        # Run escalation check
        summary = await check_and_escalate_alerts()

        # Verify escalation occurred
        assert summary["escalations_sent"] > 0
        assert created.id in summary["escalated_alert_ids"]

        # Verify notification was sent
        mock_alert.send_email.assert_called()

    # Verify alert marked as escalated
    escalated = await manager.get_record(created.id)
    assert escalated.escalated is True
    assert escalated.escalated_at is not None

    # Verify escalated alert no longer appears in escalation query
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pending = await manager.get_unacknowledged_critical(cutoff)
    assert created.id not in [r.id for r in pending]


@pytest.mark.asyncio
async def test_dismiss_workflow():
    """Test alert dismissal workflow"""
    manager = get_cve_alert_history_manager()

    # Create alert
    record = CVEAlertHistoryRecord(
        alert_type="high",
        cve_ids=["CVE-2024-DIS-001"],
        cve_count=1,
        affected_vm_count=1
    )
    created = await manager.create_record(record)

    # Dismiss
    success = await manager.dismiss(
        created.id,
        reason="False positive - vulnerability not applicable to our configuration"
    )

    assert success is True

    # Verify dismissal
    dismissed = await manager.get_record(created.id)
    assert dismissed.dismissed is True
    assert dismissed.dismissed_reason is not None
    assert "False positive" in dismissed.dismissed_reason
    assert dismissed.dismissed_at is not None

    # Verify dismissed alerts excluded from escalation
    if dismissed.alert_type == "critical":
        cutoff = datetime.now(timezone.utc).isoformat()
        pending = await manager.get_unacknowledged_critical(cutoff)
        assert created.id not in [r.id for r in pending]


@pytest.mark.asyncio
async def test_alert_history_filtering():
    """Test comprehensive alert history filtering"""
    manager = get_cve_alert_history_manager()

    # Create multiple alerts with different states
    now = datetime.now(timezone.utc)

    # Unacknowledged critical
    unack_crit = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        timestamp=(now - timedelta(hours=5)).isoformat()
    )
    await manager.create_record(unack_crit)

    # Acknowledged high
    ack_high = CVEAlertHistoryRecord(
        alert_type="high",
        cve_count=2,
        affected_vm_count=2,
        timestamp=(now - timedelta(hours=10)).isoformat()
    )
    created_ack = await manager.create_record(ack_high)
    await manager.acknowledge(created_ack.id, "user1", "Handled")

    # Dismissed medium
    dis_med = CVEAlertHistoryRecord(
        alert_type="medium",
        cve_count=3,
        affected_vm_count=3,
        timestamp=(now - timedelta(days=2)).isoformat()
    )
    created_dis = await manager.create_record(dis_med)
    await manager.dismiss(created_dis.id, "Not applicable")

    # Filter by status
    unack_results = await manager.query_history(
        {"acknowledged": False, "dismissed": False},
        limit=100
    )
    assert len(unack_results) > 0

    ack_results = await manager.query_history(
        {"acknowledged": True},
        limit=100
    )
    assert len(ack_results) > 0

    # Filter by alert type
    crit_results = await manager.query_history(
        {"alert_type": "critical"},
        limit=100
    )
    assert len(crit_results) > 0
    assert all(r.alert_type == "critical" for r in crit_results)

    # Filter by date range
    yesterday = (now - timedelta(days=1)).isoformat()
    recent_results = await manager.query_history(
        {"start_date": yesterday},
        limit=100
    )
    assert len(recent_results) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
