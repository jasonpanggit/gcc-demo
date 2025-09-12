"""
Alert Management Module for EOL Platform
Handles alert configuration, SMTP settings, and email notifications
"""
import smtplib
import ssl
import json
import os
import socket
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel, validator
try:
    from pydantic import EmailStr
except ImportError:
    # Fallback for older pydantic versions
    EmailStr = str
import aiofiles
import asyncio
from pathlib import Path

from utils import get_logger, config
from utils.cosmos_cache import base_cosmos

logger = get_logger(__name__)

# # SECURITY NOTE: This is a placeholder - use environment variables in production
# Set via: export GMAIL_APP_PASSWORD="your_app_password_here" - gmail app password

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SMTPSettings(BaseModel):
    """SMTP configuration settings"""
    enabled: bool = False
    server: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = ""
    from_name: str = "EOL Alert System"
    
    @validator('port')
    def validate_port(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError('Port must be between 1 and 65535')
        return v
    
    def is_gmail_config(self) -> bool:
        """Check if this appears to be a Gmail configuration"""
        return "gmail.com" in self.server.lower() or "smtp.gmail.com" in self.server.lower()
    
    def get_recommended_settings_for_gmail(self) -> dict:
        """Get recommended settings for Gmail"""
        return {
            "server": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "description": "Gmail requires TLS on port 587 and an App Password instead of your regular password"
        }

class AlertPeriod(BaseModel):
    """Alert period configuration"""
    period: int
    unit: str  # 'days', 'weeks', 'months', 'years'
    frequency: str  # 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'
    
    @validator('unit')
    def validate_unit(cls, v):
        if v not in ['days', 'weeks', 'months', 'years']:
            raise ValueError('Unit must be one of: days, weeks, months, years')
        return v
    
    @validator('frequency')
    def validate_frequency(cls, v):
        if v not in ['daily', 'weekly', 'monthly', 'quarterly', 'yearly']:
            raise ValueError('Frequency must be one of: daily, weekly, monthly, quarterly, yearly')
        return v

class AlertConfiguration(BaseModel):
    """Complete alert configuration"""
    enabled: bool = True
    critical: AlertPeriod = AlertPeriod(period=3, unit='months', frequency='weekly')
    warning: AlertPeriod = AlertPeriod(period=6, unit='months', frequency='monthly')
    info: AlertPeriod = AlertPeriod(period=12, unit='months', frequency='quarterly')
    email_recipients: List[str] = []
    webhook_url: Optional[str] = None
    smtp_settings: SMTPSettings = SMTPSettings()
    last_sent: Dict[str, str] = {}  # Track when alerts were last sent

class AlertPreviewItem(BaseModel):
    """Preview item for alerts"""
    computer: str
    os_name: str
    version: str
    eol_date: datetime
    days_until_eol: int
    alert_level: str

class AlertSummary(BaseModel):
    """Alert summary statistics"""
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    total_os_count: int = 0

class NotificationRecord(BaseModel):
    """Record of a sent notification for tracking and history"""
    id: str  # Unique identifier for the notification
    timestamp: str  # ISO format timestamp when notification was sent
    alert_type: str  # 'critical', 'warning', 'info'
    recipients: List[str]  # List of email addresses
    recipient_count: int  # Number of recipients
    items_count: int  # Number of alert items included
    status: str  # 'success' or 'failed'
    error_message: Optional[str] = None  # Error message if failed
    email_subject: Optional[str] = None  # Subject line of the email
    frequency: str  # Frequency setting at time of sending
    created_at: str  # ISO format timestamp when record was created
    updated_at: str  # ISO format timestamp when record was last updated

class NotificationHistory(BaseModel):
    """Container for notification history with statistics"""
    notifications: List[NotificationRecord] = []
    total_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    last_notification_date: Optional[str] = None

# ============================================================================
# ALERT MANAGER CLASS
# ============================================================================

class AlertManager:
    """Manages EOL alerts and SMTP configuration with Cosmos DB persistence"""
    
    def __init__(self):
        # Keep file-based config as fallback
        self.config_file = Path(__file__).parent / "data" / "alert_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        self._config: Optional[AlertConfiguration] = None
        
        # Cosmos DB configuration - following pattern from other cache modules
        self.config_container_name = "alert_configuration"
        self.config_document_id = "global_alert_config"
        self.partition_path = "/config_type"
        self.container = None
        self.initialized = False
        
        # Notification tracking container configuration
        self.notification_container_name = "notification_history"
        self.notification_partition_path = "/alert_type"
        self.notification_container = None
        
    def _ensure_container(self):
        """Ensure containers are available, get them if needed - following eol_cache pattern"""
        if not self.container and hasattr(base_cosmos, 'initialized') and base_cosmos.initialized:
            try:
                self.container = base_cosmos.get_container(
                    container_id=self.config_container_name,
                    partition_path=self.partition_path,
                    offer_throughput=400
                )
                logger.debug(f"Alert manager container {self.config_container_name} obtained")
            except Exception as e:
                logger.error(f"Error getting alert configuration container: {e}")
                self.container = None
        
        # Ensure notification tracking container
        if not self.notification_container and hasattr(base_cosmos, 'initialized') and base_cosmos.initialized:
            try:
                self.notification_container = base_cosmos.get_container(
                    container_id=self.notification_container_name,
                    partition_path=self.notification_partition_path,
                    offer_throughput=400
                )
                logger.debug(f"Notification tracking container {self.notification_container_name} obtained")
            except Exception as e:
                logger.error(f"Error getting notification tracking container: {e}")
                self.notification_container = None
    
    async def initialize(self):
        """Initialize the alert manager and ensure Cosmos DB is ready - following eol_cache pattern"""
        if self.initialized and self.container:
            return  # Already initialized
            
        try:
            # Ensure base cosmos is initialized
            await base_cosmos._initialize_async()
            
            # Get container if not already available
            if not self.container:
                self._ensure_container()
                
            self.initialized = True
            logger.debug(f"AlertManager initialized with container {self.config_container_name}")
        except Exception as e:
            logger.debug(f"AlertManager initialize failed: {e}")
    
    async def _get_cosmos_container(self):
        """Get or create Cosmos DB container for alert configuration"""
        try:
            # Ensure initialization
            await self.initialize()
            self._ensure_container()
            return self.container
        except Exception as e:
            logger.error(f"Error getting Cosmos container for alert config: {e}")
            return None
    
    async def load_configuration(self) -> AlertConfiguration:
        """Load alert configuration from Cosmos DB with file fallback - following inventory_cache pattern"""
        if self._config is not None:
            return self._config
            
        # Try loading from Cosmos DB first
        try:
            container = await self._get_cosmos_container()
            if container:
                logger.info("Loading alert configuration from Cosmos DB...")
                
                # Query for the configuration document - following inventory_cache pattern
                query = "SELECT * FROM c WHERE c.id = @config_id"
                params = [{"name": "@config_id", "value": self.config_document_id}]
                items = list(container.query_items(
                    query=query, 
                    parameters=params, 
                    enable_cross_partition_query=True
                ))
                
                if items:
                    config_data = items[0]
                    # Remove Cosmos DB metadata - following eol_cache pattern
                    cosmos_metadata_fields = ['id', '_rid', '_self', '_etag', '_attachments', '_ts', 'config_type', 'created_at', 'updated_at']
                    for field in cosmos_metadata_fields:
                        config_data.pop(field, None)
                    
                    self._config = AlertConfiguration(**config_data)
                    logger.info("Alert configuration loaded successfully from Cosmos DB")
                    return self._config
                else:
                    logger.info("No alert configuration found in Cosmos DB, will create default")
        except Exception as e:
            logger.warning(f"Error loading alert configuration from Cosmos DB: {e}")
            
        # Fallback to file-based configuration
        try:
            if self.config_file.exists():
                logger.info("Loading alert configuration from file (fallback)...")
                async with aiofiles.open(self.config_file, 'r') as f:
                    data = json.loads(await f.read())
                    self._config = AlertConfiguration(**data)
                    logger.info("Alert configuration loaded successfully from file")
                    
                    # Save to Cosmos DB for future use
                    await self.save_configuration(self._config)
            else:
                logger.info("No configuration file found, creating default")
                self._config = AlertConfiguration()
                await self.save_configuration(self._config)
        except Exception as e:
            logger.error(f"Error loading alert configuration from file: {e}")
            self._config = AlertConfiguration()
            
        return self._config
    
    async def save_configuration(self, config: AlertConfiguration) -> bool:
        """Save alert configuration to Cosmos DB with file fallback - following inventory_cache pattern"""
        success = False
        
        # Try saving to Cosmos DB first
        try:
            container = await self._get_cosmos_container()
            if container:
                logger.info("Saving alert configuration to Cosmos DB...")
                
                # Prepare document for Cosmos DB - following inventory_cache pattern
                config_data = config.dict()
                config_doc = {
                    "id": self.config_document_id,
                    "config_type": "alert_configuration",  # This is the partition key
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    **config_data
                }
                
                # Validate document before upserting - following eol_cache pattern
                if not config_doc.get('id'):
                    logger.error("Alert configuration document missing required 'id' field")
                    raise ValueError("Document missing required 'id' field")
                    
                if not config_doc.get('config_type'):
                    logger.error("Alert configuration document missing required 'config_type' partition key")
                    raise ValueError("Document missing required 'config_type' partition key")
                
                # Clean any invalid characters that might cause BadRequest - following eol_cache pattern
                if isinstance(config_doc.get('id'), str):
                    invalid_chars = ['/', '\\', '?', '#']
                    clean_id = config_doc['id']
                    for char in invalid_chars:
                        clean_id = clean_id.replace(char, '_')
                    config_doc['id'] = clean_id
                
                # Log document structure for debugging
                logger.debug(f"Upserting alert config with ID: {config_doc['id']}, config_type: {config_doc['config_type']}")
                
                # Upsert the configuration document
                try:
                    result = container.upsert_item(config_doc)
                    if result:
                        self._config = config
                        logger.info("Alert configuration saved successfully to Cosmos DB")
                        success = True
                    else:
                        logger.error("Failed to save alert configuration to Cosmos DB")
                except Exception as upsert_error:
                    logger.error(f"Cosmos DB upsert failed for alert config {config_doc['id']}: {upsert_error}")
                    logger.error(f"Alert config document structure: {config_doc}")
                    # Continue with file fallback even if Cosmos fails
        except Exception as e:
            logger.error(f"Error saving alert configuration to Cosmos DB: {e}")
            
        # Also save to file as backup - following inventory_cache pattern
        try:
            data = config.dict()
            async with aiofiles.open(self.config_file, 'w') as f:
                await f.write(json.dumps(data, indent=2, default=str))
            logger.info("Alert configuration also saved to file as backup")
            
            # If Cosmos DB failed but file succeeded, consider it a success
            if not success:
                self._config = config
                success = True
                
        except Exception as e:
            logger.error(f"Error saving alert configuration to file: {e}")
            
        return success
    
    async def clear_configuration(self) -> bool:
        """Clear alert configuration from both Cosmos DB and file - following inventory_cache pattern"""
        success = False
        
        # Clear from Cosmos DB
        try:
            container = await self._get_cosmos_container()
            if container:
                logger.info("Clearing alert configuration from Cosmos DB...")
                try:
                    container.delete_item(
                        item=self.config_document_id, 
                        partition_key="alert_configuration"
                    )
                    logger.info("Alert configuration cleared from Cosmos DB")
                    success = True
                except Exception as e:
                    # Check if it's a "NotFound" error - this is OK, means already cleared
                    if "NotFound" in str(e) or "does not exist" in str(e):
                        logger.info("Alert configuration already cleared - document not found in Cosmos DB")
                        success = True
                    else:
                        logger.error(f"Error clearing alert configuration from Cosmos DB: {e}")
        except Exception as e:
            logger.error(f"Error accessing Cosmos DB for alert configuration clearing: {e}")
        
        # Clear from file
        try:
            if self.config_file.exists():
                self.config_file.unlink()
                logger.info("Alert configuration file deleted")
            
            # If file clear succeeded, consider it a success even if Cosmos failed
            if not success:
                success = True
                
        except Exception as e:
            logger.error(f"Error deleting alert configuration file: {e}")
        
        # Clear cached configuration
        self._config = None
        
        return success
    
    def convert_to_days(self, period: int, unit: str) -> int:
        """Convert period to days"""
        multipliers = {
            'days': 1,
            'weeks': 7,
            'months': 30,  # Approximate
            'years': 365   # Approximate
        }
        return period * multipliers.get(unit, 30)
    
    def get_mock_eol_date(self, os_name: str, os_version: str) -> Optional[datetime]:
        """Get mock EOL date for demonstration"""
        mock_dates = {
            'Windows Server 2012': datetime(2023, 10, 10),
            'Windows Server 2012 R2': datetime(2023, 10, 10),
            'Windows Server 2016': datetime(2027, 1, 12),
            'Windows Server 2019': datetime(2029, 1, 9),
            'Windows Server 2022': datetime(2031, 10, 14),
            'Windows 10': datetime(2025, 10, 14),
            'Windows 11': datetime(2031, 10, 14),
            'Ubuntu 18.04': datetime(2023, 5, 31),
            'Ubuntu 20.04': datetime(2025, 4, 30),
            'Ubuntu 22.04': datetime(2027, 4, 30),
            'CentOS 7': datetime(2024, 6, 30),
            'CentOS 8': datetime(2021, 12, 31),
            'RHEL 7': datetime(2024, 6, 30),
            'RHEL 8': datetime(2029, 5, 31),
            'RHEL 9': datetime(2032, 5, 31)
        }
        
        # Try exact match
        key = os_name
        if key in mock_dates:
            return mock_dates[key]
            
        # Try with version
        key = f"{os_name} {os_version}"
        if key in mock_dates:
            return mock_dates[key]
            
        # Try partial matches
        for mock_key, date in mock_dates.items():
            if (os_name.lower() in mock_key.lower() or 
                mock_key.lower() in os_name.lower()):
                return date
                
        # Default future date
        import random
        days_ahead = random.randint(365, 365 * 3)
        return datetime.now() + timedelta(days=days_ahead)
    
    async def generate_alert_preview(self, os_inventory: List[Dict], config: AlertConfiguration) -> tuple[List[AlertPreviewItem], AlertSummary]:
        """Generate preview of alerts based on configuration"""
        if not config.enabled:
            return [], AlertSummary(total_os_count=len(os_inventory))
            
        now = datetime.now()
        alert_items = []
        
        # Convert periods to days
        critical_days = self.convert_to_days(config.critical.period, config.critical.unit)
        warning_days = self.convert_to_days(config.warning.period, config.warning.unit)
        info_days = self.convert_to_days(config.info.period, config.info.unit)
        
        for os_item in os_inventory:
            eol_date = self.get_mock_eol_date(
                os_item.get('os_name', ''),
                os_item.get('os_version', '')
            )
            
            if eol_date:
                days_until_eol = (eol_date - now).days
                
                alert_level = None
                if 0 <= days_until_eol <= critical_days:
                    alert_level = 'critical'
                elif 0 <= days_until_eol <= warning_days:
                    alert_level = 'warning'
                elif 0 <= days_until_eol <= info_days:
                    alert_level = 'info'
                
                if alert_level:
                    alert_items.append(AlertPreviewItem(
                        computer=os_item.get('computer_name', os_item.get('computer', 'Unknown')),
                        os_name=os_item.get('os_name', 'Unknown OS'),
                        version=os_item.get('os_version', 'Unknown'),
                        eol_date=eol_date,
                        days_until_eol=days_until_eol,
                        alert_level=alert_level
                    ))
        
        # Sort by urgency
        alert_items.sort(key=lambda x: x.days_until_eol)
        
        # Generate summary
        summary = AlertSummary(
            critical_count=len([a for a in alert_items if a.alert_level == 'critical']),
            warning_count=len([a for a in alert_items if a.alert_level == 'warning']),
            info_count=len([a for a in alert_items if a.alert_level == 'info']),
            total_os_count=len(os_inventory)
        )
        
        return alert_items, summary
    
    async def test_smtp_connection(self, smtp_settings: SMTPSettings) -> tuple[bool, str]:
        """Test SMTP connection with detailed debugging and network diagnostics"""
        server = None
        try:
            logger.info("=== SMTP Connection Test Started ===")
            logger.info(f"SMTP Settings - Server: {smtp_settings.server}:{smtp_settings.port}")
            logger.info(f"SMTP Settings - SSL: {smtp_settings.use_ssl}, TLS: {smtp_settings.use_tls}")
            logger.info(f"SMTP Settings - Username: {smtp_settings.username}")
            logger.info(f"SMTP Settings - From Email: {smtp_settings.from_email}")
            logger.info(f"SMTP Settings - Gmail Config: {smtp_settings.is_gmail_config()}")
            
            if not smtp_settings.enabled:
                logger.warning("SMTP is disabled in configuration")
                return False, "SMTP is disabled"
            
            # Network diagnostics first
            logger.info("=== Starting Network Diagnostics ===")
            
            # Test DNS resolution
            try:
                logger.info(f"Testing DNS resolution for {smtp_settings.server}...")
                ip_address = socket.gethostbyname(smtp_settings.server)
                logger.info(f"✅ DNS resolution successful: {smtp_settings.server} -> {ip_address}")
            except socket.gaierror as e:
                logger.error(f"❌ DNS resolution failed: {e}")
                return False, f"DNS resolution failed for {smtp_settings.server}: {str(e)}"
            
            # Test basic TCP connectivity
            try:
                logger.info(f"Testing TCP connectivity to {smtp_settings.server}:{smtp_settings.port}...")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)  # 10 second timeout for TCP test
                result = sock.connect_ex((smtp_settings.server, smtp_settings.port))
                sock.close()
                
                if result == 0:
                    logger.info(f"✅ TCP connectivity successful to {smtp_settings.server}:{smtp_settings.port}")
                else:
                    logger.error(f"❌ TCP connectivity failed to {smtp_settings.server}:{smtp_settings.port} (error code: {result})")
                    return False, f"TCP connection failed to {smtp_settings.server}:{smtp_settings.port}"
            except Exception as e:
                logger.error(f"❌ TCP connectivity test failed: {e}")
                return False, f"TCP connectivity test failed: {str(e)}"
                
            # Create and connect to SMTP server with timeout
            logger.info("Creating SMTP connection...")
            if smtp_settings.use_ssl:
                logger.info("Using SMTP_SSL connection")
                context = ssl.create_default_context()
                logger.debug(f"SSL Context created with default settings")
                server = smtplib.SMTP_SSL(smtp_settings.server, smtp_settings.port, context=context, timeout=30)
                logger.info(f"SMTP_SSL connection established to {smtp_settings.server}:{smtp_settings.port}")
            else:
                logger.info("Using regular SMTP connection")
                server = smtplib.SMTP(smtp_settings.server, smtp_settings.port, timeout=30)
                logger.info(f"SMTP connection established to {smtp_settings.server}:{smtp_settings.port}")
                
                if smtp_settings.use_tls:
                    logger.info("Starting TLS encryption...")
                    context = ssl.create_default_context()
                    logger.debug(f"TLS Context created with default settings")
                    server.starttls(context=context)
                    logger.info("TLS encryption enabled successfully")
            
            # Enable debug mode for even more detailed SMTP logging
            server.set_debuglevel(1)
            logger.info("SMTP debug mode enabled for detailed protocol logging")
            
            # Test authentication if credentials provided
            if smtp_settings.username and smtp_settings.password:
                logger.info(f"Testing authentication for user: {smtp_settings.username}")
                server.login(smtp_settings.username, smtp_settings.password)
                logger.info("SMTP authentication successful")
            else:
                logger.warning("No authentication credentials provided - testing anonymous connection")
            
            # Send a test message to verify the connection works
            logger.info("Testing connection with NOOP command...")
            server.noop()  # No-operation to test connection
            logger.info("NOOP command successful - connection is active")
            
            logger.info("=== SMTP Connection Test PASSED ===")
            return True, "SMTP connection successful"
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "SMTP authentication failed - check username/password"
            if smtp_settings.is_gmail_config():
                error_msg += " (Gmail requires App Password, not regular password)"
            logger.error(f"=== SMTP AUTH ERROR === {error_msg}")
            logger.error(f"Auth error details: {str(e)}")
            logger.error(f"Username attempted: {smtp_settings.username}")
            logger.error(f"Server: {smtp_settings.server}:{smtp_settings.port}")
            return False, error_msg
        except smtplib.SMTPConnectError as e:
            error_msg = "Could not connect to SMTP server - check server/port"
            if smtp_settings.is_gmail_config():
                error_msg += " (Gmail uses port 587 with TLS or 465 with SSL)"
            logger.error(f"=== SMTP CONNECT ERROR === {error_msg}")
            logger.error(f"Connect error details: {str(e)}")
            logger.error(f"Attempted connection: {smtp_settings.server}:{smtp_settings.port}")
            logger.error(f"SSL enabled: {smtp_settings.use_ssl}, TLS enabled: {smtp_settings.use_tls}")
            return False, error_msg
        except ssl.SSLError as e:
            error_msg = "SSL/TLS connection error"
            if smtp_settings.is_gmail_config():
                error_msg += " (Check TLS/SSL settings for Gmail)"
            logger.error(f"=== SSL/TLS ERROR === {error_msg}")
            logger.error(f"SSL error details: {str(e)}")
            logger.error(f"SSL settings - use_ssl: {smtp_settings.use_ssl}, use_tls: {smtp_settings.use_tls}")
            return False, error_msg
        except (TimeoutError, OSError) as e:
            error_msg = "Connection timeout - SMTP server not responding"
            if "timed out" in str(e).lower():
                error_msg += " (30 second timeout exceeded)"
            logger.error(f"=== TIMEOUT ERROR === {error_msg}")
            logger.error(f"Timeout details: {str(e)}")
            logger.error(f"Server: {smtp_settings.server}:{smtp_settings.port}")
            return False, error_msg
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            logger.error(f"=== SMTP GENERAL ERROR === {error_msg}")
            logger.error(f"SMTP exception type: {type(e).__name__}")
            logger.error(f"Server: {smtp_settings.server}:{smtp_settings.port}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
            logger.error(f"=== UNEXPECTED ERROR === {error_msg}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Full exception details: {repr(e)}")
            return False, error_msg
        finally:
            if server:
                try:
                    logger.info("Closing SMTP connection...")
                    server.quit()
                    logger.info("SMTP connection closed successfully")
                except Exception as e:
                    logger.warning(f"Error closing SMTP connection: {str(e)}")
                    pass
    
    def create_alert_email(self, alert_items: List[AlertPreviewItem], alert_level: str) -> tuple[str, str]:
        """Create email content for alerts with enhanced styling matching the UI"""
        level_items = [item for item in alert_items if item.alert_level == alert_level]
        
        if not level_items:
            return "", ""
            
        level_title = alert_level.capitalize()
        subject = f"EOL {level_title} Alert - {len(level_items)} Systems Affected"
        
        # Determine color scheme based on alert level
        color_scheme = {
            'critical': {'bg': '#dc2626', 'light_bg': '#fef2f2', 'border': '#fecaca'},
            'warning': {'bg': '#d97706', 'light_bg': '#fffbeb', 'border': '#fed7aa'},
            'info': {'bg': '#2563eb', 'light_bg': '#eff6ff', 'border': '#bfdbfe'}
        }
        colors = color_scheme.get(alert_level, color_scheme['info'])
        
        # HTML email content with enhanced styling matching the UI
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    margin: 20px; 
                    line-height: 1.6; 
                    color: #333;
                }}
                .header {{ 
                    background: linear-gradient(135deg, {colors['bg']} 0%, #e67e22 50%, #d35400 100%); 
                    color: white; 
                    padding: 25px; 
                    border-radius: 12px; 
                    margin-bottom: 25px; 
                    text-align: center;
                }}
                .header h1 {{ 
                    margin: 0 0 10px 0; 
                    font-size: 28px; 
                    font-weight: 700;
                }}
                .header p {{ 
                    margin: 0; 
                    font-size: 16px; 
                    opacity: 0.95;
                }}
                .summary {{ 
                    background: #f8fafc; 
                    padding: 20px; 
                    border-radius: 8px; 
                    margin: 25px 0; 
                    text-align: center;
                }}
                .summary-value {{ 
                    font-size: 32px; 
                    font-weight: 700; 
                    color: {colors['bg']}; 
                    margin: 10px 0;
                }}
                .summary-label {{ 
                    font-size: 14px; 
                    color: #6b7280; 
                    text-transform: uppercase; 
                    letter-spacing: 0.5px;
                }}
                .alert-table {{ 
                    width: 100%; 
                    border-collapse: separate; 
                    border-spacing: 0; 
                    margin: 25px 0; 
                    border-radius: 8px; 
                    overflow: hidden; 
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                }}
                .alert-table th {{ 
                    background-color: #f1f5f9; 
                    color: #374151; 
                    padding: 15px 12px; 
                    text-align: left; 
                    font-weight: 600; 
                    font-size: 13px; 
                    text-transform: uppercase; 
                    letter-spacing: 0.5px;
                    border-bottom: 2px solid #e2e8f0;
                }}
                .alert-table td {{ 
                    padding: 12px; 
                    border-bottom: 1px solid #f1f5f9; 
                    vertical-align: middle;
                }}
                .alert-table tbody tr:nth-child(even) {{ 
                    background-color: #f9fafb; 
                }}
                .alert-table tbody tr:hover {{ 
                    background-color: #f3f4f6; 
                }}
                .eol-badge {{ 
                    background-color: {colors['light_bg']}; 
                    color: {colors['bg']}; 
                    border: 1px solid {colors['border']}; 
                    font-size: 11px; 
                    font-weight: 600; 
                    padding: 4px 8px; 
                    border-radius: 4px; 
                    text-transform: uppercase; 
                    letter-spacing: 0.5px; 
                    display: inline-block;
                }}
                .recommendations {{ 
                    background: #f8fafc; 
                    padding: 25px; 
                    border-radius: 8px; 
                    margin: 25px 0; 
                    border-left: 4px solid {colors['bg']};
                }}
                .recommendations h3 {{ 
                    margin-top: 0; 
                    color: #1f2937; 
                    font-size: 18px;
                }}
                .recommendations ul {{ 
                    margin: 15px 0; 
                    padding-left: 20px;
                }}
                .recommendations li {{ 
                    margin: 8px 0; 
                    color: #4b5563;
                }}
                .footer {{ 
                    margin-top: 30px; 
                    padding: 20px; 
                    background-color: #f1f5f9; 
                    border-radius: 8px; 
                    color: #6b7280; 
                    text-align: center; 
                    font-size: 14px;
                }}
                .footer em {{ 
                    font-style: italic; 
                }}
                .urgency-indicator {{
                    font-weight: bold;
                    color: {colors['bg']};
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🔔 EOL {level_title} Alert</h1>
                <p>The following {len(level_items)} systems are approaching their End-of-Life dates and require attention.</p>
            </div>
            
            <div class="summary">
                <div class="summary-value">{len(level_items)}</div>
                <div class="summary-label">{level_title} Alerts Triggered</div>
            </div>
            
            <table class="alert-table">
                <thead>
                    <tr>
                        <th>Computer Name</th>
                        <th>Operating System</th>
                        <th>Version</th>
                        <th>EOL Date</th>
                        <th>Days Until EOL</th>
                        <th>Alert Level</th>
                    </tr>
                </thead>
                <tbody>"""
        
        # Sort items by days until EOL (most urgent first)
        sorted_items = sorted(level_items, key=lambda x: x.days_until_eol)
        
        for item in sorted_items:
            urgency_class = "urgency-indicator" if item.days_until_eol <= 30 else ""
            html_content += f"""
                    <tr>
                        <td class="{urgency_class}"><strong>{item.computer}</strong></td>
                        <td>{item.os_name}</td>
                        <td>{item.version}</td>
                        <td>{item.eol_date.strftime('%Y-%m-%d')}</td>
                        <td class="{urgency_class}"><strong>{item.days_until_eol} days</strong></td>
                        <td><span class="eol-badge">{level_title}</span></td>
                    </tr>"""
        
        html_content += f"""
                </tbody>
            </table>
            
            <div class="recommendations">
                <h3>📋 Recommended Actions</h3>
                <ul>
                    <li><strong>Plan upgrade or migration</strong> for affected systems before EOL dates</li>
                    <li><strong>Review security implications</strong> of EOL systems and assess risks</li>
                    <li><strong>Contact vendors</strong> for extended support options if available</li>
                    <li><strong>Update system documentation</strong> and inventory records</li>
                    <li><strong>Schedule maintenance windows</strong> for critical system updates</li>
                </ul>
            </div>
            
            <div class="footer">
                <p><em>This alert was generated automatically by the EOL Management Platform.</em></p>
                <p>Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
            </div>
        </body>
        </html>
        """
        
        return subject, html_content
    
    async def send_alert_email(self, smtp_settings: SMTPSettings, recipients: List[str], 
                              subject: str, html_content: str) -> tuple[bool, str]:
        """Send alert email with detailed debugging"""
        server = None
        try:
            logger.info("=== SENDING ALERT EMAIL ===")
            logger.info(f"Recipients: {recipients}")
            logger.info(f"Subject: {subject}")
            logger.info(f"HTML content length: {len(html_content)} characters")
            logger.info(f"SMTP Server: {smtp_settings.server}:{smtp_settings.port}")
            logger.info(f"From: {smtp_settings.from_name} <{smtp_settings.from_email}>")
            
            if not smtp_settings.enabled or not recipients:
                logger.warning("Cannot send email - SMTP disabled or no recipients")
                return False, "SMTP disabled or no recipients"
                
            # Create message
            logger.info("Creating email message...")
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{smtp_settings.from_name} <{smtp_settings.from_email}>"
            msg['To'] = ', '.join(recipients)
            logger.info(f"Email headers set - To: {msg['To']}, From: {msg['From']}")
            
            # Add HTML content
            logger.info("Attaching HTML content to email...")
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            logger.info("HTML content attached successfully")
            
            # Create and connect to SMTP server
            logger.info("Establishing SMTP connection for email send...")
            if smtp_settings.use_ssl:
                logger.info("Creating SMTP_SSL connection for email send")
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(smtp_settings.server, smtp_settings.port, context=context)
                logger.info(f"SMTP_SSL connection established for email send")
            else:
                logger.info("Creating regular SMTP connection for email send")
                server = smtplib.SMTP(smtp_settings.server, smtp_settings.port)
                logger.info(f"SMTP connection established for email send")
                if smtp_settings.use_tls:
                    logger.info("Starting TLS for email send...")
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    logger.info("TLS enabled for email send")
            
            # Enable debug mode for detailed SMTP protocol logging
            server.set_debuglevel(1)
            logger.info("SMTP debug mode enabled for email send")
            
            # Authenticate if credentials provided
            if smtp_settings.username and smtp_settings.password:
                logger.info(f"Authenticating with SMTP server for email send: {smtp_settings.username}")
                server.login(smtp_settings.username, smtp_settings.password)
                logger.info("SMTP authentication successful for email send")
            else:
                logger.warning("No authentication credentials for email send")
            
            # Send the message
            logger.info(f"Sending email to {len(recipients)} recipients...")
            server.send_message(msg)
            logger.info(f"✅ Alert email sent successfully to {len(recipients)} recipients")
            logger.info("=== EMAIL SEND COMPLETED ===")
            return True, "Email sent successfully"
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "SMTP authentication failed during email send - check username/password"
            logger.error(f"=== EMAIL SEND AUTH ERROR === {error_msg}")
            logger.error(f"Auth error details: {str(e)}")
            logger.error(f"Username: {smtp_settings.username}")
            logger.error(f"Recipients: {recipients}")
            return False, error_msg
        except smtplib.SMTPConnectError as e:
            error_msg = "Could not connect to SMTP server during email send - check server/port"
            logger.error(f"=== EMAIL SEND CONNECT ERROR === {error_msg}")
            logger.error(f"Connect error details: {str(e)}")
            logger.error(f"Server: {smtp_settings.server}:{smtp_settings.port}")
            return False, error_msg
        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"SMTP server refused recipients: {str(e)}"
            logger.error(f"=== EMAIL SEND RECIPIENTS REFUSED === {error_msg}")
            logger.error(f"Refused recipients details: {e}")
            logger.error(f"Attempted recipients: {recipients}")
            return False, error_msg
        except smtplib.SMTPSenderRefused as e:
            error_msg = f"SMTP server refused sender: {str(e)}"
            logger.error(f"=== EMAIL SEND SENDER REFUSED === {error_msg}")
            logger.error(f"Sender refusal details: {e}")
            logger.error(f"From email: {smtp_settings.from_email}")
            return False, error_msg
        except smtplib.SMTPDataError as e:
            error_msg = f"SMTP data error during email send: {str(e)}"
            logger.error(f"=== EMAIL SEND DATA ERROR === {error_msg}")
            logger.error(f"Data error details: {e}")
            logger.error(f"Message size: {len(html_content)} chars")
            return False, error_msg
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error during email send: {str(e)}"
            logger.error(f"=== EMAIL SEND SMTP ERROR === {error_msg}")
            logger.error(f"SMTP exception type: {type(e).__name__}")
            logger.error(f"Exception details: {repr(e)}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            logger.error(f"=== EMAIL SEND UNEXPECTED ERROR === {error_msg}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Full exception: {repr(e)}")
            return False, error_msg
        finally:
            if server:
                try:
                    logger.info("Closing SMTP connection after email send...")
                    server.quit()
                    logger.info("SMTP connection closed after email send")
                except Exception as e:
                    logger.warning(f"Error closing SMTP connection after email send: {str(e)}")
                    pass

    async def save_notification_record(self, notification: NotificationRecord) -> bool:
        """
        Save a notification record to Cosmos DB for tracking and history.
        
        Args:
            notification: NotificationRecord to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            # Ensure notification container is available
            await self.initialize()
            if not self.notification_container:
                logger.error("Notification container not available")
                return False
            
            # Prepare document for Cosmos DB
            notification_dict = notification.dict()
            notification_dict['id'] = notification.id
            notification_dict['alert_type'] = notification.alert_type  # This is the partition key
            
            # Add metadata
            now = datetime.utcnow().isoformat() + "Z"
            notification_dict['created_at'] = notification_dict.get('created_at', now)
            notification_dict['updated_at'] = now
            
            # Save to Cosmos DB
            self.notification_container.create_item(notification_dict)
            logger.info(f"Notification record saved: {notification.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving notification record {notification.id}: {e}")
            return False

    async def get_notification_history(self, 
                                     alert_type: Optional[str] = None,
                                     limit: int = 100,
                                     offset: int = 0) -> NotificationHistory:
        """
        Retrieve notification history from Cosmos DB.
        
        Args:
            alert_type: Filter by alert type ('critical', 'warning', 'info') or None for all
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            NotificationHistory object with notifications and statistics
        """
        try:
            # Ensure notification container is available
            await self.initialize()
            if not self.notification_container:
                logger.warning("Notification container not available, returning empty history")
                return NotificationHistory()
            
            # Build query
            if alert_type:
                query = """
                    SELECT * FROM c 
                    WHERE c.alert_type = @alert_type 
                    ORDER BY c.timestamp DESC 
                    OFFSET @offset LIMIT @limit
                """
                params = [
                    {"name": "@alert_type", "value": alert_type},
                    {"name": "@offset", "value": offset},
                    {"name": "@limit", "value": limit}
                ]
            else:
                query = """
                    SELECT * FROM c 
                    ORDER BY c.timestamp DESC 
                    OFFSET @offset LIMIT @limit
                """
                params = [
                    {"name": "@offset", "value": offset},
                    {"name": "@limit", "value": limit}
                ]
            
            # Query notifications
            items = list(self.notification_container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))
            
            # Convert to NotificationRecord objects
            notifications = []
            for item in items:
                # Remove Cosmos DB metadata
                cosmos_metadata_fields = ['_rid', '_self', '_etag', '_attachments', '_ts']
                for field in cosmos_metadata_fields:
                    item.pop(field, None)
                
                try:
                    notification = NotificationRecord(**item)
                    notifications.append(notification)
                except Exception as e:
                    logger.warning(f"Error parsing notification record: {e}")
                    continue
            
            # Calculate statistics
            total_count = len(notifications)
            successful_count = len([n for n in notifications if n.status == 'success'])
            failed_count = len([n for n in notifications if n.status == 'failed'])
            
            last_notification_date = None
            if notifications:
                last_notification_date = notifications[0].timestamp  # Already sorted by timestamp DESC
            
            return NotificationHistory(
                notifications=notifications,
                total_count=total_count,
                successful_count=successful_count,
                failed_count=failed_count,
                last_notification_date=last_notification_date
            )
            
        except Exception as e:
            logger.error(f"Error retrieving notification history: {e}")
            return NotificationHistory()

    async def create_notification_record(self,
                                       alert_type: str,
                                       recipients: List[str],
                                       items_count: int,
                                       frequency: str,
                                       email_subject: Optional[str] = None) -> NotificationRecord:
        """
        Create a new notification record with a unique ID.
        
        Args:
            alert_type: Type of alert ('critical', 'warning', 'info')
            recipients: List of email recipients
            items_count: Number of alert items
            frequency: Frequency setting used
            email_subject: Subject line of the email
            
        Returns:
            NotificationRecord object ready to be updated with send results
        """
        import uuid
        
        now = datetime.utcnow().isoformat() + "Z"
        notification_id = f"{alert_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        return NotificationRecord(
            id=notification_id,
            timestamp=now,
            alert_type=alert_type,
            recipients=recipients,
            recipient_count=len(recipients),
            items_count=items_count,
            status="pending",  # Will be updated after send attempt
            frequency=frequency,
            email_subject=email_subject,
            created_at=now,
            updated_at=now
        )

    def should_send_notification(self, alert_type: str, frequency: str, last_sent: Optional[str] = None) -> bool:
        """
        Check if it's time to send a notification based on frequency and last sent time.
        This method should be called once daily at 9:00 AM UTC.
        
        Args:
            alert_type: 'critical', 'warning', or 'info'
            frequency: 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'
            last_sent: ISO format datetime string of when alert was last sent
            
        Returns:
            bool: True if notification should be sent today
        """
        try:
            now = datetime.utcnow()
            
            # Parse last sent date if provided
            if last_sent:
                try:
                    last_sent_date = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                    if last_sent_date.tzinfo is None:
                        last_sent_date = last_sent_date.replace(tzinfo=None)
                    else:
                        last_sent_date = last_sent_date.replace(tzinfo=None)
                except (ValueError, AttributeError):
                    logger.warning(f"Invalid last_sent date format: {last_sent}")
                    last_sent_date = None
            else:
                last_sent_date = None
            
            # Check frequency conditions
            if frequency == 'daily':
                # Send every day (if last sent was before today)
                if not last_sent_date:
                    return True
                return last_sent_date.date() < now.date()
                
            elif frequency == 'weekly':
                # Send every Monday (weekday 0)
                if now.weekday() != 0:  # Not Monday
                    return False
                if not last_sent_date:
                    return True
                # Check if last sent was before this Monday
                days_since_monday = now.weekday()
                this_monday = now.date() - timedelta(days=days_since_monday)
                return last_sent_date.date() < this_monday
                
            elif frequency == 'monthly':
                # Send on 1st of every month
                if now.day != 1:  # Not the 1st of the month
                    return False
                if not last_sent_date:
                    return True
                # Check if last sent was before this month's 1st
                first_of_this_month = now.replace(day=1).date()
                return last_sent_date.date() < first_of_this_month
                
            elif frequency == 'quarterly':
                # Send on 1st of Jan, Apr, Jul, Oct (months 1, 4, 7, 10)
                if now.month not in [1, 4, 7, 10] or now.day != 1:
                    return False
                if not last_sent_date:
                    return True
                # Check if last sent was before this quarter's start
                quarter_start = now.replace(day=1).date()
                return last_sent_date.date() < quarter_start
                
            elif frequency == 'yearly':
                # Send on January 1st only
                if now.month != 1 or now.day != 1:
                    return False
                if not last_sent_date:
                    return True
                # Check if last sent was before this year's January 1st
                jan_first = now.replace(month=1, day=1).date()
                return last_sent_date.date() < jan_first
                
            else:
                logger.warning(f"Unknown frequency: {frequency}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking notification schedule for {alert_type} ({frequency}): {e}")
            return False

    async def check_and_send_daily_notifications(self) -> Dict[str, Any]:
        """
        Daily check method to determine which notifications should be sent.
        Should be called once per day at 9:00 AM UTC.
        
        Returns:
            Dict with results of the daily check and any notifications sent
        """
        try:
            logger.info("=== DAILY NOTIFICATION CHECK STARTED ===")
            
            # Load current configuration
            config = await self.load_configuration()
            if not config.enabled:
                logger.info("Alert system is disabled, skipping daily check")
                return {"status": "disabled", "checks": 0, "sent": 0}
            
            if not config.smtp_settings.enabled:
                logger.info("SMTP is disabled, skipping daily check")
                return {"status": "smtp_disabled", "checks": 0, "sent": 0}
                
            if not config.email_recipients:
                logger.info("No email recipients configured, skipping daily check")
                return {"status": "no_recipients", "checks": 0, "sent": 0}
            
            # Get current time info for logging
            now = datetime.utcnow()
            logger.info(f"Daily check running at: {now.isoformat()} UTC")
            logger.info(f"Day of week: {now.strftime('%A')} (weekday {now.weekday()})")
            logger.info(f"Date: {now.strftime('%Y-%m-%d')} (day {now.day} of month {now.month})")
            
            results = {
                "status": "completed",
                "timestamp": now.isoformat() + "Z",
                "checks": 0,
                "sent": 0,
                "notifications": []
            }
            
            # Check each alert type
            alert_configs = {
                'critical': config.critical,
                'warning': config.warning, 
                'info': config.info
            }
            
            for alert_type, alert_config in alert_configs.items():
                results["checks"] += 1
                
                # Get last sent time for this alert type
                last_sent = config.last_sent.get(alert_type)
                
                # Check if notification should be sent
                should_send = self.should_send_notification(
                    alert_type, 
                    alert_config.frequency, 
                    last_sent
                )
                
                logger.info(f"Alert type '{alert_type}' (frequency: {alert_config.frequency})")
                logger.info(f"  Last sent: {last_sent or 'Never'}")
                logger.info(f"  Should send: {should_send}")
                
                if should_send:
                    # Create notification record for tracking
                    notification_record = await self.create_notification_record(
                        alert_type=alert_type,
                        recipients=config.email_recipients,
                        items_count=0,  # TODO: Get actual count from inventory data
                        frequency=alert_config.frequency,
                        email_subject=f"{alert_type.title()} EOL Alert - {now.strftime('%Y-%m-%d')}"
                    )
                    
                    # TODO: Here we would load inventory data and generate/send alerts
                    # For now, we'll simulate the notification and mark as successful
                    try:
                        # Simulate sending notification
                        logger.info(f"Sending {alert_type} notification (frequency: {alert_config.frequency}) to {len(config.email_recipients)} recipients")
                        
                        # Update notification record as successful
                        notification_record.status = "success"
                        notification_record.updated_at = now.isoformat() + "Z"
                        
                        # Save notification record to Cosmos DB
                        await self.save_notification_record(notification_record)
                        
                        # Update last_sent timestamp
                        config.last_sent[alert_type] = now.isoformat() + "Z"
                        
                        results["sent"] += 1
                        results["notifications"].append({
                            "id": notification_record.id,
                            "type": alert_type,
                            "frequency": alert_config.frequency,
                            "sent_at": now.isoformat() + "Z",
                            "recipients": len(config.email_recipients),
                            "status": "success"
                        })
                        
                    except Exception as send_error:
                        logger.error(f"Error sending {alert_type} notification: {send_error}")
                        
                        # Update notification record as failed
                        notification_record.status = "failed"
                        notification_record.error_message = str(send_error)
                        notification_record.updated_at = now.isoformat() + "Z"
                        
                        # Save failed notification record
                        await self.save_notification_record(notification_record)
                        
                        results["notifications"].append({
                            "id": notification_record.id,
                            "type": alert_type,
                            "frequency": alert_config.frequency,
                            "sent_at": now.isoformat() + "Z",
                            "recipients": len(config.email_recipients),
                            "status": "failed",
                            "error": str(send_error)
                        })
            
            # Save updated configuration with new last_sent timestamps
            if results["sent"] > 0:
                await self.save_configuration(config)
                logger.info(f"Updated last_sent timestamps for {results['sent']} notifications")
            
            logger.info(f"=== DAILY NOTIFICATION CHECK COMPLETED ===")
            logger.info(f"Checked {results['checks']} alert types, sent {results['sent']} notifications")
            
            return results
            
        except Exception as e:
            logger.error(f"Error during daily notification check: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "checks": 0,
                "sent": 0
            }

    def is_daily_check_time(self, target_hour: int = 9, target_minute: int = 0) -> bool:
        """
        Check if current UTC time matches the target time for daily checks.
        Default is 9:00 AM UTC.
        
        Args:
            target_hour: Hour in UTC (0-23)
            target_minute: Minute (0-59)
            
        Returns:
            bool: True if current time matches target time
        """
        try:
            now = datetime.utcnow()
            return now.hour == target_hour and now.minute == target_minute
        except Exception as e:
            logger.error(f"Error checking daily check time: {e}")
            return False

# Global alert manager instance
alert_manager = AlertManager()

async def initialize_alert_manager():
    """Initialize the alert manager and load configuration from Cosmos DB - following eol_cache pattern"""
    try:
        logger.info("Initializing alert manager...")
        
        # Initialize the alert manager first
        await alert_manager.initialize()
        
        # Load configuration
        config = await alert_manager.load_configuration()
        logger.info(f"Alert manager initialized with SMTP enabled: {config.smtp_settings.enabled}")
        return True
    except Exception as e:
        logger.error(f"Error initializing alert manager: {e}")
        return False
