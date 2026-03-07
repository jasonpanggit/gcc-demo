"""
CVE Alert History Manager

Manages CVE alert history with Cosmos DB persistence.
Provides CRUD operations for alert history records including
acknowledge, dismiss, and escalation tracking.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from models.cve_alert_models import CVEAlertHistoryRecord
from utils.cosmos_cache.base_cosmos import get_cosmos_client
from utils.logger import get_logger
from utils.config import config


class CVEAlertHistoryManager:
    """
    Manages CVE alert history with Cosmos DB persistence.

    Container: cve_alert_history
    Partition Key: /alert_type
    """

    def __init__(self):
        self.cosmos_client = get_cosmos_client()
        self.container = self.cosmos_client.get_container_client(
            database="eol_db",
            container="cve_alert_history"
        )
        self.logger = get_logger(__name__, config.app.log_level)

    async def create_record(self, record: CVEAlertHistoryRecord) -> CVEAlertHistoryRecord:
        """
        Create new alert history record in Cosmos DB.

        Args:
            record: CVEAlertHistoryRecord to persist

        Returns:
            Created record with ID
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            record.created_at = now
            record.updated_at = now

            await self.container.create_item(body=record.to_dict())
            self.logger.info(f"Created alert history record: {record.id}")
            return record
        except Exception as e:
            self.logger.error(f"Failed to create alert history record: {e}")
            raise

    async def get_record(self, record_id: str) -> Optional[CVEAlertHistoryRecord]:
        """Fetch alert history record by ID"""
        try:
            query = "SELECT * FROM c WHERE c.id = @record_id"
            params = [{"name": "@record_id", "value": record_id}]

            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))

            if not items:
                return None

            return CVEAlertHistoryRecord.from_dict(items[0])
        except Exception as e:
            self.logger.error(f"Failed to get alert history record {record_id}: {e}")
            return None

    async def query_history(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[CVEAlertHistoryRecord]:
        """
        Query alert history with filters.

        Filters:
            alert_type: Filter by severity (critical, high, etc.)
            acknowledged: Filter by acknowledgment status (true/false)
            dismissed: Filter by dismiss status (true/false)
            start_date: Filter by timestamp >= start_date
            end_date: Filter by timestamp <= end_date
            scan_id: Filter by specific scan

        Returns:
            List of alert history records sorted by timestamp DESC
        """
        try:
            # Build query
            query_parts = ["SELECT * FROM c WHERE 1=1"]
            params = []

            if filters:
                if "alert_type" in filters:
                    query_parts.append("AND c.alert_type = @alert_type")
                    params.append({"name": "@alert_type", "value": filters["alert_type"]})

                if "acknowledged" in filters:
                    query_parts.append("AND c.acknowledged = @acknowledged")
                    params.append({"name": "@acknowledged", "value": filters["acknowledged"]})

                if "dismissed" in filters:
                    query_parts.append("AND c.dismissed = @dismissed")
                    params.append({"name": "@dismissed", "value": filters["dismissed"]})

                if "start_date" in filters:
                    query_parts.append("AND c.timestamp >= @start_date")
                    params.append({"name": "@start_date", "value": filters["start_date"]})

                if "end_date" in filters:
                    query_parts.append("AND c.timestamp <= @end_date")
                    params.append({"name": "@end_date", "value": filters["end_date"]})

                if "scan_id" in filters:
                    query_parts.append("AND c.scan_id = @scan_id")
                    params.append({"name": "@scan_id", "value": filters["scan_id"]})

            query_parts.append(f"ORDER BY c.timestamp DESC OFFSET {offset} LIMIT {limit}")
            query = " ".join(query_parts)

            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))

            return [CVEAlertHistoryRecord.from_dict(item) for item in items]
        except Exception as e:
            self.logger.error(f"Failed to query alert history: {e}")
            return []

    async def acknowledge(
        self,
        record_id: str,
        user: str,
        note: Optional[str] = None
    ) -> bool:
        """
        Mark alert as acknowledged.

        Args:
            record_id: Alert history record ID
            user: User acknowledging the alert
            note: Optional acknowledgment note

        Returns:
            True if successful
        """
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

            await self.container.replace_item(
                item=record_id,
                body=record.to_dict()
            )

            self.logger.info(f"Alert {record_id} acknowledged by {user}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to acknowledge alert {record_id}: {e}")
            return False

    async def dismiss(self, record_id: str, reason: str) -> bool:
        """
        Dismiss alert with reason.

        Args:
            record_id: Alert history record ID
            reason: Reason for dismissal

        Returns:
            True if successful
        """
        try:
            record = await self.get_record(record_id)
            if not record:
                self.logger.warning(f"Record {record_id} not found for dismissal")
                return False

            record.dismissed = True
            record.dismissed_reason = reason
            record.dismissed_at = datetime.now(timezone.utc).isoformat()
            record.updated_at = datetime.now(timezone.utc).isoformat()

            await self.container.replace_item(
                item=record_id,
                body=record.to_dict()
            )

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

            await self.container.replace_item(
                item=record_id,
                body=record.to_dict()
            )

            self.logger.info(f"Alert {record_id} marked as escalated")
            return True
        except Exception as e:
            self.logger.error(f"Failed to mark alert {record_id} as escalated: {e}")
            return False

    async def get_unacknowledged_critical(
        self,
        cutoff_time: str
    ) -> List[CVEAlertHistoryRecord]:
        """
        Get unacknowledged critical alerts older than cutoff time.
        Used for escalation logic.

        Args:
            cutoff_time: ISO timestamp (alerts before this are eligible)

        Returns:
            List of critical alerts requiring escalation
        """
        try:
            query = """
                SELECT * FROM c
                WHERE c.alert_type = 'critical'
                AND c.acknowledged = false
                AND c.dismissed = false
                AND c.escalated = false
                AND c.timestamp < @cutoff_time
                ORDER BY c.timestamp ASC
            """
            params = [{"name": "@cutoff_time", "value": cutoff_time}]

            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=False  # Single partition (critical)
            ))

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
