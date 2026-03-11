"""
Tests for CVE Alert History Manager

Tests CRUD operations, filtering, acknowledge, dismiss, and escalation queries.
"""

import pytest
from datetime import datetime, timezone, timedelta
from models.cve_alert_models import CVEAlertHistoryRecord
from utils.cve_alert_history_manager import get_cve_alert_history_manager


@pytest.mark.asyncio
async def test_create_history_record():
    """Test creating alert history record"""
    manager = get_cve_alert_history_manager()

    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_ids=["CVE-2024-0001", "CVE-2024-0002"],
        cve_count=2,
        affected_vm_count=5,
        affected_vms=["vm1", "vm2", "vm3"],
        affected_vm_names=["VM-1", "VM-2", "VM-3"],
        severity_breakdown={"CRITICAL": 2},
        recipients=["admin@example.com"],
        channels_sent=["email", "teams"],
        status="success",
        scan_id="scan-123"
    )

    created = await manager.create_record(record)

    assert created.id is not None
    assert created.alert_type == "critical"
    assert created.cve_count == 2
    assert created.affected_vm_count == 5
    assert len(created.cve_ids) == 2
    assert created.acknowledged is False
    assert created.dismissed is False
    assert created.escalated is False


@pytest.mark.asyncio
async def test_get_record():
    """Test fetching alert history record by ID"""
    manager = get_cve_alert_history_manager()

    # Create record
    record = CVEAlertHistoryRecord(
        alert_type="high",
        cve_ids=["CVE-2024-0003"],
        cve_count=1,
        affected_vm_count=2
    )
    created = await manager.create_record(record)

    # Fetch by ID
    fetched = await manager.get_record(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.alert_type == "high"
    assert len(fetched.cve_ids) == 1


@pytest.mark.asyncio
async def test_query_history_by_alert_type():
    """Test querying history by alert type"""
    manager = get_cve_alert_history_manager()

    # Create critical alert
    critical = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1
    )
    await manager.create_record(critical)

    # Create high alert
    high = CVEAlertHistoryRecord(
        alert_type="high",
        cve_count=1,
        affected_vm_count=1
    )
    await manager.create_record(high)

    # Query critical only
    results = await manager.query_history({"alert_type": "critical"}, limit=100)

    assert len(results) > 0
    assert all(r.alert_type == "critical" for r in results)


@pytest.mark.asyncio
async def test_query_history_by_date_range():
    """Test querying history by date range"""
    manager = get_cve_alert_history_manager()

    # Create record with specific timestamp
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).isoformat()

    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        timestamp=yesterday
    )
    await manager.create_record(record)

    # Query with date filter
    two_days_ago = (now - timedelta(days=2)).isoformat()
    results = await manager.query_history(
        {"start_date": two_days_ago, "end_date": now.isoformat()},
        limit=100
    )

    assert len(results) > 0


@pytest.mark.asyncio
async def test_acknowledge_alert():
    """Test acknowledging alert"""
    manager = get_cve_alert_history_manager()

    # Create record
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1
    )
    created = await manager.create_record(record)

    # Acknowledge
    success = await manager.acknowledge(
        created.id,
        user="test_user",
        note="Reviewed and patching"
    )

    assert success is True

    # Verify acknowledgment
    updated = await manager.get_record(created.id)
    assert updated.acknowledged is True
    assert updated.acknowledged_by == "test_user"
    assert updated.acknowledged_note == "Reviewed and patching"
    assert updated.acknowledged_at is not None


@pytest.mark.asyncio
async def test_dismiss_alert():
    """Test dismissing alert"""
    manager = get_cve_alert_history_manager()

    # Create record
    record = CVEAlertHistoryRecord(
        alert_type="high",
        cve_count=1,
        affected_vm_count=1
    )
    created = await manager.create_record(record)

    # Dismiss
    success = await manager.dismiss(
        created.id,
        reason="False positive - already patched"
    )

    assert success is True

    # Verify dismissal
    updated = await manager.get_record(created.id)
    assert updated.dismissed is True
    assert updated.dismissed_reason == "False positive - already patched"
    assert updated.dismissed_at is not None


@pytest.mark.asyncio
async def test_mark_escalated():
    """Test marking alert as escalated"""
    manager = get_cve_alert_history_manager()

    # Create record
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1
    )
    created = await manager.create_record(record)

    # Mark escalated
    success = await manager.mark_escalated(created.id)

    assert success is True

    # Verify escalation
    updated = await manager.get_record(created.id)
    assert updated.escalated is True
    assert updated.escalated_at is not None


@pytest.mark.asyncio
async def test_get_unacknowledged_critical():
    """Test querying unacknowledged critical alerts for escalation"""
    manager = get_cve_alert_history_manager()

    # Create old unacknowledged critical alert
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    record = CVEAlertHistoryRecord(
        alert_type="critical",
        cve_count=1,
        affected_vm_count=1,
        timestamp=old_time
    )
    created = await manager.create_record(record)

    # Query for escalation (cutoff 24 hours ago)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    results = await manager.get_unacknowledged_critical(cutoff)

    assert len(results) > 0
    assert all(r.alert_type == "critical" for r in results)
    assert all(not r.acknowledged for r in results)
    assert all(not r.dismissed for r in results)
    assert all(not r.escalated for r in results)


@pytest.mark.asyncio
async def test_query_history_pagination():
    """Test pagination in query_history"""
    manager = get_cve_alert_history_manager()

    # Create multiple records
    for i in range(5):
        record = CVEAlertHistoryRecord(
            alert_type="medium",
            cve_count=1,
            affected_vm_count=1
        )
        await manager.create_record(record)

    # Query with pagination
    page1 = await manager.query_history({}, limit=2, offset=0)
    page2 = await manager.query_history({}, limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id  # Different records


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
