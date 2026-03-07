"""
CVE Alert Data Models

Data models for CVE monitoring, alerting, and notification tracking.
Used by CVE monitoring scheduler and alert dispatcher.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


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
