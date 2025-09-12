"""
Centralized configuration management for the EOL Multi-Agent App
"""
import os
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
    subscription_id: str
    resource_group_name: str
    
    # Azure Cosmos DB
    cosmos_endpoint: str
    cosmos_database: str
    cosmos_container: str



@dataclass
class AppConfig:
    """Application configuration"""
    title: str = "EOL Multi-Agent App"
    version: str = "2.0.0"
    timeout: int = 60
    log_level: str = "INFO"
    debug_mode: bool = False


class ConfigManager:
    """Centralized configuration manager"""
    
    def __init__(self):
        self._azure_config: Optional[AzureConfig] = None
        self._app_config: Optional[AppConfig] = None
    
    @property
    def azure(self) -> AzureConfig:
        """Get Azure configuration"""
        if self._azure_config is None:
            self._azure_config = AzureConfig(
                aoai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                aoai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
                log_analytics_workspace_id=os.getenv("LOG_ANALYTICS_WORKSPACE_ID", ""),
                subscription_id=os.getenv("SUBSCRIPTION_ID", ""),
                resource_group_name=os.getenv("RESOURCE_GROUP_NAME", ""),
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
                title=os.getenv("APP_TITLE", "EOL Multi-Agent App"),
                version=os.getenv("APP_VERSION", "2.0.0"),
                timeout=int(os.getenv("APP_TIMEOUT", "60")),
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true"
            )
        return self._app_config
    
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
