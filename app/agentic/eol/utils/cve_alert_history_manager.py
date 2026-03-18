"""
CVE Alert History Manager

Manages CVE alert history with in-memory persistence.
Provides CRUD operations for alert history records including
acknowledge, dismiss, and escalation tracking.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from models.cve_alert_models import CVEAlertHistoryRecord
from utils.logger import get_logger
from utils.config import config


class CVEAlertHistoryManager:
    """
    Manages CVE alert history with in-memory persistence.

    Container: cve_alert_history
    Partition Key: /alert_type
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger(__name__, config.app.log_level)

    async def create_record(self, record: CVEAlertHistoryRecord) -> CVEAlertHistoryRecord:
        """Create new alert history record."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            record.created_at = now
            record.updated_at = now

            self._store[record.id] = record.to_dict()
            self.logger.info(f"Created alert history record: {record.id}")
            return record
        except Exception as e:
            self.logger.error(f"Failed to create alert history record: {e}")
            raise

    async def get_record(self, record_id: str) -> Optional[CVEAlertHistoryRecord]:
        """Fetch alert history record by ID"""
        try:
            doc = self._store.get(record_id)
            if not doc:
                return None
            return CVEAlertHistoryRecord.from_dict(doc)
        except Exception as e:
            self.logger.error(f"Failed to get alert history record {record_id}: {e}")
            return None

    async def query_history(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[CVEAlertHistoryRecord]:
        """Query alert history with filters."""
        try:
            items = list(self._store.values())

            if filters:
                if "alert_type" in filters:
                    items = [i for i in items if i.get("alert_type") == filters["alert_type"]]
                if "acknowledged" in filters:
                    items = [i for i in items if i.get("acknowledged") == filters["acknowledged"]]
                if "dismissed" in filters:
                    items = [i for i in items if i.get("dismissed") == filters["dismissed"]]
                if "start_date" in filters:
                    items = [i for i in items if (i.get("timestamp") or "") >= filters["start_date"]]
                if "end_date" in filters:
                    items = [i for i in items if (i.get("timestamp") or "") <= filters["end_date"]]
                if "scan_id" in filters:
                    items = [i for i in items if i.get("scan_id") == filters["scan_id"]]

            items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            page = items[offset:offset + limit]
            return [CVEAlertHistoryRecord.from_dict(item) for item in page]
        except Exception as e:
            self.logger.error(f"Failed to query alert history: {e}")
            return []

    async def acknowledge(
        self,
        record_id: str,
        user: str,
        note: Optional[str] = None
    ) -> bool:
        """Mark alert as acknowledged."""
        try:
            record = await self.get_record(record_id)
            if not record:
                self.logger.warning(f"Record {record_id} not found for acknowledgment")
                return False

            record.acknowledged = True
            record.acknowledged_by = user
            record.acknowledged_at = datetime.now(timezone.utc).isoformat()
            record.acknowledged_note = note
            record.updated_at = datetime.now(timezone.utc).isoformat()

            self._store[record_id] = record.to_dict()
            self.logger.info(f"Alert {record_id} acknowledged by {user}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to acknowledge alert {record_id}: {e}")
            return False

    async def dismiss(self, record_id: str, reason: str) -> bool:
        """Dismiss alert with reason."""
        try:
            record = await self.get_record(record_id)
            if not record:
                self.logger.warning(f"Record {record_id} not found for dismissal")
                return False

            record.dismissed = True
            record.dismissed_reason = reason
            record.dismissed_at = datetime.now(timezone.utc).isoformat()
            record.updated_at = datetime.now(timezone.utc).isoformat()

            self._store[record_id] = record.to_dict()
            self.logger.info(f"Alert {record_id} dismissed: {reason}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to dismiss alert {record_id}: {e}")
            return False

    async def mark_escalated(self, record_id: str) -> bool:
        """Mark alert as escalated"""
        try:
            record = await self.get_record(record_id)
            if not record:
                return False

            record.escalated = True
            record.escalated_at = datetime.now(timezone.utc).isoformat()
            record.updated_at = datetime.now(timezone.utc).isoformat()

            self._store[record_id] = record.to_dict()
            self.logger.info(f"Alert {record_id} marked as escalated")
            return True
        except Exception as e:
            self.logger.error(f"Failed to mark alert {record_id} as escalated: {e}")
            return False

    async def get_unacknowledged_critical(
        self,
        cutoff_time: str
    ) -> List[CVEAlertHistoryRecord]:
        """Get unacknowledged critical alerts older than cutoff time."""
        try:
            items = [
                v for v in self._store.values()
                if v.get("alert_type") == "critical"
                and v.get("acknowledged") is False
                and v.get("dismissed") is False
                and v.get("escalated") is False
                and (v.get("timestamp") or "") < cutoff_time
            ]
            items.sort(key=lambda x: x.get("timestamp", ""))
            return [CVEAlertHistoryRecord.from_dict(item) for item in items]
        except Exception as e:
            self.logger.error(f"Failed to get unacknowledged critical alerts: {e}")
            return []


# Singleton factory
_alert_history_manager: Optional[CVEAlertHistoryManager] = None


def get_cve_alert_history_manager() -> CVEAlertHistoryManager:
    """Singleton factory for alert history manager"""
    global _alert_history_manager
    if _alert_history_manager is None:
        _alert_history_manager = CVEAlertHistoryManager()
    return _alert_history_manager
