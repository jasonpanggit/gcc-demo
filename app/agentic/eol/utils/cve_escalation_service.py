"""
CVE Escalation Service

Handles escalation of unacknowledged critical CVE alerts after timeout.
Sends escalation notifications to designated recipients.
"""

from typing import Dict, Any
from datetime import datetime, timezone, timedelta

try:
    from models.cve_alert_models import CVEAlertHistoryRecord, CVEAlertRule
    from utils.repositories.alert_repository import AlertRepository
    from utils.alert_manager import alert_manager
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_alert_models import CVEAlertHistoryRecord, CVEAlertRule
    from app.agentic.eol.utils.repositories.alert_repository import AlertRepository
    from app.agentic.eol.utils.alert_manager import alert_manager
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)


async def check_and_escalate_alerts(alert_repo: AlertRepository | None = None) -> Dict[str, Any]:
    """
    Check for unacknowledged critical CVE alerts requiring escalation.

    Workflow:
    1. Calculate cutoff time (now - escalation_timeout_hours)
    2. Query unacknowledged critical alerts older than cutoff
    3. For each alert, send escalation notification
    4. Mark alert as escalated

    Args:
        alert_repo: AlertRepository instance for DB access.

    Returns:
        Summary of escalations sent
    """
    logger.info("Checking for CVE alerts requiring escalation")

    if alert_repo is None:
        logger.warning("alert_repo not provided for escalation check -- skipping")
        return {"escalations_sent": 0, "alerts_checked": 0}

    # Calculate cutoff time (default 24 hours)
    timeout_hours = getattr(config.cve_monitoring, 'escalation_timeout_hours', 24)
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=timeout_hours)).isoformat()

    # Query unacknowledged critical alerts
    alerts_to_escalate = await alert_repo.get_unacknowledged_critical(cutoff_time)

    if not alerts_to_escalate:
        logger.info("No alerts requiring escalation")
        return {"escalations_sent": 0, "alerts_checked": 0}

    logger.info(f"Found {len(alerts_to_escalate)} alerts requiring escalation")

    escalation_summary = {
        "escalations_sent": 0,
        "alerts_checked": len(alerts_to_escalate),
        "escalated_alert_ids": []
    }

    for alert in alerts_to_escalate:
        try:
            alert_id = alert.get("id", "")
            alert_timestamp = alert.get("timestamp", "")
            # Calculate time since alert
            alert_time = datetime.fromisoformat(alert_timestamp.replace('Z', '+00:00'))
            hours_elapsed = (datetime.now(timezone.utc) - alert_time).total_seconds() / 3600

            # Build a lightweight CVEAlertHistoryRecord for the notification formatter
            alert_record = CVEAlertHistoryRecord(**{
                k: v for k, v in alert.items()
                if k in CVEAlertHistoryRecord.__dataclass_fields__
            })

            # Send escalation notification
            escalation_result = await send_escalation_notification(
                alert=alert_record,
                hours_elapsed=hours_elapsed
            )

            if escalation_result["success"]:
                # Mark as escalated
                await alert_repo.mark_escalated(alert_id)
                escalation_summary["escalations_sent"] += 1
                escalation_summary["escalated_alert_ids"].append(alert_id)
                logger.info(f"Escalated alert {alert_id} after {hours_elapsed:.1f} hours")
            else:
                logger.error(f"Failed to escalate alert {alert_id}: {escalation_result.get('error')}")

        except Exception as e:
            logger.error(f"Error escalating alert {alert.get('id', '?')}: {e}", exc_info=True)

    logger.info(f"Escalation check complete: {escalation_summary['escalations_sent']} escalations sent")
    return escalation_summary


