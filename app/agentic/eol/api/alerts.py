"""
Alert Management API Module

This module provides endpoints for configuring and managing email alerts for
End-of-Life (EOL) systems and software. It handles SMTP configuration, alert
preview generation, and test email sending.

Key Features:
    - Alert configuration management (SMTP, recipients, rules)
    - Configuration persistence to Cosmos DB
    - SMTP connection testing with detailed diagnostics
    - Alert preview generation based on OS inventory
    - Test email sending functionality
    - Configuration reload with cache clearing

Endpoints:
    GET  /api/alerts/config - Get current alert configuration
    POST /api/alerts/config - Save alert configuration
    POST /api/alerts/config/reload - Reload configuration from Cosmos DB
    GET  /api/alerts/preview - Preview alerts for current inventory
    POST /api/alerts/smtp/test - Test SMTP connection
    POST /api/alerts/send - Send test alert email

Author: GitHub Copilot
Date: October 2025
"""

import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
import logging

from utils.config import config
from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    readonly_endpoint,
    write_endpoint,
    standard_endpoint
)

logger = logging.getLogger(__name__)

# Create router for alert endpoints
router = APIRouter(tags=["Alert Management"])


def _get_eol_orchestrator():
    """Lazy import to avoid circular dependency"""
    from main import get_eol_orchestrator
    return get_eol_orchestrator()


# ============================================================================
# ALERT CONFIGURATION ENDPOINTS
# ============================================================================

@router.get("/api/alerts/config")
@readonly_endpoint(agent_name="get_alert_config", timeout_seconds=20)
async def get_alert_configuration():
    """
    Get current alert configuration.
    
    Retrieves the alert configuration from Cosmos DB including SMTP settings,
    recipient lists, and notification preferences.
    
    Returns:
        Dict with alert configuration (not wrapped in list).
    
    Example Response:
        {
            "success": true,
            "data": {
                "smtp": {
                    "server": "smtp.gmail.com",
                    "port": 587,
                    "use_tls": true,
                    "username": "alerts@company.com"
                },
                "recipients": ["admin@company.com"],
                "alert_rules": {
                    "eol_warning_days": 90,
                    "send_daily": true
                }
            },
            "timestamp": "2025-10-15T11:30:00Z"
        }
    """
    from utils.alert_manager import alert_manager

    config = await alert_manager.load_configuration()
    config_dict = config.dict()
    if "smtp_settings" in config_dict:
        config_dict["smtp_settings"]["password"] = "***"

    return StandardResponse.success_response(
        {
            "configuration": config_dict,
            "source": "cosmos" if config_dict.get("email_recipients") else "local",
        }
    )


