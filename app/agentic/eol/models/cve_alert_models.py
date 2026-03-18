"""
CVE Alert Data Models

Data models for CVE monitoring, alerting, and notification tracking.
Used by CVE monitoring scheduler and alert dispatcher.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


@dataclass
class CVEAlertItem:
    """Single CVE in an alert"""
    cve_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    cvss_score: float
    affected_vms: List[str]  # VM resource IDs
    affected_vm_names: List[str]  # VM display names
    published_date: str
    patch_available: bool
    patch_kb_ids: List[str] = field(default_factory=list)
    description: Optional[str] = None

    def __post_init__(self):
        """Validate severity values"""
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        if self.severity not in valid_severities:
            raise ValueError(f"Invalid severity: {self.severity}. Must be one of {valid_severities}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "cve_id": self.cve_id,
            "severity": self.severity,
            "cvss_score": self.cvss_score,
            "affected_vms": self.affected_vms,
            "affected_vm_names": self.affected_vm_names,
            "published_date": self.published_date,
            "patch_available": self.patch_available,
            "patch_kb_ids": self.patch_kb_ids,
            "description": self.description
        }


@dataclass
class CVEDelta:
    """Results of baseline comparison"""
    new_cves: List[CVEAlertItem]
    resolved_cves: List[str]  # CVE IDs no longer detected
    severity_changes: List[Dict[str, Any]]  # CVEs with increased severity
    is_first_scan: bool = False
    baseline_scan_id: Optional[str] = None
    current_scan_id: str = ""
    baseline_timestamp: Optional[str] = None
    current_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "new_cves": [cve.to_dict() for cve in self.new_cves],
            "resolved_cves": self.resolved_cves,
            "severity_changes": self.severity_changes,
            "is_first_scan": self.is_first_scan,
            "baseline_scan_id": self.baseline_scan_id,
            "current_scan_id": self.current_scan_id,
            "baseline_timestamp": self.baseline_timestamp,
            "current_timestamp": self.current_timestamp
        }


@dataclass
class CVEMonitoringStats:
    """Tracking stats for monitoring scheduler"""
    last_scan_time: Optional[str] = None
    next_scan_time: Optional[str] = None
    last_scan_duration_seconds: Optional[float] = None
    total_scans: int = 0
    total_alerts_sent: int = 0
    total_errors: int = 0
    last_error: Optional[str] = None
    last_delta_summary: Optional[Dict[str, int]] = None  # {new: X, resolved: Y}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "last_scan_time": self.last_scan_time,
            "next_scan_time": self.next_scan_time,
            "last_scan_duration_seconds": self.last_scan_duration_seconds,
            "total_scans": self.total_scans,
            "total_alerts_sent": self.total_alerts_sent,
            "total_errors": self.total_errors,
            "last_error": self.last_error,
            "last_delta_summary": self.last_delta_summary
        }


@dataclass
class CVEAlertRule:
    """CVE alert rule configuration"""
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    enabled: bool = True
    rule_type: str = "delta"  # Partition key: delta, threshold, scheduled

    # Severity filters
    severity_levels: List[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    min_cvss_score: Optional[float] = None
    max_cvss_score: Optional[float] = None

    # VM filters
    vm_resource_groups: List[str] = field(default_factory=list)  # Empty = all RGs
    vm_tags: Dict[str, str] = field(default_factory=dict)  # Tag key-value filters
    vm_name_pattern: Optional[str] = None  # Regex pattern for VM names

    # Notification channels
    email_recipients: List[str] = field(default_factory=list)
    teams_enabled: bool = True
    teams_webhook_url: Optional[str] = None  # Override default webhook

    # Frequency and schedule
    scan_schedule_cron: Optional[str] = None  # Override default: "0 9 * * *"
    alert_frequency: str = "immediate"  # immediate, daily, weekly, monthly
    last_triggered: Optional[str] = None

    # Escalation
    enable_escalation: bool = False
    escalation_timeout_hours: int = 24
    escalation_recipients: List[str] = field(default_factory=list)

    # Metadata
    created_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "rule_type": self.rule_type,
            "severity_levels": self.severity_levels,
            "min_cvss_score": self.min_cvss_score,
            "max_cvss_score": self.max_cvss_score,
            "vm_resource_groups": self.vm_resource_groups,
            "vm_tags": self.vm_tags,
            "vm_name_pattern": self.vm_name_pattern,
            "email_recipients": self.email_recipients,
            "teams_enabled": self.teams_enabled,
            "teams_webhook_url": self.teams_webhook_url,
            "scan_schedule_cron": self.scan_schedule_cron,
            "alert_frequency": self.alert_frequency,
            "last_triggered": self.last_triggered,
            "enable_escalation": self.enable_escalation,
            "escalation_timeout_hours": self.escalation_timeout_hours,
            "escalation_recipients": self.escalation_recipients,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CVEAlertRule":
        """Create from database document"""
        return cls(**data)

    def __post_init__(self):
        """Validate rule configuration"""
        valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        invalid = set(self.severity_levels) - valid_severities
        if invalid:
            raise ValueError(f"Invalid severity levels: {invalid}")

        if self.min_cvss_score and (self.min_cvss_score < 0 or self.min_cvss_score > 10):
            raise ValueError("CVSS score must be between 0 and 10")

        if self.max_cvss_score and (self.max_cvss_score < 0 or self.max_cvss_score > 10):
            raise ValueError("CVSS score must be between 0 and 10")

        if self.min_cvss_score and self.max_cvss_score and self.min_cvss_score > self.max_cvss_score:
            raise ValueError("min_cvss_score must be <= max_cvss_score")


@dataclass
class CVEAlertHistoryRecord:
    """Historical record of CVE alert sent"""
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alert_rule_id: Optional[str] = None  # Reference to rule that triggered alert
    alert_type: str = "high"  # Partition key: "critical", "high", "medium", "low"

    # Alert content
    cve_ids: List[str] = field(default_factory=list)
    cve_count: int = 0
    affected_vm_count: int = 0
    affected_vms: List[str] = field(default_factory=list)  # VM resource IDs
    affected_vm_names: List[str] = field(default_factory=list)  # VM display names

    # Severity breakdown
    severity_breakdown: Dict[str, int] = field(default_factory=dict)  # {CRITICAL: 5, HIGH: 10}

    # Delivery
    recipients: List[str] = field(default_factory=list)
    channels_sent: List[str] = field(default_factory=list)  # ["email", "teams"]
    status: str = "success"  # success, failed, partial
    error_message: Optional[str] = None

    # Lifecycle
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None
    acknowledged_note: Optional[str] = None
    dismissed: bool = False
    dismissed_reason: Optional[str] = None
    dismissed_at: Optional[str] = None
    escalated: bool = False
    escalated_at: Optional[str] = None

    # Metadata
    scan_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "id": self.id,
            "alert_rule_id": self.alert_rule_id,
            "alert_type": self.alert_type,
            "cve_ids": self.cve_ids,
            "cve_count": self.cve_count,
            "affected_vm_count": self.affected_vm_count,
            "affected_vms": self.affected_vms,
            "affected_vm_names": self.affected_vm_names,
            "severity_breakdown": self.severity_breakdown,
            "recipients": self.recipients,
            "channels_sent": self.channels_sent,
            "status": self.status,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at,
            "acknowledged_note": self.acknowledged_note,
            "dismissed": self.dismissed,
            "dismissed_reason": self.dismissed_reason,
            "dismissed_at": self.dismissed_at,
            "escalated": self.escalated,
            "escalated_at": self.escalated_at,
            "scan_id": self.scan_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CVEAlertHistoryRecord":
        """Create from database document"""
        return cls(**data)
