"""Alert Repository -- CVE Alert Rules and Alert History.

Phase 8: Replaces Cosmos-backed ``cve_alert_rule_manager.py`` and
``cve_alert_history_manager.py`` with asyncpg PostgreSQL queries.

Tables: ``cve_alert_rules``, ``cve_alert_history``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

# Alert rules
INSERT_RULE = """
INSERT INTO cve_alert_rules (
    id, name, description, enabled, rule_type,
    severity_levels, min_cvss_score, max_cvss_score,
    vm_resource_groups, vm_tags, vm_name_pattern,
    email_recipients, teams_enabled, teams_webhook_url,
    scan_schedule_cron, alert_frequency, last_triggered,
    enable_escalation, escalation_timeout_hours, escalation_recipients,
    created_by, created_at, updated_at
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8,
    $9, $10, $11,
    $12, $13, $14,
    $15, $16, $17,
    $18, $19, $20,
    $21, $22, $23
)
RETURNING *;
"""

SELECT_RULE_BY_ID = """
SELECT * FROM cve_alert_rules WHERE id = $1;
"""

SELECT_RULE_BY_NAME = """
SELECT * FROM cve_alert_rules WHERE name = $1;
"""

SELECT_RULES_ALL = """
SELECT * FROM cve_alert_rules ORDER BY created_at DESC;
"""

SELECT_RULES_ENABLED = """
SELECT * FROM cve_alert_rules WHERE enabled = true ORDER BY created_at DESC;
"""

UPDATE_RULE = """
UPDATE cve_alert_rules
SET name = $2, description = $3, enabled = $4, rule_type = $5,
    severity_levels = $6, min_cvss_score = $7, max_cvss_score = $8,
    vm_resource_groups = $9, vm_tags = $10, vm_name_pattern = $11,
    email_recipients = $12, teams_enabled = $13, teams_webhook_url = $14,
    scan_schedule_cron = $15, alert_frequency = $16, last_triggered = $17,
    enable_escalation = $18, escalation_timeout_hours = $19, escalation_recipients = $20,
    updated_at = $21
WHERE id = $1
RETURNING *;
"""

DELETE_RULE = """
DELETE FROM cve_alert_rules WHERE id = $1;
"""

# Alert history
INSERT_HISTORY = """
INSERT INTO cve_alert_history (
    id, alert_rule_id, alert_type,
    cve_ids, cve_count, affected_vm_count,
    affected_vms, affected_vm_names,
    severity_breakdown,
    recipients, channels_sent, status, error_message,
    timestamp, scan_id, created_at, updated_at
) VALUES (
    $1, $2, $3,
    $4, $5, $6,
    $7, $8,
    $9,
    $10, $11, $12, $13,
    $14, $15, $16, $17
)
RETURNING *;
"""

SELECT_HISTORY_BY_ID = """
SELECT * FROM cve_alert_history WHERE id = $1;
"""

UPDATE_HISTORY_ACKNOWLEDGE = """
UPDATE cve_alert_history
SET acknowledged = true,
    acknowledged_by = $2,
    acknowledged_at = $3,
    acknowledged_note = $4,
    updated_at = $5
WHERE id = $1
RETURNING *;
"""

UPDATE_HISTORY_DISMISS = """
UPDATE cve_alert_history
SET dismissed = true,
    dismissed_reason = $2,
    dismissed_at = $3,
    updated_at = $4
WHERE id = $1
RETURNING *;
"""

UPDATE_HISTORY_ESCALATED = """
UPDATE cve_alert_history
SET escalated = true,
    escalated_at = $2,
    updated_at = $3
WHERE id = $1
RETURNING *;
"""

SELECT_UNACKNOWLEDGED_CRITICAL = """
SELECT * FROM cve_alert_history
WHERE alert_type = 'critical'
  AND acknowledged = false
  AND dismissed = false
  AND escalated = false
  AND timestamp < $1