@router.post("/api/alerts/config")
@write_endpoint(agent_name="save_alert_config", timeout_seconds=30)
async def save_alert_configuration(config_data: dict):
    """
    Save alert configuration to Cosmos DB.

    Updates the alert configuration with new SMTP settings, recipients,
    and notification preferences. Validates configuration before saving.
    If password is empty or not provided, keeps the existing password.

    Args:
        config_data: Dictionary with alert configuration (SMTP, recipients, etc.)

    Returns:
        StandardResponse indicating success or failure of save operation.

    Example Request:
        {
            "smtp": {
                "server": "smtp.gmail.com",
                "port": 587,
                "use_tls": true,
                "username": "alerts@company.com",
                "password": "app-password-here"
            },
            "recipients": ["admin@company.com", "team@company.com"],
            "alert_rules": {
                "eol_warning_days": 90,
                "send_daily": true,
                "alert_levels": ["high", "critical"]
            }
        }

    Example Response:
        {
            "success": true,
            "message": "Configuration saved successfully",
            "timestamp": "2025-10-15T11:35:00Z"
        }
    """
    from utils.alert_manager import alert_manager, AlertConfiguration

    try:
        # 🔍 DEBUG: Log received SMTP settings
        smtp_settings = config_data.get('smtp_settings', {})
        logger.info(f"🔍 DEBUG - Received SMTP settings:")
        logger.info(f"  Server: {smtp_settings.get('server', 'NOT SET')}")
        logger.info(f"  Port: {smtp_settings.get('port', 'NOT SET')}")
        logger.info(f"  Username: {smtp_settings.get('username', 'NOT SET')}")
        logger.info(f"  Password: {'***SET***' if smtp_settings.get('password') else '***EMPTY***'}")
        logger.info(f"  From Email: {smtp_settings.get('from_email', 'NOT SET')}")
        logger.info(f"  From Name: {smtp_settings.get('from_name', 'NOT SET')}")
        logger.info(f"  TLS: {smtp_settings.get('use_tls', 'NOT SET')}")
        logger.info(f"  SSL: {smtp_settings.get('use_ssl', 'NOT SET')}")
        logger.info(f"  Enabled: {smtp_settings.get('enabled', 'NOT SET')}")

        # Load existing configuration to preserve password if not provided
        existing_config = await alert_manager.load_configuration()

        # If password is empty or not provided, use existing password
        if 'smtp_settings' in config_data:
            new_password = config_data['smtp_settings'].get('password', '')
            if not new_password or new_password in ['***', '***SET***']:
                # Keep existing password
                logger.info("📝 Password not provided or masked - keeping existing password")
                config_data['smtp_settings']['password'] = existing_config.smtp_settings.password
            else:
                logger.info("📝 New password provided - updating password")

        logger.info(f"📝 Saving alert configuration")
        config = AlertConfiguration(**config_data)
        success = await alert_manager.save_configuration(config)

        if success:
            sanitized_config = config.dict()
            if "smtp_settings" in sanitized_config:
                sanitized_config["smtp_settings"]["password"] = "***"

            response = StandardResponse.success_response(
                {
                    "configuration": sanitized_config,
                },
                message="Configuration saved successfully",
            )
            logger.info("✅ Configuration saved successfully")
            return response
        else:
            logger.error("❌ Failed to save configuration to Cosmos DB")
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except Exception as e:
        logger.error(f"❌ Error saving alert configuration: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {str(e)}")


@router.post("/api/alerts/config/reload")
@write_endpoint(agent_name="reload_alert_config", timeout_seconds=30)
async def reload_alert_configuration():
    """
    Reload alert configuration from Cosmos DB (force refresh).
    
    Clears cached configuration and loads fresh settings from Cosmos DB.
    Useful after external configuration changes or troubleshooting.
    
    Returns:
        StandardResponse with reloaded configuration data.
    
    Example Response:
        {
            "success": true,
            "message": "Configuration reloaded successfully from Cosmos DB",
            "data": {
                "smtp": {...},
                "recipients": [...],
                "alert_rules": {...}
            },
            "timestamp": "2025-10-15T11:40:00Z"
        }
    """
    from utils.alert_manager import alert_manager
    
    # Clear cached configuration to force reload
    alert_manager._config = None
    
    # Load fresh configuration from Cosmos DB
    config = await alert_manager.load_configuration()
    
    config_dict = config.dict()
    if "smtp_settings" in config_dict:
        config_dict["smtp_settings"]["password"] = "***"

    response = StandardResponse.success_response(
        {
            "configuration": config_dict,
        },
        message="Configuration reloaded successfully from Cosmos DB",
    )
    return response


# ============================================================================
# ALERT PREVIEW & TESTING ENDPOINTS
# ============================================================================

