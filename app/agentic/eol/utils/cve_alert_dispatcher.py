"""
CVE Alert Dispatcher

Multi-channel alert delivery for new CVE detections.
Integrates with AlertManager for email and Teams notifications.
"""

from typing import Dict, List, Any
from datetime import datetime, timezone

try:
    from models.cve_alert_models import CVEDelta, CVEAlertItem, CVEAlertHistoryRecord
    from utils.alert_manager import alert_manager, AlertConfiguration, NotificationRecord
    from utils.repositories.alert_repository import AlertRepository
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_alert_models import CVEDelta, CVEAlertItem, CVEAlertHistoryRecord
    from app.agentic.eol.utils.alert_manager import alert_manager, AlertConfiguration, NotificationRecord
    from app.agentic.eol.utils.repositories.alert_repository import AlertRepository
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)


class CVEAlertDispatcher:
    """Dispatches CVE alerts via email and Teams channels."""

    # Severity order for filtering
    SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}

    def __init__(self, alert_repo: AlertRepository | None = None) -> None:
        self.alert_repo = alert_repo

    async def send_cve_alerts(
        self,
        delta: CVEDelta,
        severity_threshold: str = "HIGH"
    ) -> Dict[str, Any]:
        """
        Send alerts for new CVEs via email and Teams.

        Workflow:
        1. Filter new CVEs by severity threshold
        2. Group CVEs by severity level
        3. Format alert content for each channel
        4. Send via AlertManager (email + Teams)
        5. Create notification records for tracking
        6. Return delivery summary

        Args:
            delta: CVEDelta from detect_new_cves()
            severity_threshold: Minimum severity to alert (HIGH or CRITICAL)

        Returns:
            {
                "alerts_sent": 2,
                "email_success": True,
                "teams_success": True,
                "cves_alerted": ["CVE-2024-1234", ...],
                "notification_records": [...]
            }
        """
        try:
            # Filter by severity threshold
            threshold_level = self.SEVERITY_ORDER.get(severity_threshold, 3)
            alertable_cves = [
                cve for cve in delta.new_cves
                if self.SEVERITY_ORDER.get(cve.severity, 0) >= threshold_level
            ]

            if not alertable_cves:
                logger.info("No CVEs meet severity threshold for alerting")
                return {
                    "alerts_sent": 0,
                    "email_success": False,
                    "teams_success": False,
                    "cves_alerted": [],
                    "notification_records": []
                }

            logger.info(f"Sending alerts for {len(alertable_cves)} CVEs (threshold: {severity_threshold})")

            # Group by severity
            cves_by_severity = self._group_by_severity(alertable_cves)

            # Load alert configuration
            alert_config = await alert_manager.load_configuration()

            # Send alerts for each severity level
            results = {
                "alerts_sent": 0,
                "email_success": True,
                "teams_success": True,
                "cves_alerted": [],
                "notification_records": [],
                "history_records": []
            }

            # Get alert repository
            alert_repo = self.alert_repo

            for severity, cves in cves_by_severity.items():
                if not cves:
                    continue

                # Determine alert level
                alert_level = "critical" if severity == "CRITICAL" else "warning"

                # Send combined alert (email + Teams)
                try:
                    # Build alert items (reusing AlertManager's data structure)
                    alert_items = self._build_alert_items(cves, severity)

                    # Send via AlertManager
                    send_result = await alert_manager.send_combined_alert(
                        alert_items=alert_items,
                        alert_level=alert_level,
                        config=alert_config,
                        send_email=True,
                        send_teams=True
                    )

                    # Track results
                    email_sent = send_result.get("email", {}).get("sent", False)
                    teams_sent = send_result.get("teams", {}).get("sent", False)

                    if email_sent:
                        results["alerts_sent"] += 1
                    else:
                        results["email_success"] = False

                    if not teams_sent:
                        results["teams_success"] = False

                    # Add CVE IDs to alerted list
                    results["cves_alerted"].extend([cve.cve_id for cve in cves])

                    # Create history record
                    channels_sent = []
                    if email_sent:
                        channels_sent.append("email")
                    if teams_sent:
                        channels_sent.append("teams")

                    delivery_status = "success" if (email_sent or teams_sent) else "failed"
                    if email_sent and not teams_sent:
                        delivery_status = "partial"
                    elif teams_sent and not email_sent:
                        delivery_status = "partial"

                    # Aggregate affected VMs
                    all_vms = set()
                    all_vm_names = set()
                    for cve in cves:
                        all_vms.update(cve.affected_vms)
                        all_vm_names.update(cve.affected_vm_names)

                    history_record = CVEAlertHistoryRecord(
                        alert_rule_id=None,  # No rule for automatic alerts
                        alert_type=severity.lower(),
                        cve_ids=[cve.cve_id for cve in cves],
                        cve_count=len(cves),
                        affected_vm_count=len(all_vms),
                        affected_vms=list(all_vms),
                        affected_vm_names=list(all_vm_names),
                        severity_breakdown={severity: len(cves)},
                        recipients=alert_config.email_recipients if hasattr(alert_config, 'email_recipients') else [],
                        channels_sent=channels_sent,
                        status=delivery_status,
                        error_message=send_result.get("error") if delivery_status == "failed" else None,
                        scan_id=delta.current_scan_id,
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )

                    # Persist history record
                    created_record = await alert_repo.create_record(history_record.to_dict())
                    results["history_records"].append(created_record)

                    # Create notification record (existing functionality)
                    notification = await self._create_notification_record(
                        cves=cves,
                        severity=severity,
                        scan_id=delta.current_scan_id,
                        delivery_status=send_result
                    )
                    results["notification_records"].append(notification)

                    logger.info(f"Alert sent for {len(cves)} {severity} CVEs (history ID: {created_record.get('id', 'unknown')})")

                except Exception as e:
                    logger.error(f"Failed to send {severity} CVE alerts: {e}", exc_info=True)
                    results["email_success"] = False
                    results["teams_success"] = False

            return results

        except Exception as e:
            logger.error(f"CVE alert dispatch failed: {e}", exc_info=True)
            return {
                "alerts_sent": 0,
                "email_success": False,
                "teams_success": False,
                "cves_alerted": [],
                "notification_records": [],
                "history_records": [],
                "error": str(e)
            }

    def _group_by_severity(self, cves: List[CVEAlertItem]) -> Dict[str, List[CVEAlertItem]]:
        """Group CVEs by severity level."""
        groups = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}

        for cve in cves:
            if cve.severity in groups:
                groups[cve.severity].append(cve)

        return groups

    def _build_alert_items(self, cves: List[CVEAlertItem], severity: str) -> List[Dict[str, Any]]:
        """
        Build alert items in format expected by AlertManager.

        Note: AlertManager expects AlertPreviewItem objects with fields:
        computer, os_name, version, eol_date, days_until_eol, alert_level

        For CVE alerts, we adapt our CVEAlertItem data to this structure.
        """
        alert_items = []

        for cve in cves:
            # Build HTML representation for email
            vm_list_html = "<br>".join([
                f"• {vm_name}" for vm_name in cve.affected_vm_names[:10]  # Limit to 10 VMs
            ])

            if len(cve.affected_vm_names) > 10:
                vm_list_html += f"<br>... and {len(cve.affected_vm_names) - 10} more"

            patch_status = "✅ Patch Available" if cve.patch_available else "⚠️ No Patch Available"

            # Create a pseudo-AlertPreviewItem structure
            # We'll use custom fields that AlertManager's template can handle
            item = {
                "computer": cve.cve_id,
                "os_name": f"CVSS {cve.cvss_score} | {patch_status}",
                "version": f"Affects {len(cve.affected_vms)} VM(s)",
                "eol_date": cve.published_date or "Unknown",
                "days_until_eol": len(cve.affected_vms),  # Reuse for VM count
                "alert_level": severity.lower(),
                "description": cve.description or "No description available",
                "affected_vms": vm_list_html,
                "patch_kb_ids": ", ".join(cve.patch_kb_ids) if cve.patch_kb_ids else "None"
            }

            alert_items.append(item)

        return alert_items

    def _build_email_html(self, cves: List[CVEAlertItem], severity: str) -> str:
        """Generate HTML email body with CVE table."""
        rows = []
        for cve in cves:
            vm_count = len(cve.affected_vms)
            patch_status = "✅" if cve.patch_available else "❌"

            rows.append(f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{cve.cve_id}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{cve.cvss_score}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{vm_count}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{patch_status}</td>
                </tr>
            """)

        html = f"""
        <html>
        <body>
            <h2 style="color: {'#dc2626' if severity == 'CRITICAL' else '#ea580c'};">
                🚨 CVE Security Alert - {len(cves)} New {severity} Vulnerabilities
            </h2>
            <p>New CVEs have been detected in your environment:</p>
            <table style="border-collapse: collapse; width: 100%; margin-top: 20px;">
                <thead>
                    <tr style="background-color: #f3f4f6;">
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">CVE ID</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">CVSS Score</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Affected VMs</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Patch</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
            <p style="margin-top: 20px;">
                <strong>Recommended Actions:</strong>
                <ul>
                    <li>Review affected systems in the CVE dashboard</li>
                    <li>Prioritize patching critical vulnerabilities</li>
                    <li>Verify patch availability and compatibility</li>
                </ul>
            </p>
        </body>
        </html>
        """

        return html

    def _build_teams_card(self, cves: List[CVEAlertItem], severity: str) -> Dict:
        """Generate Teams Adaptive Card JSON."""
        color = "Attention" if severity == "CRITICAL" else "Warning"

        facts = [
            {"title": "Severity", "value": severity},
            {"title": "New CVEs", "value": str(len(cves))},
            {"title": "Affected VMs", "value": str(sum(len(cve.affected_vms) for cve in cves))}
        ]

        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "🚨 CVE Security Alert",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": color
                },
                {
                    "type": "FactSet",
                    "facts": facts
                },
                {
                    "type": "TextBlock",
                    "text": "New CVEs detected:",
                    "weight": "Bolder",
                    "spacing": "Medium"
                }
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "View Dashboard",
                    "url": f"{config.app.base_url}/cve-dashboard"
                }
            ]
        }

        # Add CVE details (limit to 5 for card size)
        for cve in cves[:5]:
            card["body"].append({
                "type": "TextBlock",
                "text": f"**{cve.cve_id}** (CVSS {cve.cvss_score}) - {len(cve.affected_vms)} VMs affected",
                "wrap": True
            })

        if len(cves) > 5:
            card["body"].append({
                "type": "TextBlock",
                "text": f"... and {len(cves) - 5} more CVEs",
                "isSubtle": True
            })

        return card

    async def _create_notification_record(
        self,
        cves: List[CVEAlertItem],
        severity: str,
        scan_id: str,
        delivery_status: Dict
    ) -> NotificationRecord:
        """Create tracking record for alert history."""
        now = datetime.now(timezone.utc).isoformat()

        record = NotificationRecord(
            id=f"cve-alert-{scan_id}-{severity.lower()}-{int(datetime.now(timezone.utc).timestamp())}",
            timestamp=now,
            alert_type=severity.lower(),
            recipients=[],  # TODO: Get from config
            recipient_count=0,
            items_count=len(cves),
            status="success" if delivery_status.get("email", {}).get("sent") else "failed",
            error_message=None,
            email_subject=f"CVE Alert: {len(cves)} New {severity} Vulnerabilities",
            frequency="on-detection",
            created_at=now,
            updated_at=now
        )

        # Save to Cosmos via AlertManager
        try:
            await alert_manager.save_notification_record(record)
            logger.info(f"Notification record saved: {record.id}")
        except Exception as e:
            logger.warning(f"Failed to save notification record: {e}")

        return record


_cve_alert_dispatcher: CVEAlertDispatcher | None = None


def get_cve_alert_dispatcher(alert_repo: AlertRepository | None = None) -> CVEAlertDispatcher:
    """Return a shared CVE alert dispatcher instance."""

    global _cve_alert_dispatcher
    if _cve_alert_dispatcher is None:
        _cve_alert_dispatcher = CVEAlertDispatcher(alert_repo=alert_repo)
    elif alert_repo is not None and _cve_alert_dispatcher.alert_repo is None:
        _cve_alert_dispatcher.alert_repo = alert_repo
    return _cve_alert_dispatcher
