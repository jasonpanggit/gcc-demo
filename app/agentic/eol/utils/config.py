"""
Centralized configuration management for the EOL Multi-Agent App
"""
import json
import os
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
    
    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_database: str
    cosmos_container: str



@dataclass
class AppConfig:
    """Application configuration"""
    title: str = "Azure Agentic Platform"
    version: str = "1.0.0"
    timeout: int = 60
    log_level: str = "INFO"
    debug_mode: bool = False


@dataclass
class InventoryAssistantConfig:
    """Inventory assistant experience configuration"""
    enabled: bool = True
    provider: str = "agent-framework"
    default_timeout: int = 150


@dataclass
class AzureAISREConfig:
    """Azure AI SRE Agent configuration"""
    agent_name: str
    agent_id: Optional[str]
    project_endpoint: Optional[str]
    enabled: bool


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

    # Cosmos DB
    cosmos_container_inventory: str = "resource_inventory"
    cosmos_container_metadata: str = "resource_inventory_metadata"
    cosmos_autoscale_min_ru: int = 400
    cosmos_autoscale_max_ru: int = 4000


class ConfigManager:
    """Centralized configuration manager"""

    def __init__(self):
        self._azure_config: Optional[AzureConfig] = None
        self._app_config: Optional[AppConfig] = None
        self._inventory_asst_config: Optional[InventoryAssistantConfig] = None
        self._azure_ai_sre_config: Optional[AzureAISREConfig] = None
        self._inventory_config: Optional[InventoryConfig] = None
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
                cosmos_endpoint=os.getenv("AZURE_COSMOS_DB_ENDPOINT", ""),
                cosmos_database=os.getenv("AZURE_COSMOS_DB_DATABASE", ""),
                cosmos_container=os.getenv("AZURE_COSMOS_DB_CONTAINER", "")
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
    def azure_ai_sre(self) -> AzureAISREConfig:
        """Get Azure AI SRE agent configuration"""
        if self._azure_ai_sre_config is None:
            self._azure_ai_sre_config = AzureAISREConfig(
                agent_name=os.getenv("AZURE_AI_SRE_AGENT_NAME", "gccsreagent"),
                agent_id=os.getenv("AZURE_AI_SRE_AGENT_ID"),
                project_endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
                enabled=os.getenv("AZURE_AI_SRE_ENABLED", "true").lower() == "true"
            )
        return self._azure_ai_sre_config

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

            # Cosmos DB container overrides
            container_inv = os.getenv("INVENTORY_COSMOS_CONTAINER")
            if container_inv is not None:
                inv.cosmos_container_inventory = container_inv

            container_meta = os.getenv("INVENTORY_COSMOS_METADATA_CONTAINER")
            if container_meta is not None:
                inv.cosmos_container_metadata = container_meta

            min_ru = os.getenv("INVENTORY_COSMOS_AUTOSCALE_MIN_RU")
            if min_ru is not None:
                inv.cosmos_autoscale_min_ru = int(min_ru)

            max_ru = os.getenv("INVENTORY_COSMOS_AUTOSCALE_MAX_RU")
            if max_ru is not None:
                inv.cosmos_autoscale_max_ru = int(max_ru)

            self._inventory_config = inv
        return self._inventory_config

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
        
        # Check required Azure services (Cosmos DB now added for caching)
        azure_services = {
            "aoai_endpoint": self.azure.aoai_endpoint,
            "log_analytics_workspace_id": self.azure.log_analytics_workspace_id,
        }
        
        # Check optional Cosmos DB service for caching
        optional_services = {
            "subscription_id": self.azure.subscription_id,
            "resource_group_name": self.azure.resource_group_name,
            "cosmos_endpoint": self.azure.cosmos_endpoint
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
            if not self.azure.cosmos_endpoint:
                validation_results["warnings"].append(
                    "Resource inventory enabled but Cosmos DB endpoint not configured"
                )
            validation_results["services"]["inventory_startup_blocking"] = inv.startup_blocking

        return validation_results
    
    def get_environment_summary(self) -> Dict[str, str]:
        """Get a summary of environment configuration for logging"""
        return {
            "AZURE_OPENAI_ENDPOINT": "✅" if self.azure.aoai_endpoint else "❌",
            "LOG_ANALYTICS_WORKSPACE_ID": "✅" if self.azure.log_analytics_workspace_id else "❌",
            "AZURE_COSMOS_DB_ENDPOINT": "✅" if self.azure.cosmos_endpoint else "❌",
            "DEBUG_MODE": "✅" if self.app.debug_mode else "❌",
            "INVENTORY_ENABLED": "✅" if self.inventory.enable_inventory else "❌",
            "INVENTORY_STARTUP_BLOCKING": "✅" if self.inventory.startup_blocking else "❌",
        }


# Global configuration instance
config = ConfigManager()