@router.get("/api/alerts/preview")
@standard_endpoint(agent_name="alert_preview", timeout_seconds=35)
async def get_alert_preview(days: int = 90):
    """
    Get preview of alerts based on current configuration.
    
    Fetches OS inventory data and generates alert preview showing which
    computers would trigger alerts based on current EOL rules. Uses cached
    inventory data when available.
    
    Args:
        days: Number of days of inventory history to include (default: 90)
    
    Returns:
        StandardResponse with alert items, summary statistics, and configuration.
    
    Example Response:
        {
            "success": true,
            "data": {
                "alerts": [
                    {
                        "computer": "SERVER-01",
                        "os_name": "Windows Server 2012 R2",
                        "eol_date": "2023-10-10",
                        "days_until_eol": -730,
                        "severity": "critical"
                    }
                ],
                "summary": {
                    "total_alerts": 15,
                    "critical": 5,
                    "high": 7,
                    "medium": 3
                },
                "config": {
                    "alert_rules": {...}
                }
            },
            "timestamp": "2025-10-15T11:45:00Z"
        }
    """
    from utils.alert_manager import alert_manager
    
    # Get OS inventory data using agent's built-in caching
    logger.debug(f"🔄 Fetching OS inventory for alert preview (days={days})")
    os_data = await asyncio.wait_for(
        _get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days, use_cache=True),
        timeout=30.0,
    )
    
    # Extract inventory data from standardized response
    if isinstance(os_data, dict) and os_data.get("success"):
        inventory_data = os_data.get("data", [])
    elif isinstance(os_data, list):
        inventory_data = os_data
    else:
        logger.warning(f"⚠️ Invalid OS data format: {type(os_data)}")
        inventory_data = []
    
    # Merge Azure VMs from Resource Inventory so alert preview includes
    # both Arc-enabled servers and Azure VMs.
    try:
        from utils.resource_inventory_client import get_resource_inventory_client

        inv_client = get_resource_inventory_client()
        azure_vms = await inv_client.get_resources(
            "Microsoft.Compute/virtualMachines",
            subscription_id=config.azure.subscription_id,
        )

        existing_resource_ids = {
            str(item.get("resource_id") or item.get("resourceId") or "").lower()
            for item in inventory_data
            if str(item.get("resource_id") or item.get("resourceId") or "").strip()
        }

        for vm in azure_vms:
            selected = vm.get("selected_properties") or {}
            resource_id = str(vm.get("resource_id") or vm.get("id") or "")
            if not resource_id:
                continue
            if resource_id.lower() in existing_resource_ids:
                continue

            vm_name = vm.get("resource_name") or vm.get("name")
            if not vm_name:
                continue

            os_name = selected.get("os_image") or selected.get("os_type") or vm.get("os_name") or "Unknown"

            inventory_data.append({
                "computer_name": vm_name,
                "computer": vm_name,
                "os_name": os_name,
                "os_version": vm.get("os_version") or "",
                "os_type": selected.get("os_type") or vm.get("os_type") or "Unknown",
                "computer_environment": "Azure",
                "computer_type": "Azure VM",
                "resource_group": vm.get("resource_group") or vm.get("resourceGroup") or "",
                "resource_id": resource_id,
                "source": "resource_inventory",
                "vm_type": "azure-vm",
            })
            existing_resource_ids.add(resource_id.lower())
    except Exception as exc:
        logger.warning("Unable to merge Azure VMs into alert preview inventory: %s", exc)

    # Load configuration and generate preview
    config = await alert_manager.load_configuration()
    alert_items, summary = await alert_manager.generate_alert_preview(inventory_data, config)
    
    return {
        "success": True,
        "data": {
            "alerts": [item.dict() for item in alert_items],
            "summary": summary.dict(),
            "config": config.dict()
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/alerts/smtp/test")
@write_endpoint(agent_name="test_smtp", timeout_seconds=30)
async def test_smtp_connection(smtp_data: dict):
    """
    Test SMTP connection with provided settings.
    
    Validates SMTP settings by attempting to connect to the mail server.
    Includes detailed debugging information for troubleshooting connection issues.
    
    Args:
        smtp_data: Dictionary with SMTP settings (server, port, credentials, SSL/TLS)
    
    Returns:
        StandardResponse with success status, message, and debug information.
    
    Example Request:
        {
            "server": "smtp.gmail.com",
            "port": 587,
            "use_tls": true,
            "use_ssl": false,
            "username": "alerts@company.com",
            "password": "app-specific-password"
        }
    
    Example Response:
        {
            "success": true,
            "message": "SMTP connection successful",
            "timestamp": "2025-10-15T11:50:00Z",
            "debug_info": {
                "server": "smtp.gmail.com",
                "port": 587,
                "use_ssl": false,
                "use_tls": true,
                "username": "alerts@company.com",
                "has_password": true,
                "is_gmail": true
            }
        }
    """
    logger.info("📧 === SMTP TEST ENDPOINT CALLED ===")
    logger.info(f"📧 SMTP test data received: {smtp_data}")
    
    from utils.alert_manager import alert_manager, SMTPSettings
    
    # Create settings and log them (masking password)
    smtp_settings = SMTPSettings(**smtp_data)
    logger.info(f"📧 SMTP settings created - server: {smtp_settings.server}:{smtp_settings.port}")
    logger.info(f"📧 SMTP settings - SSL: {smtp_settings.use_ssl}, TLS: {smtp_settings.use_tls}")
    logger.info(f"📧 SMTP settings - username: {smtp_settings.username}")
    logger.info(f"📧 SMTP settings - password provided: {'Yes' if smtp_settings.password else 'No'}")
    
    # Execute the test
    logger.info("🔄 Calling alert_manager.test_smtp_connection...")
    success, message = await alert_manager.test_smtp_connection(smtp_settings)
    
    result = {
        "success": success,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "debug_info": {
            "server": smtp_settings.server,
            "port": smtp_settings.port,
            "use_ssl": smtp_settings.use_ssl,
            "use_tls": smtp_settings.use_tls,
            "username": smtp_settings.username,
            "has_password": bool(smtp_settings.password),
            "is_gmail": smtp_settings.is_gmail_config()
        }
    }
    
    logger.info(f"✅ SMTP test result: {result}")
    return result


@router.post("/api/alerts/send")
@write_endpoint(agent_name="send_alert", timeout_seconds=45)
async def send_test_alert(request_data: dict):
    """
    Send a test alert email with current configuration.
    
    Sends a test email alert using configured SMTP settings. Supports custom
    subject/body content or uses defaults. Content can be plain text or HTML.
    
    Args:
        request_data: Dictionary with optional recipients, level, custom_subject,
                     custom_body, and use_html_body flags
    
    Returns:
        StandardResponse with send results and detailed status information.
    
    Example Request:
        {
            "recipients": ["admin@company.com"],
            "level": "info",
            "custom_subject": "Test Alert",
            "custom_body": "This is a test alert message",
            "use_html_body": false
        }
    
    Example Response:
        {
            "success": true,
            "message": "Test alert sent successfully",
            "recipients": ["admin@company.com"],
            "subject": "Test Alert",
            "timestamp": "2025-10-15T11:55:00Z"
        }
    """
    from utils.alert_manager import alert_manager
    
    # Extract request parameters with defaults
    recipients = request_data.get("recipients")
    level = request_data.get("level", "info")
    custom_subject = request_data.get("custom_subject")
    custom_body = request_data.get("custom_body")
    use_html_body = request_data.get("use_html_body", request_data.get("is_html", False))
    
    logger.info(f"📧 Sending test alert: level={level}, recipients={recipients}")
    logger.info(f"📧 Custom subject: {custom_subject}, HTML: {use_html_body}")
    
    # Load configuration
    config = await alert_manager.load_configuration()
    
    # Use provided recipients or fall back to config
    if not recipients:
        recipients = config.email_recipients
        if not recipients:
            return StandardResponse.error_response(
                error="No recipients configured",
                message="Please configure recipients in alert settings",
            )
    
    # Generate test alert subject and body
    if custom_subject:
        subject = custom_subject
    else:
        subject = f"EOL Alert System Test - {level.upper()}"
    
    if custom_body:
        body = custom_body
    else:
        body = (
            f"This is a test alert from the EOL Alert System.\n\n"
            f"Alert Level: {level.upper()}\n"
            f"Timestamp: {datetime.utcnow().isoformat()}\n\n"
            f"If you received this message, your alert configuration is working correctly."
        )
    
    # Convert to HTML if requested
    if use_html_body and custom_body:
        body = f"<html><body><pre>{body}</pre></body></html>"
    
    try:
        # Send the alert
        success = await alert_manager.send_alert(
            subject=subject,
            body=body,
            recipients=recipients,
            level=level
        )
        
        if success:
            return StandardResponse.success_response(
                {
                    "recipients": recipients,
                    "recipients_count": len(recipients),
                    "subject": subject,
                    "level": level,
                },
                message="Test alert sent successfully",
            )
        else:
            return StandardResponse.error_response(
                error="Failed to send test alert",
                message="Check SMTP configuration and logs",
            )
    except Exception as e:
        logger.error(f"❌ Error sending test alert: {e}", exc_info=True)
        return StandardResponse.error_response(
            error=str(e),
            message="Exception occurred while sending alert",
        )


@router.post("/api/alerts/send-teams-test")
@write_endpoint(agent_name="send_teams_test", timeout_seconds=30)
async def send_teams_test_alert():
    """
    Send a test alert notification to Microsoft Teams.

    Uses the MCP Orchestrator's Teams bot integration to send a test alert
    to the configured Teams channel via webhook.

    Returns:
        StandardResponse with Teams send results and status information.

    Example Response:
        {
            "success": true,
            "message": "Teams test alert sent successfully",
            "teams": {
                "sent": true,
                "message": "Teams alert sent successfully"
            },
            "timestamp": "2025-10-15T12:00:00Z"
        }
    """
    from utils.alert_manager import alert_manager, AlertPreviewItem
    from datetime import datetime, timedelta

    try:
        logger.info("📧 Sending test Teams alert...")

        # Load configuration to check if Teams is enabled
        config = await alert_manager.load_configuration()

        # Create sample alert items for testing
        sample_items = [
            AlertPreviewItem(
                computer="TEST-SERVER-01",
                os_name="Windows Server 2016",
                version="Standard",
                eol_date=datetime.now() + timedelta(days=60),
                days_until_eol=60,
                alert_level="info"
            ),
            AlertPreviewItem(
                computer="TEST-SERVER-02",
                os_name="Ubuntu 20.04 LTS",
                version="20.04",
                eol_date=datetime.now() + timedelta(days=180),
                days_until_eol=180,
                alert_level="info"
            )
        ]

        # Send Teams alert with teams_enabled flag
        success, message = await alert_manager.send_alert_teams(
            sample_items,
            "info",
            teams_enabled=config.teams_settings.enabled
        )

        if success:
            return StandardResponse.success_response(
                {
                    "teams": {
                        "sent": True,
                        "message": message,
                    }
                },
                message="Test Teams alert sent successfully",
            )
        else:
            return StandardResponse.error_response(
                error=message,
                message="Failed to send Teams test alert",
                details={
                    "teams": {
                        "sent": False,
                        "message": message,
                    }
                },
            )
    except Exception as e:
        logger.error(f"❌ Error sending test Teams alert: {e}", exc_info=True)
        return StandardResponse.error_response(
            error=str(e),
            message="Exception occurred while sending Teams test alert",
        )


@router.post("/api/alerts/send-teams-bot-notification")
@write_endpoint(agent_name="send_teams_bot_notification", timeout_seconds=45)
async def send_teams_bot_notification(
    alert_level: str = "info",
    conversation_id: Optional[str] = None,
    recipient_email: Optional[str] = None
):
    """
    Send an alert notification via Teams Bot to a specific conversation or user.

    This endpoint sends proactive EOL alert notifications through the Teams Bot,
    allowing you to see the formatted alert in a Teams conversation.

    Args:
        alert_level: Alert severity level ('critical', 'warning', 'info')
        conversation_id: Optional Teams conversation ID to send to
        recipient_email: Optional user email to send 1:1 message

    Returns:
        StandardResponse with send status and details

    Example Request:
        POST /api/alerts/send-teams-bot-notification?alert_level=critical

    Example Response:
        {
            "success": true,
            "message": "Alert notification sent via Teams Bot",
            "data": [{
                "alert_level": "critical",
                "systems_count": 2,
                "notification_sent": true,
                "delivery_method": "teams_bot"
            }]
        }
    """
    from utils.alert_manager import alert_manager, AlertPreviewItem
    from datetime import timedelta
    import os
    import aiohttp

    try:
        logger.info(f"📱 Sending {alert_level} alert notification via Teams Bot...")

        # Get Teams Bot credentials
        bot_app_id = os.getenv("TEAMS_BOT_APP_ID")
        bot_app_password = os.getenv("TEAMS_BOT_APP_PASSWORD")
        tenant_id = os.getenv("AZURE_TENANT_ID", "ffc83107-fcc0-4d2e-8798-d582da36505e")

        if not bot_app_id or not bot_app_password:
            return StandardResponse.error_response(
                error="Teams Bot not configured",
                message="TEAMS_BOT_APP_ID and TEAMS_BOT_APP_PASSWORD environment variables required",
            )

        # Create sample alert items for the notification
        sample_items = [
            AlertPreviewItem(
                computer="PROD-WEB-01",
                os_name="Windows Server 2016",
                version="Standard",
                eol_date=datetime.now() + timedelta(days=45),
                days_until_eol=45,
                alert_level=alert_level
            ),
            AlertPreviewItem(
                computer="PROD-DB-02",
                os_name="Ubuntu 18.04 LTS",
                version="18.04",
                eol_date=datetime.now() + timedelta(days=90),
                days_until_eol=90,
                alert_level=alert_level
            )
        ]

        # Filter by alert level
        level_items = [item for item in sample_items if item.alert_level == alert_level]

        if not level_items:
            return StandardResponse.error_response(
                error="No items match alert level",
                message=f"No {alert_level} items found in sample data",
            )

        # Build alert message
        level_title = alert_level.capitalize()
        emoji_map = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}
        emoji = emoji_map.get(alert_level, "📢")

        message_lines = [
            f"{emoji} **EOL {level_title} Alert - {len(level_items)} Systems**",
            "",
            f"{len(level_items)} systems are approaching their End-of-Life dates and require attention.",
            "",
            "**Affected Systems:**"
        ]

        for item in sorted(level_items, key=lambda x: x.days_until_eol):
            days_text = f"{item.days_until_eol} days remaining"
            message_lines.append(
                f"• **{item.computer}**: {item.os_name} {item.version} - "
                f"EOL: {item.eol_date.strftime('%Y-%m-%d')} ({days_text})"
            )

        message_lines.extend([
            "",
            "**Recommended Actions:**",
            "• Plan upgrade or migration for affected systems",
            "• Review security implications of EOL systems",
            "• Contact vendors for extended support options",
            "• Update system documentation and inventory",
            "",
            f"_Alert generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        ])

        alert_message = "\n".join(message_lines)

        # Get Bot Framework access token
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": bot_app_id,
            "client_secret": bot_app_password,
            "scope": "https://api.botframework.com/.default"
        }

        async with aiohttp.ClientSession() as session:
            # Get access token
            async with session.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as token_response:
                if token_response.status != 200:
                    error_text = await token_response.text()
                    logger.error(f"Failed to get Bot Framework token: {token_response.status} - {error_text}")
                    return StandardResponse.error_response(
                        error="Authentication failed",
                        message="Failed to get Bot Framework token",
                        )

                token_json = await token_response.json()
                access_token = token_json.get("access_token")

                if not access_token:
                    return StandardResponse.error_response(
                        error="No access token",
                        message="Failed to obtain Bot Framework access token",
                    )

            # Determine target for message
            if conversation_id:
                # Send to existing conversation
                service_url = "https://smba.trafficmanager.net/amer"
                message_url = f"{service_url}/v3/conversations/{conversation_id}/activities"
                target_description = f"conversation {conversation_id}"
            elif recipient_email:
                # Create 1:1 conversation with user
                # Note: This requires knowing the user's Teams ID or AAD object ID
                return StandardResponse.error_response(
                    error="Direct messaging not yet implemented",
                    message="Please provide a conversation_id instead. Direct user messaging requires AAD user lookup.",
                )
            else:
                # No target specified - return instructions
                return StandardResponse.error_response(
                    error="No target specified",
                    message="Please provide either conversation_id or recipient_email parameter. To find your conversation ID, send any message to the bot in Teams and check the logs.",
                    details={
                        "teams_bot_help": {
                            "how_to_find_conversation_id": [
                                "1. Open Teams and start a chat with the bot",
                                "2. Send any message (e.g., 'hello')",
                                "3. Check the application logs for 'Received Teams bot activity'",
                                "4. Copy the conversation ID from the logs",
                                "5. Use that ID in the conversation_id parameter"
                            ],
                            "alternative": "Or use the test endpoint: POST /api/alerts/test-teams"
                        }
                    },
                )

            # Send message to Teams
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            message_body = {
                "type": "message",
                "from": {"id": bot_app_id},
                "text": alert_message
            }

            async with session.post(message_url, json=message_body, headers=headers) as send_response:
                if send_response.status not in (200, 201):
                    error_text = await send_response.text()
                    logger.error(f"Failed to send Teams message: {send_response.status} - {error_text}")
                    return StandardResponse.error_response(
                        error=f"Send failed with status {send_response.status}",
                        message=f"Failed to send message to {target_description}",
                        details={"response_body": error_text},
                    )

                logger.info(f"✅ Successfully sent alert notification to {target_description}")

                return StandardResponse.success_response(
                    {
                        "alert_level": alert_level,
                        "systems_count": len(level_items),
                        "notification_sent": True,
                        "delivery_method": "teams_bot",
                        "target": target_description,
                        "message_preview": alert_message[:200] + "..." if len(alert_message) > 200 else alert_message,
                    },
                    message=f"Alert notification sent via Teams Bot to {target_description}",
                )

    except Exception as e:
        logger.error(f"❌ Error sending Teams Bot notification: {e}", exc_info=True)
        return StandardResponse.error_response(
            error=str(e),
            message="Exception occurred while sending Teams Bot notification",
        )


@router.get("/api/alerts/teams-bot-conversations")
@readonly_endpoint(agent_name="teams_bot_conversations", timeout_seconds=20)
async def get_teams_bot_conversations():
    """
    Get list of active Teams Bot conversations.

    This endpoint retrieves the list of active conversation IDs that you can use
    to send alert notifications via the send-teams-bot-notification endpoint.

    Returns:
        List of active conversation IDs with metadata

    Example Response:
        {
            "success": true,
            "message": "Found 2 active conversations",
            "data": [{
                "conversations": [
                    {
                        "conversation_id": "a:1v...",
                        "message_count": 10,
                        "last_updated": "2025-02-15T08:30:00Z",
                        "age_hours": 2.5
                    }
                ],
                "total_conversations": 2,
                "instructions": "Use conversation_id with /api/alerts/send-teams-bot-notification"
            }]
        }
    """
    try:
        # Import conversation state from teams_bot module
        from api.teams_bot import _conversation_states

        if not _conversation_states:
            return StandardResponse.success_response(
                {
                    "conversations": [],
                    "total_conversations": 0,
                    "help": {
                        "how_to_start_conversation": [
                            "1. Open Microsoft Teams",
                            "2. Search for your bot by name or App ID",
                            "3. Start a chat and send any message (e.g., 'hello')",
                            "4. The conversation will appear in this list"
                        ]
                    },
                },
                count=0,
                message="No active Teams Bot conversations found",
            )

        # Build conversation list
        conversations = []
        for conv_id, state in _conversation_states.items():
            last_updated = state.get("last_updated")
            age_hours = None
            if last_updated:
                age = datetime.utcnow() - last_updated
                age_hours = round(age.total_seconds() / 3600, 1)

            conversations.append({
                "conversation_id": conv_id,
                "message_count": len(state.get("history", [])),
                "last_updated": last_updated.isoformat() + "Z" if last_updated else None,
                "age_hours": age_hours
            })

        # Sort by most recent first
        conversations.sort(key=lambda x: x["last_updated"] or "", reverse=True)

        return StandardResponse.success_response(
            {
                "conversations": conversations,
                "total_conversations": len(conversations),
                "instructions": "Use conversation_id with POST /api/alerts/send-teams-bot-notification?conversation_id=<id>&alert_level=<level>",
            },
            count=len(conversations),
            message=f"Found {len(conversations)} active conversation(s)",
        )

    except Exception as e:
        logger.error(f"❌ Error getting Teams Bot conversations: {e}", exc_info=True)
        return StandardResponse.error_response(
            error=str(e),
            message="Exception occurred while retrieving Teams Bot conversations",
        )