ORDER BY timestamp ASC;
"""


class AlertRepository:
    """PostgreSQL repository for CVE alert rules and history."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Rule CRUD
    # ------------------------------------------------------------------

    async def create_rule(self, rule_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new alert rule. Returns the created row as dict."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            INSERT_RULE,
            rule_dict["id"],
            rule_dict.get("name", ""),
            rule_dict.get("description", ""),
            rule_dict.get("enabled", True),
            rule_dict.get("rule_type", "delta"),
            json.dumps(rule_dict.get("severity_levels", ["CRITICAL", "HIGH"])),
            rule_dict.get("min_cvss_score"),
            rule_dict.get("max_cvss_score"),
            json.dumps(rule_dict.get("vm_resource_groups", [])),
            json.dumps(rule_dict.get("vm_tags", {})),
            rule_dict.get("vm_name_pattern"),
            json.dumps(rule_dict.get("email_recipients", [])),
            rule_dict.get("teams_enabled", True),
            rule_dict.get("teams_webhook_url"),
            rule_dict.get("scan_schedule_cron"),
            rule_dict.get("alert_frequency", "immediate"),
            rule_dict.get("last_triggered"),
            rule_dict.get("enable_escalation", False),
            rule_dict.get("escalation_timeout_hours", 24),
            json.dumps(rule_dict.get("escalation_recipients", [])),
            rule_dict.get("created_by"),
            now,
            now,
        )
        return dict(row) if row else {}

    async def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Fetch rule by ID."""
        row = await self.pool.fetchrow(SELECT_RULE_BY_ID, rule_id)
        return dict(row) if row else None

    async def get_rule_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch rule by name (duplicate check)."""
        row = await self.pool.fetchrow(SELECT_RULE_BY_NAME, name)
        return dict(row) if row else None

    async def list_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all rules, optionally only enabled."""
        query = SELECT_RULES_ENABLED if enabled_only else SELECT_RULES_ALL
        rows = await self.pool.fetch(query)
        return [dict(r) for r in rows]

    async def update_rule(self, rule_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing rule. Returns updated row."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            UPDATE_RULE,
            rule_dict["id"],
            rule_dict.get("name", ""),
            rule_dict.get("description", ""),
            rule_dict.get("enabled", True),
            rule_dict.get("rule_type", "delta"),
            json.dumps(rule_dict.get("severity_levels", ["CRITICAL", "HIGH"])),
            rule_dict.get("min_cvss_score"),
            rule_dict.get("max_cvss_score"),
            json.dumps(rule_dict.get("vm_resource_groups", [])),
            json.dumps(rule_dict.get("vm_tags", {})),
            rule_dict.get("vm_name_pattern"),
            json.dumps(rule_dict.get("email_recipients", [])),
            rule_dict.get("teams_enabled", True),
            rule_dict.get("teams_webhook_url"),
            rule_dict.get("scan_schedule_cron"),
            rule_dict.get("alert_frequency", "immediate"),
            rule_dict.get("last_triggered"),
            rule_dict.get("enable_escalation", False),
            rule_dict.get("escalation_timeout_hours", 24),
            json.dumps(rule_dict.get("escalation_recipients", [])),
            now,
        )
        return dict(row) if row else None

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID. Returns True if a row was deleted."""
        result = await self.pool.execute(DELETE_RULE, rule_id)
        return result == "DELETE 1"

    # ------------------------------------------------------------------
    # History CRUD
    # ------------------------------------------------------------------

    async def create_record(self, record_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Create alert history record. Returns created row as dict."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            INSERT_HISTORY,
            record_dict["id"],
            record_dict.get("alert_rule_id"),
            record_dict.get("alert_type", "high"),
            json.dumps(record_dict.get("cve_ids", [])),
            record_dict.get("cve_count", 0),
            record_dict.get("affected_vm_count", 0),
            json.dumps(record_dict.get("affected_vms", [])),
            json.dumps(record_dict.get("affected_vm_names", [])),
            json.dumps(record_dict.get("severity_breakdown", {})),
            json.dumps(record_dict.get("recipients", [])),
            json.dumps(record_dict.get("channels_sent", [])),
            record_dict.get("status", "success"),
            record_dict.get("error_message"),
            record_dict.get("timestamp", now),
            record_dict.get("scan_id", ""),
            now,
            now,
        )
        return dict(row) if row else {}

    async def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Fetch history record by ID."""
        row = await self.pool.fetchrow(SELECT_HISTORY_BY_ID, record_id)
        return dict(row) if row else None

    async def query_history(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query alert history with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        idx = 1

        if filters:
            if "alert_type" in filters:
                clauses.append(f"alert_type = ${idx}")
                params.append(filters["alert_type"])
                idx += 1
            if "acknowledged" in filters:
                clauses.append(f"acknowledged = ${idx}")
                params.append(filters["acknowledged"])
                idx += 1
            if "dismissed" in filters:
                clauses.append(f"dismissed = ${idx}")
                params.append(filters["dismissed"])
                idx += 1
            if "start_date" in filters:
                clauses.append(f"timestamp >= ${idx}")
                params.append(filters["start_date"])
                idx += 1
            if "end_date" in filters:
                clauses.append(f"timestamp <= ${idx}")
                params.append(filters["end_date"])
                idx += 1
            if "scan_id" in filters:
                clauses.append(f"scan_id = ${idx}")
                params.append(filters["scan_id"])
                idx += 1

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM cve_alert_history {where} ORDER BY timestamp DESC LIMIT ${idx} OFFSET ${idx + 1};"
        params.extend([limit, offset])

        rows = await self.pool.fetch(query, *params)
        return [dict(r) for r in rows]

    async def acknowledge(
        self, record_id: str, user: str, note: Optional[str] = None
    ) -> bool:
        """Mark a history record as acknowledged."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            UPDATE_HISTORY_ACKNOWLEDGE, record_id, user, now, note, now
        )
        return row is not None

    async def dismiss(self, record_id: str, reason: str) -> bool:
        """Dismiss a history record with a reason."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            UPDATE_HISTORY_DISMISS, record_id, reason, now, now
        )
        return row is not None

    async def mark_escalated(self, record_id: str) -> bool:
        """Mark a history record as escalated."""
        now = datetime.now(timezone.utc).isoformat()
        row = await self.pool.fetchrow(
            UPDATE_HISTORY_ESCALATED, record_id, now, now
        )
        return row is not None

    async def get_unacknowledged_critical(
        self, cutoff_time: str
    ) -> List[Dict[str, Any]]:
        """Get unacknowledged critical alerts older than cutoff for escalation."""
        rows = await self.pool.fetch(SELECT_UNACKNOWLEDGED_CRITICAL, cutoff_time)
        return [dict(r) for r in rows]
