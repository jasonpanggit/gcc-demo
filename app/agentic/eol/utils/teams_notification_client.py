"""
Microsoft Teams notification client for Azure SRE operations

NOTE: This client uses the legacy webhook approach. For modern Teams Bot integration,
use the Teams Bot Framework API (see api/teams_bot.py) which supports:
- Bidirectional conversations
- Proactive messaging to specific users/channels
- Adaptive cards and rich formatting

The webhook approach is being phased out and only works for incoming webhooks.
For SRE notifications, consider using:
1. Teams Bot proactive messaging (requires conversation reference)
2. Email alerts (SMTP)
3. Azure Monitor Action Groups
"""
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import pymsteams

from utils.logger import get_logger

logger = get_logger(__name__)


class TeamsNotificationClient:
    """
    Send adaptive cards and messages to Microsoft Teams via incoming webhooks.

    DEPRECATED: Webhook-based notifications are limited. Consider using:
    - Teams Bot Framework (api/teams_bot.py) for bidirectional conversations
    - SMTP email alerts for proactive notifications
    - Azure Monitor Action Groups for production alerting

    This client supports:
    - Sending incident alerts and notifications
    - Creating rich adaptive cards with actions
    - Sending status updates
    - Formatting SRE-specific messages
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        critical_webhook_url: Optional[str] = None
    ):
        """
        Initialize Teams notification client.

        Args:
            webhook_url: Primary Teams webhook URL (defaults to env var)
            critical_webhook_url: Separate webhook for critical alerts (optional)
        """
        self.webhook_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL")
        self.critical_webhook_url = critical_webhook_url or os.getenv("TEAMS_CRITICAL_WEBHOOK_URL")

        # Check if Teams Bot is configured instead
        bot_app_id = os.getenv("TEAMS_BOT_APP_ID")
        bot_app_password = os.getenv("TEAMS_BOT_APP_PASSWORD")

        if not self.webhook_url:
            if bot_app_id and bot_app_password:
                logger.info(
                    "Teams Bot is configured (webhook not set). "
                    "For proactive notifications, use Teams Bot API or configure email alerts. "
                    "See api/teams_bot.py for bidirectional Teams integration."
                )
            else:
                logger.warning("No Teams integration configured - Teams notifications disabled")

    def _create_message_card(self, webhook_url: str) -> pymsteams.connectorcard:
        """Create a new Teams connector card"""
        return pymsteams.connectorcard(webhook_url)

    def send_incident_alert(
        self,
        title: str,
        severity: str,
        description: str,
        resource_id: Optional[str] = None,
        affected_resources: Optional[List[str]] = None,
        incident_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an incident alert to Teams with formatted adaptive card.

        Args:
            title: Incident title
            severity: Severity level (critical, error, warning, info)
            description: Incident description
            resource_id: Primary affected resource ID
            affected_resources: List of affected resource IDs
            incident_url: URL to incident details
            metadata: Additional metadata to include

        Returns:
            Dict with status and message
        """
        if not self.webhook_url:
            return {
                "success": False,
                "error": "Teams webhook not configured",
                "recommendation": (
                    "Webhook-based notifications are not configured. Consider using: "
                    "(1) Teams Bot for bidirectional chat - interact via /api/teams-bot/messages, "
                    "(2) Email alerts via SMTP - configure with /api/alerts endpoints, "
                    "(3) Azure Monitor Action Groups for production alerting"
                )
            }

        try:
            # Use critical webhook for critical/error severity
            use_webhook = (
                self.critical_webhook_url
                if severity.lower() in ["critical", "error"] and self.critical_webhook_url
                else self.webhook_url
            )

            # Create message card
            card = self._create_message_card(use_webhook)

            # Set title and text
            card.title(f"🚨 {title}" if severity.lower() == "critical" else f"⚠️ {title}")
            card.text(description)

            # Set color based on severity
            severity_colors = {
                "critical": "FF0000",  # Red
                "error": "FFA500",     # Orange
                "warning": "FFD700",   # Gold
                "info": "1E90FF"       # Blue
            }
            card.color(severity_colors.get(severity.lower(), "808080"))

            # Add sections
            if resource_id:
                section = pymsteams.cardsection()
                section.activityTitle("Primary Resource")
                section.activityText(f"`{resource_id}`")
                card.addSection(section)

            if affected_resources:
                section = pymsteams.cardsection()
                section.activityTitle(f"Affected Resources ({len(affected_resources)})")
                section.activityText("\\n".join(f"- `{r}`" for r in affected_resources[:5]))
                if len(affected_resources) > 5:
                    section.activityText(f"\\n... and {len(affected_resources) - 5} more")
                card.addSection(section)

            # Add metadata
            if metadata:
                section = pymsteams.cardsection()
                section.activityTitle("Details")
                for key, value in metadata.items():
                    section.addFact(key, str(value))
                card.addSection(section)

            # Add timestamp
            section = pymsteams.cardsection()
            section.addFact("Timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
            card.addSection(section)

            # Add action button if incident URL provided
            if incident_url:
                card.addLinkButton("View Incident Details", incident_url)

            # Send the card
            card.send()

            logger.info(f"Sent Teams incident alert: {title} (severity: {severity})")
            return {"success": True, "message": "Alert sent successfully"}

        except Exception as e:
            logger.error(f"Failed to send Teams incident alert: {e}")
            return {"success": False, "error": str(e)}

    def send_notification(
        self,
        title: str,
        message: str,
        color: Optional[str] = None,
        facts: Optional[Dict[str, str]] = None,
        buttons: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Send a general notification to Teams.

        Args:
            title: Notification title
            message: Notification message
            color: Hex color code (without #)
            facts: Dictionary of key-value facts to display
            buttons: List of buttons with 'text' and 'url' keys

        Returns:
            Dict with status and message
        """
        if not self.webhook_url:
            return {
                "success": False,
                "error": "Teams webhook not configured",
                "recommendation": (
                    "Webhook-based notifications are not configured. Consider using: "
                    "(1) Teams Bot for bidirectional chat - interact via /api/teams-bot/messages, "
                    "(2) Email alerts via SMTP - configure with /api/alerts endpoints, "
                    "(3) Azure Monitor Action Groups for production alerting"
                )
            }

        try:
            card = self._create_message_card(self.webhook_url)

            card.title(title)
            card.text(message)

            if color:
                card.color(color)

            # Add facts if provided
            if facts:
                section = pymsteams.cardsection()
                for key, value in facts.items():
                    section.addFact(key, value)
                card.addSection(section)

            # Add buttons if provided
            if buttons:
                for button in buttons:
                    if "text" in button and "url" in button:
                        card.addLinkButton(button["text"], button["url"])

            card.send()

            logger.info(f"Sent Teams notification: {title}")
            return {"success": True, "message": "Notification sent successfully"}

        except Exception as e:
            logger.error(f"Failed to send Teams notification: {e}")
            return {"success": False, "error": str(e)}

    def send_sre_status_update(
        self,
        operation: str,
        status: str,
        details: Dict[str, Any],
        resource_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an SRE operation status update.

        Args:
            operation: Operation name (e.g., "Resource Health Check", "Incident Triage")
            status: Operation status (success, failed, in_progress)
            details: Operation details dictionary
            resource_id: Related resource ID

        Returns:
            Dict with status and message
        """
        if not self.webhook_url:
            return {
                "success": False,
                "error": "Teams webhook not configured",
                "recommendation": (
                    "Webhook-based notifications are not configured. Consider using: "
                    "(1) Teams Bot for bidirectional chat - interact via /api/teams-bot/messages, "
                    "(2) Email alerts via SMTP - configure with /api/alerts endpoints, "
                    "(3) Azure Monitor Action Groups for production alerting"
                )
            }

        try:
            card = self._create_message_card(self.webhook_url)

            # Set status emoji
            status_emoji = {
                "success": "✅",
                "failed": "❌",
                "in_progress": "⏳",
                "warning": "⚠️"
            }
            emoji = status_emoji.get(status.lower(), "ℹ️")

            card.title(f"{emoji} SRE Operation: {operation}")
            card.text(f"Status: **{status.upper()}**")

            # Set color based on status
            status_colors = {
                "success": "00FF00",    # Green
                "failed": "FF0000",     # Red
                "in_progress": "FFD700",  # Gold
                "warning": "FFA500"     # Orange
            }
            card.color(status_colors.get(status.lower(), "1E90FF"))

            # Add resource if provided
            if resource_id:
                section = pymsteams.cardsection()
                section.activityTitle("Resource")
                section.activityText(f"`{resource_id}`")
                card.addSection(section)

            # Add details
            if details:
                section = pymsteams.cardsection()
                section.activityTitle("Details")
                for key, value in details.items():
                    # Truncate long values
                    value_str = str(value)
                    if len(value_str) > 200:
                        value_str = value_str[:197] + "..."
                    section.addFact(key, value_str)
                card.addSection(section)

            # Add timestamp
            section = pymsteams.cardsection()
            section.addFact("Timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
            card.addSection(section)

            card.send()

            logger.info(f"Sent SRE status update: {operation} - {status}")
            return {"success": True, "message": "Status update sent successfully"}

        except Exception as e:
            logger.error(f"Failed to send SRE status update: {e}")
            return {"success": False, "error": str(e)}

    def is_configured(self) -> bool:
        """Check if Teams webhook is configured"""
        return bool(self.webhook_url)
