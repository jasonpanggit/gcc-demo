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

from utils.response_models import StandardResponse
from utils.endpoint_decorators import (
    readonly_endpoint,
    write_endpoint,
    standard_endpoint
)

logger = logging.getLogger(__name__)

# Import main module dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import get_eol_orchestrator

# Create router for alert endpoints
router = APIRouter(tags=["Alert Management"])


# ============================================================================
# ALERT CONFIGURATION ENDPOINTS
# ============================================================================

@router.get("/api/alerts/config", response_model=StandardResponse)
@readonly_endpoint(agent_name="get_alert_config", timeout_seconds=20)
async def get_alert_configuration():
    """
    Get current alert configuration.
    
    Retrieves the alert configuration from Cosmos DB including SMTP settings,
    recipient lists, and notification preferences.
    
    Returns:
        StandardResponse with alert configuration dictionary.
    
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
    return {
        "success": True,
        "data": config.dict(),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/api/alerts/config", response_model=StandardResponse)
@write_endpoint(agent_name="save_alert_config", timeout_seconds=30)
async def save_alert_configuration(config_data: dict):
    """
    Save alert configuration to Cosmos DB.
    
    Updates the alert configuration with new SMTP settings, recipients,
    and notification preferences. Validates configuration before saving.
    
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
    config = AlertConfiguration(**config_data)
    success = await alert_manager.save_configuration(config)
    
    if success:
        return {
            "success": True,
            "message": "Configuration saved successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@router.post("/api/alerts/config/reload", response_model=StandardResponse)
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
    
    return {
        "success": True,
        "message": "Configuration reloaded successfully from Cosmos DB",
        "data": config.dict(),
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# ALERT PREVIEW & TESTING ENDPOINTS
# ============================================================================

@router.get("/api/alerts/preview", response_model=StandardResponse)
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
        get_eol_orchestrator().agents["os_inventory"].get_os_inventory(days=days, use_cache=True),
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


@router.post("/api/alerts/smtp/test", response_model=StandardResponse)
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


@router.post("/api/alerts/send", response_model=StandardResponse)
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
    use_html_body = request_data.get("use_html_body", False)
    
    logger.info(f"📧 Sending test alert: level={level}, recipients={recipients}")
    logger.info(f"📧 Custom subject: {custom_subject}, HTML: {use_html_body}")
    
    # Load configuration
    config = await alert_manager.load_configuration()
    
    # Use provided recipients or fall back to config
    if not recipients:
        recipients = config.recipients
        if not recipients:
            return {
                "success": False,
                "error": "No recipients configured",
                "message": "Please configure recipients in alert settings",
                "timestamp": datetime.utcnow().isoformat()
            }
    
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
            return {
                "success": True,
                "message": "Test alert sent successfully",
                "recipients": recipients,
                "subject": subject,
                "level": level,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Failed to send test alert",
                "message": "Check SMTP configuration and logs",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"❌ Error sending test alert: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Exception occurred while sending alert",
            "timestamp": datetime.utcnow().isoformat()
        }
