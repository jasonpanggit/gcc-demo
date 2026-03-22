"""
Centralized configuration management for the EOL Multi-Agent App
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class AzureConfig:
    """Azure service configuration"""
    # Azure OpenAI
    aoai_endpoint: str
    aoai_deployment: str

    # Azure Log Analytics
    log_analytics_workspace_id: str
    tenant_id: str
    subscription_id: str
    resource_group_name: str



@dataclass
class AppConfig:
    """Application configuration"""
    title: str = "Azure Agentic Platform"
    version: str = "1.0.0"
    timeout: int = 60
    log_level: str = "INFO"
    debug_mode: bool = False
    base_url: str = field(default_factory=lambda: os.getenv("APP_BASE_URL", "http://localhost:8000"))
    asset_version: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))


@dataclass
class InventoryAssistantConfig:
    """Inventory assistant experience configuration"""
    enabled: bool = True
    provider: str = "agent-framework"
    default_timeout: int = 150


@dataclass
class PatchManagementConfig:
    """Patch management configuration for Azure VMs and Arc-enabled servers.

    Controls behavior for patch assessment, installation, and compliance reporting
    via the patch management orchestrator/agent/MCP architecture.
    """

    # Feature flags
    use_orchestrator: bool = field(
        default_factory=lambda: os.getenv("PATCH_USE_ORCHESTRATOR", "true").lower() == "true"
    )
    enable_streaming: bool = field(
        default_factory=lambda: os.getenv("PATCH_ENABLE_STREAMING", "true").lower() == "true"
    )

    # Operation timeouts (seconds)
    assessment_timeout: int = field(
        default_factory=lambda: int(os.getenv("PATCH_ASSESSMENT_TIMEOUT", "300"))
    )
    installation_timeout: int = field(
        default_factory=lambda: int(os.getenv("PATCH_INSTALLATION_TIMEOUT", "600"))
    )
    list_timeout: int = field(
        default_factory=lambda: int(os.getenv("PATCH_LIST_TIMEOUT", "180"))
    )

    # Batch processing
    batch_size: int = field(
        default_factory=lambda: int(os.getenv("PATCH_BATCH_SIZE", "20"))
    )
    parallel_limit: int = field(
        default_factory=lambda: int(os.getenv("PATCH_PARALLEL_LIMIT", "5"))
    )

    # Compliance thresholds
    critical_patch_age_days: int = field(
        default_factory=lambda: int(os.getenv("PATCH_CRITICAL_AGE_DAYS", "7"))
    )
    important_patch_age_days: int = field(
        default_factory=lambda: int(os.getenv("PATCH_IMPORTANT_AGE_DAYS", "30"))
    )

    # Caching
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("PATCH_CACHE_TTL", "300"))
    )


@dataclass
class InventoryConfig:
    """Resource inventory discovery and caching configuration"""

    # Feature flags
    enable_inventory: bool = field(
        default_factory=lambda: os.getenv("INVENTORY_ENABLE", "true").lower() == "true"
    )
    startup_blocking: bool = False  # Non-blocking startup

    # Cache TTL settings (seconds)
    default_l1_ttl: int = 300  # 5 minutes
    default_l2_ttl: int = 3600  # 1 hour
    resource_type_ttl_overrides: Dict[str, int] = field(default_factory=lambda: {
        "Microsoft.Compute/virtualMachines": 1800,       # 30 min
        "Microsoft.Network/virtualNetworks": 86400,      # 24 hr
        "Microsoft.Storage/storageAccounts": 3600,       # 1 hr
        "Microsoft.Web/sites": 1800,                     # 30 min
        "Microsoft.Sql/servers": 7200,                   # 2 hr
    })

    # Discovery settings
    full_scan_schedule_cron: str = "0 2 * * *"  # Daily at 2 AM
    incremental_scan_interval_minutes: int = 5
    relationship_depth: int = 2

    # Incremental logic
    detect_created_resources: bool = True
    detect_modified_resources: bool = True
    detect_deleted_resources: bool = True

    # Security
    filter_sensitive_tags: bool = True
    sensitive_tag_keywords: List[str] = field(default_factory=lambda: [
        "password", "secret", "token", "key", "credential",
        "apikey", "api_key", "connectionstring", "connection_string"
    ])

    # Property storage
    store_selective_properties: bool = True
    stored_properties: List[str] = field(default_factory=lambda: [
        "provisioningState", "location", "sku", "kind", "type",
        "vmSize", "powerState", "osType", "availabilityZone",
        "status", "state", "tier", "replicationStatus"
    ])

    # Error handling
    skip_failed_subscriptions: bool = True
    max_retry_attempts: int = 3



@dataclass
class CVEDataConfig:
    """CVE (Common Vulnerabilities and Exposures) data configuration.

    Controls CVE data fetching from multiple sources: CVE.org, NVD, vendor feeds.
    """

    # API endpoints
    cve_org_base_url: str = "https://cveawg.mitre.org/api"
    nvd_base_url: str = "https://services.nvd.nist.gov/rest/json"
    redhat_base_url: str = "https://access.redhat.com/hydra/rest/securitydata"
    ubuntu_base_url: str = "https://ubuntu.com/security"
    msrc_base_url: str = "https://api.msrc.microsoft.com/cvrf/v3.0"
    github_graphql_url: str = "https://api.github.com/graphql"

    # API keys (optional for some sources)
    cve_org_api_org: str = field(default_factory=lambda: os.getenv("CVE_API_ORG", ""))
    nvd_api_key: str = field(default_factory=lambda: os.getenv("NVD_API_KEY", ""))
    msrc_api_key: str = field(default_factory=lambda: os.getenv("MSRC_API_KEY", ""))
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))

    # Request configuration
    request_timeout: int = 30  # seconds
    max_retries: int = 3
    rate_limit_per_second: float = 5.0  # Default rate limit

    # Cache configuration
    l1_cache_size: int = 1000  # Max CVEs in memory
    l1_cache_ttl_seconds: int = 3600  # 1 hour

    # Source priority for conflict resolution (lower number = higher priority)
    source_priority: Dict[str, int] = field(default_factory=lambda: {
        "nvd": 1,        # Highest priority for CVSS scores
        "cve_org": 2,    # Authoritative for CVE metadata
        "github": 3,     # Good for software package CVEs
        "redhat": 4,     # Enterprise Linux focus
        "ubuntu": 4,     # Same priority as RedHat
        "microsoft": 4   # Windows/Office focus
    })


@dataclass
class CVESyncConfig:
    """CVE synchronization scheduler configuration.

    Controls periodic CVE database refresh jobs using APScheduler.
    """

    # Feature flag
    enable_cve_sync: bool = field(
        default_factory=lambda: os.getenv("CVE_SYNC_ENABLED", "true").lower() == "true"
    )

    # Sync schedules
    full_sync_schedule_cron: str = field(
        default_factory=lambda: os.getenv("CVE_SYNC_CRON", "0 2 * * *")  # Daily at 2 AM
    )
    incremental_sync_interval_hours: int = field(
        default_factory=lambda: int(os.getenv("CVE_SYNC_INTERVAL_HOURS", "6"))
    )

    # Sync behavior
    sync_lookback_days: int = field(
        default_factory=lambda: int(os.getenv("CVE_SYNC_LOOKBACK_DAYS", "7"))
    )

    # Job limits
    max_cves_per_sync: int = field(
        default_factory=lambda: int(os.getenv("CVE_SYNC_MAX_CVES", "10000"))
    )


@dataclass
class CVEScannerConfig:
    """CVE scanner configuration for inventory vulnerability scanning.

    Controls VM discovery, package extraction, and CVE matching behavior.
    """

    # Feature flag
    enable_scanner: bool = field(
        default_factory=lambda: os.getenv("CVE_SCANNER_ENABLED", "true").lower() == "true"
    )

    # Scan limits
    scan_timeout_minutes: int = field(
        default_factory=lambda: int(os.getenv("CVE_SCAN_TIMEOUT_MINUTES", "30"))
    )
    max_vms_per_scan: int = field(
        default_factory=lambda: int(os.getenv("CVE_SCAN_MAX_VMS", "1000"))
    )
    vm_scan_concurrency: int = field(
        default_factory=lambda: int(os.getenv("CVE_SCAN_VM_CONCURRENCY", "6"))
    )

    # Package extraction
    package_extraction_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("CVE_SCAN_PACKAGE_TIMEOUT", "10"))
    )


@dataclass
class CVEMonitoringConfig:
    """CVE monitoring and alerting configuration.

    Controls scheduled CVE scanning, delta detection, and multi-channel alerting.

    Environment variables:
        ENABLE_CVE_MONITORING: Enable scheduled scanning (default: true)
        CVE_SCAN_SCHEDULE_CRON: Cron schedule for scans (default: "0 9 * * *" - 9 AM daily)
        CVE_ALERT_SEVERITY_THRESHOLD: Minimum severity to alert (HIGH or CRITICAL, default: HIGH)
        CVE_ALERT_ON_NEW_CVES: Alert on new CVE detection (default: true)
        CVE_ALERT_ON_SEVERITY_INCREASE: Alert on severity increases (default: true)
        CVE_ENABLE_ESCALATION: Enable escalation for unacknowledged alerts (default: true)
        CVE_ESCALATION_TIMEOUT_HOURS: Hours before escalation (default: 24)
        CVE_MAX_ALERTS_PER_BATCH: Max CVEs per alert batch (default: 50)
        CVE_SCAN_TIMEOUT_SECONDS: Scan completion timeout (default: 600)
    """

    # Master switch
    enable_cve_monitoring: bool = field(
        default_factory=lambda: os.getenv("ENABLE_CVE_MONITORING", "true").lower() == "true"
    )

    # Scan schedule (cron expression)
    scan_schedule_cron: str = field(
        default_factory=lambda: os.getenv("CVE_SCAN_SCHEDULE_CRON", "0 9 * * *")
    )

    # Alert filters
    alert_severity_threshold: str = field(
        default_factory=lambda: os.getenv("CVE_ALERT_SEVERITY_THRESHOLD", "HIGH")
    )

    alert_on_new_cves: bool = field(
        default_factory=lambda: os.getenv("CVE_ALERT_ON_NEW_CVES", "true").lower() == "true"
    )

    alert_on_severity_increase: bool = field(
        default_factory=lambda: os.getenv("CVE_ALERT_ON_SEVERITY_INCREASE", "true").lower() == "true"
    )

    # Escalation
    enable_escalation: bool = field(
        default_factory=lambda: os.getenv("CVE_ENABLE_ESCALATION", "true").lower() == "true"
    )

    escalation_timeout_hours: int = field(
        default_factory=lambda: int(os.getenv("CVE_ESCALATION_TIMEOUT_HOURS", "24"))
    )

    # Performance
    max_alerts_per_batch: int = field(
        default_factory=lambda: int(os.getenv("CVE_MAX_ALERTS_PER_BATCH", "50"))
    )

    scan_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("CVE_SCAN_TIMEOUT_SECONDS", "600"))
    )

    def __post_init__(self):
        """Validate configuration values"""
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        if self.alert_severity_threshold not in valid_severities:
            raise ValueError(
                f"Invalid severity threshold: {self.alert_severity_threshold}. "
                f"Must be one of {valid_severities}"
            )

        if self.escalation_timeout_hours < 1:
            raise ValueError("Escalation timeout must be at least 1 hour")


# ============================================================================
# Phase 2 Day 6: Centralized Timeout Configuration
# ============================================================================

@dataclass
class TimeoutConfig:
    """Centralized timeout configuration for all components.

    Provides consistent timeout values across orchestrators, agents, MCP tools,
    and Azure SDK calls. All values in seconds (float for sub-second precision).

    Environment variables:
        ORCHESTRATOR_TIMEOUT: Overall orchestrator timeout (default: 30.0s)
        AGENT_TIMEOUT: Individual agent timeout (default: 10.0s)
        MCP_TOOL_TIMEOUT: MCP tool execution timeout (default: 5.0s)
        AZURE_SDK_TIMEOUT: Azure SDK call timeout (default: 15.0s)
        HTTP_CLIENT_TIMEOUT: Generic HTTP client timeout (default: 20.0s)
        DB_QUERY_TIMEOUT: Database query timeout (default: 10.0s)
    """

    # Orchestrator-level timeouts
    orchestrator_timeout: float = field(
        default_factory=lambda: float(os.getenv("ORCHESTRATOR_TIMEOUT", "30.0"))
    )

    # Agent-level timeouts
    agent_timeout: float = field(
        default_factory=lambda: float(os.getenv("AGENT_TIMEOUT", "10.0"))
    )

    # MCP tool timeouts
    mcp_tool_timeout: float = field(
        default_factory=lambda: float(os.getenv("MCP_TOOL_TIMEOUT", "5.0"))
    )

    # Azure SDK timeouts
    azure_sdk_timeout: float = field(
        default_factory=lambda: float(os.getenv("AZURE_SDK_TIMEOUT", "15.0"))
    )

    # HTTP client timeouts
    http_client_timeout: float = field(
        default_factory=lambda: float(os.getenv("HTTP_CLIENT_TIMEOUT", "20.0"))
    )

    # Database query timeouts
    db_query_timeout: float = field(
        default_factory=lambda: float(os.getenv("DB_QUERY_TIMEOUT", "10.0"))
    )

    @classmethod
    def from_env(cls) -> "TimeoutConfig":
        """Create TimeoutConfig from environment variables."""
        return cls()

    def get_all_timeouts(self) -> Dict[str, float]:
        """Get all timeout values as a dictionary."""
        return {
            "orchestrator_timeout": self.orchestrator_timeout,
            "agent_timeout": self.agent_timeout,
            "mcp_tool_timeout": self.mcp_tool_timeout,
            "azure_sdk_timeout": self.azure_sdk_timeout,
            "http_client_timeout": self.http_client_timeout,
            "db_query_timeout": self.db_query_timeout,
        }


@dataclass
class EolConfig:
    """EOL orchestrator configuration.

    Controls confidence scoring behavior, shadow mode, and pipeline settings.

    Environment variables:
        EOL_SHADOW_SCORING: Enable shadow scoring (default: true)
        EOL_PIPELINE_CONFIDENCE_THRESHOLD: Minimum confidence for early pipeline termination (default: 0.80)
    """
    shadow_scoring: bool = field(
        default_factory=lambda: os.getenv("EOL_SHADOW_SCORING", "true").lower() == "true"
    )
    pipeline_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("EOL_PIPELINE_CONFIDENCE_THRESHOLD", "0.80"))
    )


class ConfigManager:
    """Centralized configuration manager"""

    def __init__(self):
        self._azure_config: Optional[AzureConfig] = None
        self._app_config: Optional[AppConfig] = None
        self._inventory_asst_config: Optional[InventoryAssistantConfig] = None
        self._inventory_config: Optional[InventoryConfig] = None
        self._cve_data_config: Optional[CVEDataConfig] = None
        self._cve_sync_config: Optional[CVESyncConfig] = None
        self._cve_scanner_config: Optional[CVEScannerConfig] = None
        self._cve_monitoring_config: Optional[CVEMonitoringConfig] = None
        self._timeout_config: Optional[TimeoutConfig] = None
        self._eol_config: Optional[EolConfig] = None
        self._appsettings_cache: Optional[Dict[str, Any]] = None

    def _load_appsettings(self) -> Dict[str, Any]:
        if self._appsettings_cache is not None:
            return self._appsettings_cache

        settings_path = os.getenv("APPSETTINGS_PATH")
        if not settings_path:
            settings_path = str(Path(__file__).resolve().parents[1] / "deploy" / "appsettings.json")

        try:
            if Path(settings_path).is_file():
                with open(settings_path, "r", encoding="utf-8") as handle:
                    self._appsettings_cache = json.load(handle)
            else:
                self._appsettings_cache = {}
        except Exception:
            self._appsettings_cache = {}

        return self._appsettings_cache

    def _get_appsettings_value(self, *keys: str) -> Optional[str]:
        data: Any = self._load_appsettings()
        for key in keys:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        if data is None:
            return None
        return str(data)
    
    @property
    def azure(self) -> AzureConfig:
        """Get Azure configuration"""
        if self._azure_config is None:
            app_subscription = self._get_appsettings_value("Azure", "SubscriptionId")
            app_tenant = self._get_appsettings_value("Azure", "TenantId")
            app_resource_group = self._get_appsettings_value("Azure", "ResourceGroup")

            self._azure_config = AzureConfig(
                aoai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                aoai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
                log_analytics_workspace_id=os.getenv("LOG_ANALYTICS_WORKSPACE_ID", ""),
                tenant_id=os.getenv("AZURE_TENANT_ID", os.getenv("TENANT_ID", app_tenant or "")),
                subscription_id=os.getenv("SUBSCRIPTION_ID", app_subscription or ""),
                resource_group_name=os.getenv("RESOURCE_GROUP_NAME", app_resource_group or ""),
            )
        return self._azure_config
    
    @property
    def app(self) -> AppConfig:
        """Get application configuration"""
        if self._app_config is None:
            self._app_config = AppConfig(
                title=os.getenv("APP_TITLE", "Azure Agentic Platform"),
                version=os.getenv("APP_VERSION", "1.0.0"),
                timeout=int(os.getenv("APP_TIMEOUT", "60")),
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true"
            )
        return self._app_config

    @property
    def inventory_assistant(self) -> InventoryAssistantConfig:
        """Get inventory assistant configuration"""
        if self._inventory_asst_config is None:
            enabled = os.getenv("INVENTORY_ASSISTANT_ENABLED")
            provider = os.getenv("INVENTORY_ASSISTANT_PROVIDER")
            default_timeout = os.getenv("INVENTORY_ASSISTANT_DEFAULT_TIMEOUT")

            # Fallback to legacy environment variables if new ones are unset
            if enabled is None:
                enabled = os.getenv("CHAT_ENABLED", "true")
            if provider is None:
                provider = os.getenv("CHAT_PROVIDER", "agent-framework")
            if default_timeout is None:
                default_timeout = os.getenv("CHAT_DEFAULT_TIMEOUT", "150")

            self._inventory_asst_config = InventoryAssistantConfig(
                enabled=str(enabled).lower() == "true",
                provider=str(provider),
                default_timeout=int(str(default_timeout)),
            )
        return self._inventory_asst_config

    @property
    def patch_management(self) -> PatchManagementConfig:
        """Get patch management configuration"""
        if not hasattr(self, '_patch_mgmt_config'):
            self._patch_mgmt_config = None
        if self._patch_mgmt_config is None:
            self._patch_mgmt_config = PatchManagementConfig()
        return self._patch_mgmt_config

    @property
    def inventory(self) -> InventoryConfig:
        """Get resource inventory configuration"""
        if self._inventory_config is None:
            # Load from environment with defaults from the dataclass
            inv = InventoryConfig()

            # Override from environment variables where applicable
            l1_ttl = os.getenv("INVENTORY_DEFAULT_L1_TTL")
            if l1_ttl is not None:
                inv.default_l1_ttl = int(l1_ttl)

            l2_ttl = os.getenv("INVENTORY_DEFAULT_L2_TTL")
            if l2_ttl is not None:
                inv.default_l2_ttl = int(l2_ttl)

            cron = os.getenv("INVENTORY_FULL_SCAN_CRON")
            if cron is not None:
                inv.full_scan_schedule_cron = cron

            inc_interval = os.getenv("INVENTORY_INCREMENTAL_INTERVAL_MINUTES")
            if inc_interval is not None:
                inv.incremental_scan_interval_minutes = int(inc_interval)

            rel_depth = os.getenv("INVENTORY_RELATIONSHIP_DEPTH")
            if rel_depth is not None:
                inv.relationship_depth = int(rel_depth)

            max_retries = os.getenv("INVENTORY_MAX_RETRY_ATTEMPTS")
            if max_retries is not None:
                inv.max_retry_attempts = int(max_retries)

            self._inventory_config = inv
        return self._inventory_config

    @property
    def cve_sync(self) -> CVESyncConfig:
        """Get CVE sync scheduler configuration"""
        if self._cve_sync_config is None:
            self._cve_sync_config = CVESyncConfig()
        return self._cve_sync_config

    @property
    def cve_data(self) -> CVEDataConfig:
        """Get CVE data source/cache configuration."""
        if self._cve_data_config is None:
            self._cve_data_config = CVEDataConfig()
        return self._cve_data_config

    @property
    def cve_scanner(self) -> CVEScannerConfig:
        """Get CVE scanner configuration (Phase 5)"""
        if self._cve_scanner_config is None:
            self._cve_scanner_config = CVEScannerConfig()
        return self._cve_scanner_config

    @property
    def cve_monitoring(self) -> CVEMonitoringConfig:
        """Get CVE monitoring configuration (Phase 9)"""
        if self._cve_monitoring_config is None:
            self._cve_monitoring_config = CVEMonitoringConfig()
        return self._cve_monitoring_config

    @property
    def timeouts(self) -> TimeoutConfig:
        """Get centralized timeout configuration (Phase 2, Day 6)"""
        if self._timeout_config is None:
            self._timeout_config = TimeoutConfig.from_env()
        return self._timeout_config

    @property
    def eol(self) -> EolConfig:
        """Get EOL orchestrator configuration"""
        if self._eol_config is None:
            self._eol_config = EolConfig()
        return self._eol_config

    def validate_config(self) -> Dict[str, Any]:
        """
        Validate configuration and return status

        Returns:
            Dictionary containing validation results
        """
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "services": {}
        }

        # Check required Azure services
        azure_services = {
            "aoai_endpoint": self.azure.aoai_endpoint,
            "log_analytics_workspace_id": self.azure.log_analytics_workspace_id,
        }

        # Check optional services
        optional_services = {
            "subscription_id": self.azure.subscription_id,
            "resource_group_name": self.azure.resource_group_name,
        }

        for service, value in optional_services.items():
            is_configured = bool(value)
            validation_results["services"][service] = is_configured

            if not is_configured:
                warning_msg = f"Optional service not configured: {service}"
                validation_results["warnings"].append(warning_msg)

        # Check resource inventory configuration
        inv = self.inventory
        validation_results["services"]["inventory_enabled"] = inv.enable_inventory
        if inv.enable_inventory:
            validation_results["services"]["inventory_startup_blocking"] = inv.startup_blocking

        return validation_results
    
    def get_environment_summary(self) -> Dict[str, str]:
        """Get a summary of environment configuration for logging"""
        return {
            "AZURE_OPENAI_ENDPOINT": "✅" if self.azure.aoai_endpoint else "❌",
            "LOG_ANALYTICS_WORKSPACE_ID": "✅" if self.azure.log_analytics_workspace_id else "❌",
            "DEBUG_MODE": "✅" if self.app.debug_mode else "❌",
            "INVENTORY_ENABLED": "✅" if self.inventory.enable_inventory else "❌",
            "INVENTORY_STARTUP_BLOCKING": "✅" if self.inventory.startup_blocking else "❌",
        }


# Global configuration instance
config = ConfigManager()

# Compatibility alias used by some modules
def get_config() -> ConfigManager:
    return config