async def send_escalation_notification(
    alert: CVEAlertHistoryRecord,
    hours_elapsed: float
) -> Dict[str, Any]:
    """
    Send escalation notification for unacknowledged alert.

    Args:
        alert: Alert history record requiring escalation
        hours_elapsed: Hours since original alert

    Returns:
        {success: bool, error: Optional[str]}
    """
    logger.info(f"Sending escalation notification for alert {alert.id}")

    try:
        # Build escalation message
        subject = f"⚠️ ESCALATION: Unacknowledged Critical CVEs - Attention Required"

        email_body = f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px;">
            <h1 style="color: white;">⚠️ CVE Alert Escalation</h1>
            <p style="color: white; font-size: 16px;">
                Critical CVE alert has not been acknowledged for {hours_elapsed:.1f} hours.
            </p>
        </div>

        <div style="margin-top: 20px;">
            <h2>Alert Summary</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 8px;"><strong>Alert ID:</strong></td>
                    <td style="padding: 8px;">{alert.id}</td>
                </tr>
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 8px;"><strong>Original Alert Time:</strong></td>
                    <td style="padding: 8px;">{alert.timestamp}</td>
                </tr>
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 8px;"><strong>Time Elapsed:</strong></td>
                    <td style="padding: 8px;">{hours_elapsed:.1f} hours</td>
                </tr>
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 8px;"><strong>CVE Count:</strong></td>
                    <td style="padding: 8px;">{alert.cve_count}</td>
                </tr>
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 8px;"><strong>Affected VMs:</strong></td>
                    <td style="padding: 8px;">{alert.affected_vm_count}</td>
                </tr>
            </table>
        </div>

        <div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-left: 4px solid #ffc107;">
            <strong>Action Required:</strong> Please review and acknowledge this alert immediately.
            <br><br>
            <a href="{config.app.base_url}/cve-alert-history" style="color: #0066cc;">View Alert History →</a>
        </div>

        <div style="margin-top: 20px;">
            <h3>CVE IDs:</h3>
            <ul>
                {"".join(f"<li>{cve_id}</li>" for cve_id in alert.cve_ids[:10])}
                {f"<li>... and {len(alert.cve_ids) - 10} more</li>" if len(alert.cve_ids) > 10 else ""}
            </ul>
        </div>

        <div style="margin-top: 20px;">
            <h3>Affected VMs (Top 10):</h3>
            <ul>
                {"".join(f"<li>{vm_name}</li>" for vm_name in alert.affected_vm_names[:10])}
                {f"<li>... and {len(alert.affected_vm_names) - 10} more</li>" if len(alert.affected_vm_names) > 10 else ""}
            </ul>
        </div>
        """

        # Send email to original recipients (escalation)
        if alert.recipients:
            try:
                email_result = await alert_manager.send_email(
                    recipients=alert.recipients,
                    subject=subject,
                    body=email_body
                )
                logger.info(f"Escalation email sent to {len(alert.recipients)} recipients")
            except Exception as e:
                logger.error(f"Failed to send escalation email: {e}")

        # Send Teams notification if originally sent via Teams
        if "teams" in alert.channels_sent:
            try:
                teams_card = {
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "⚠️ CVE Alert Escalation",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": "Attention"
                        },
                        {
                            "type": "TextBlock",
                            "text": f"Critical CVE alert unacknowledged for {hours_elapsed:.1f} hours",
                            "wrap": True
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Alert ID", "value": alert.id},
                                {"title": "CVE Count", "value": str(alert.cve_count)},
                                {"title": "Affected VMs", "value": str(alert.affected_vm_count)},
                                {"title": "Time Elapsed", "value": f"{hours_elapsed:.1f} hours"}
                            ]
                        }
                    ],
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "View Alert History",
                            "url": f"{config.app.base_url}/cve-alert-history"
                        }
                    ]
                }

                teams_result = await alert_manager.send_teams_notification(teams_card)
                logger.info("Escalation Teams notification sent")
            except Exception as e:
                logger.error(f"Failed to send escalation Teams notification: {e}")

        return {"success": True}

    except Exception as e:
        logger.error(f"Failed to send escalation notification: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
