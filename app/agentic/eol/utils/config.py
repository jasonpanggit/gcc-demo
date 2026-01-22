"""
Centralized configuration management for the EOL Multi-Agent App
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


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


class ConfigManager:
    """Centralized configuration manager"""
    
    def __init__(self):
        self._azure_config: Optional[AzureConfig] = None
        self._app_config: Optional[AppConfig] = None
        self._inventory_asst_config: Optional[InventoryAssistantConfig] = None
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
        
        return validation_results
    
    def get_environment_summary(self) -> Dict[str, str]:
        """Get a summary of environment configuration for logging"""
        return {
            "AZURE_OPENAI_ENDPOINT": "✅" if self.azure.aoai_endpoint else "❌",
            "LOG_ANALYTICS_WORKSPACE_ID": "✅" if self.azure.log_analytics_workspace_id else "❌",
            "AZURE_COSMOS_DB_ENDPOINT": "✅" if self.azure.cosmos_endpoint else "❌",
            "DEBUG_MODE": "✅" if self.app.debug_mode else "❌"
        }


# Global configuration instance
config = ConfigManager()
