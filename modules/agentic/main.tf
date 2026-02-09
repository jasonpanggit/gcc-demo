# ============================================================================
# AGENTIC APP MODULE - Container App + AOAI with Private Endpoints
# ============================================================================

# terraform {
#   required_providers {
#     azurerm = {
#       source  = "hashicorp/azurerm"
#       version = ">= 3.100.0"
#     }
#   }
# }

# Get current Azure context
data "azurerm_client_config" "current" {}

# App Service Plan
resource "azurerm_service_plan" "plan" {
  count               = var.deploy_agentic_app ? 1 : 0
  name                = "asp-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  tags                = var.tags
}

# Storage Account for App Content (containerized image not used here)
resource "azurerm_storage_account" "sa" {
  count                    = var.deploy_agentic_app ? 1 : 0
  name                     = replace("sa${var.project_name}${var.environment}agentic", "-", "")
  location                 = var.location
  resource_group_name      = var.resource_group_name
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = var.tags
}

# App Insights (for simple telemetry)
resource "azurerm_application_insights" "appi" {
  count               = var.deploy_agentic_app ? 1 : 0
  name                = "appi-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
  workspace_id        = var.workspace_resource_id
  tags                = var.tags
}

# Azure OpenAI
resource "azurerm_cognitive_account" "aoai" {
  count                         = var.deploy_agentic_app && var.deploy_aoai ? 1 : 0
  name                          = coalesce(var.aoai_name, "aoai-${var.agentic_app_name}-${var.project_name}-${var.environment}")
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "OpenAI"
  sku_name                      = var.aoai_sku_name
  custom_subdomain_name         = "${var.project_name}-${var.environment}-${var.agentic_app_name}"
  public_network_access_enabled = !var.deploy_agentic_private_endpoints
  tags                          = var.tags

  # Network ACLs for private endpoint access
  dynamic "network_acls" {
    for_each = var.deploy_agentic_private_endpoints ? [1] : []
    content {
      default_action = "Deny"
      ip_rules       = []
      virtual_network_rules {
        subnet_id = coalesce(var.nongen_appsvc_integration_subnet_id, var.nongen_app_subnet_id)
      }
    }
  }
}

# ============================================================================
# COSMOS DB for EOL Response Caching
# ============================================================================

# Azure Cosmos DB Account
resource "azurerm_cosmosdb_account" "cosmos" {
  count                         = var.deploy_agentic_app && var.deploy_cosmos_db ? 1 : 0
  name                          = coalesce(var.cosmos_db_name, "cosmos-${var.agentic_app_name}-${var.project_name}-${var.environment}")
  location                      = var.location
  resource_group_name           = var.resource_group_name
  offer_type                    = var.cosmos_db_offer_type
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = !var.deploy_agentic_private_endpoints
  
  # Serverless or provisioned throughput
  capabilities {
    name = var.cosmos_db_serverless ? "EnableServerless" : "EnableAggregationPipeline"
  }

  dynamic "capabilities" {
    for_each = var.cosmos_db_serverless ? [] : [1]
    content {
      name = "EnableAggregationPipeline"
    }
  }

  consistency_policy {
    consistency_level       = var.cosmos_db_consistency_level
    max_interval_in_seconds = var.cosmos_db_consistency_level == "BoundedStaleness" ? 86400 : null
    max_staleness_prefix    = var.cosmos_db_consistency_level == "BoundedStaleness" ? 100000 : null
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  # Optional additional geo-location for disaster recovery
  dynamic "geo_location" {
    for_each = var.cosmos_db_geo_location != null ? [1] : []
    content {
      location          = var.cosmos_db_geo_location
      failover_priority = 1
    }
  }

  # Automatic failover configuration
  automatic_failover_enabled = var.cosmos_db_automatic_failover

  tags = var.tags
}

# Cosmos DB Database
resource "azurerm_cosmosdb_sql_database" "database" {
  count               = var.deploy_agentic_app && var.deploy_cosmos_db ? 1 : 0
  name                = var.cosmos_db_database_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos[0].name
}

# Cosmos DB Container for EOL Response Caching
resource "azurerm_cosmosdb_sql_container" "container" {
  count               = var.deploy_agentic_app && var.deploy_cosmos_db ? 1 : 0
  name                = var.cosmos_db_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos[0].name
  database_name       = azurerm_cosmosdb_sql_database.database[0].name
  partition_key_paths = ["/cache_key"]
  partition_key_kind  = "Hash"
  
  # TTL for automatic cleanup of expired cache entries
  default_ttl = 2592000  # 30 days in seconds

  # Throughput configuration (only for non-serverless)
  throughput = var.cosmos_db_serverless ? null : var.cosmos_db_throughput

  # Indexing policy optimized for cache queries
  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }

    # Optimized paths for EOL cache queries
    included_path {
      path = "/cache_key/?"
    }

    included_path {
      path = "/software_name/?"
    }

    included_path {
      path = "/agent_name/?"
    }

    included_path {
      path = "/expires_at/?"
    }
    
    included_path {
      path = "/verified/?"
    }
    
    included_path {
      path = "/confidence_level/?"
    }
    
    included_path {
      path = "/created_at/?"
    }
    
    included_path {
      path = "/marked_as_failed/?"
    }

    # Composite indexes to support ORDER BY queries
    composite_index {
      index {
        path  = "/cache_key"
        order = "ascending"
      }
      index {
        path  = "/verified"
        order = "descending"
      }
      index {
        path  = "/confidence_level"
        order = "descending"
      }
      index {
        path  = "/created_at"
        order = "descending"
      }
    }
    
    composite_index {
      index {
        path  = "/cache_key"
        order = "ascending"
      }
      index {
        path  = "/marked_as_failed"
        order = "ascending"
      }
      index {
        path  = "/verified"
        order = "descending"
      }
    }
    
    composite_index {
      index {
        path  = "/agent_name"
        order = "ascending"
      }
      index {
        path  = "/created_at"
        order = "descending"
      }
    }

    excluded_path {
      path = "/response_data/*"
    }
  }
}


# Private DNS zone links may exist elsewhere; this module only creates PEs.
# Private Endpoints
resource "azurerm_private_endpoint" "pe_aoai" {
  count               = var.deploy_agentic_app && var.deploy_aoai && var.deploy_agentic_private_endpoints ? 1 : 0
  name                = "pe-aoai-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.nongen_private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-aoai"
    private_connection_resource_id = azurerm_cognitive_account.aoai[0].id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.pdz_aoai[0].id]
  }

  tags = var.tags
}

# Private Endpoint for Cosmos DB
resource "azurerm_private_endpoint" "pe_cosmos" {
  count               = var.deploy_agentic_app && var.deploy_cosmos_db && var.deploy_agentic_private_endpoints ? 1 : 0
  name                = "pe-cosmos-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.nongen_private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-cosmos"
    private_connection_resource_id = azurerm_cosmosdb_account.cosmos[0].id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.pdz_cosmos[0].id]
  }

  tags = var.tags
}


# Private DNS zones and links for the private endpoints
resource "azurerm_private_dns_zone" "pdz_aoai" {
  count               = var.deploy_agentic_app && var.deploy_agentic_private_endpoints && var.deploy_aoai ? 1 : 0
  name                = "privatelink.openai.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# Private DNS Zone for Cosmos DB
resource "azurerm_private_dns_zone" "pdz_cosmos" {
  count               = var.deploy_agentic_app && var.deploy_agentic_private_endpoints && var.deploy_cosmos_db ? 1 : 0
  name                = "privatelink.documents.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_aoai_nongen" {
  count                 = var.deploy_agentic_app && var.deploy_agentic_private_endpoints && var.deploy_aoai && var.deploy_nongen_vnet ? 1 : 0
  name                  = "aoai-nongen-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_aoai[0].name
  virtual_network_id    = var.nongen_vnet_id
  registration_enabled  = false
  tags                  = var.tags
}

# Private DNS Zone Virtual Network Link for Cosmos DB
resource "azurerm_private_dns_zone_virtual_network_link" "pdzvl_cosmos_nongen" {
  count                 = var.deploy_agentic_app && var.deploy_agentic_private_endpoints && var.deploy_cosmos_db && var.deploy_nongen_vnet ? 1 : 0
  name                  = "cosmos-nongen-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.pdz_cosmos[0].name
  virtual_network_id    = var.nongen_vnet_id
  registration_enabled  = false
  tags                  = var.tags
}


# Attach DNS zones to the private endpoints
// Note: DNS zone groups are defined inline in the private endpoint resources above.

# System assigned identity for app
resource "azurerm_linux_web_app" "app" {
  count               = var.deploy_agentic_app ? 1 : 0
  name                = "app-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.plan[0].id

  https_only = true

  site_config {
    application_stack {
      python_version = "3.11"
    }
    # VNet integration to egress through Non-Gen firewall UDR
    vnet_route_all_enabled = true
    # Always enable HTTPS only and configure startup
    always_on = true
  # Startup command for Python app - dependencies installed via SCM_DO_BUILD_DURING_DEPLOYMENT
  app_command_line = "python -m uvicorn main:app --host 0.0.0.0 --port 8000"
  }

  identity {
    type = "SystemAssigned"
  }

  app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.appi[0].connection_string
    WEBSITES_ENABLE_APP_SERVICE_STORAGE   = "true"
    WEBSITE_RUN_FROM_PACKAGE              = ""
    SCM_DO_BUILD_DURING_DEPLOYMENT        = "true"
    PYTHONUNBUFFERED                      = "1"
    # Azure OpenAI settings (using managed identity - no API key needed)
    AZURE_OPENAI_ENDPOINT   = try(azurerm_cognitive_account.aoai[0].endpoint, "")
    AZURE_OPENAI_DEPLOYMENT = var.aoai_deployment_name
    # Azure Cosmos DB settings for EOL response caching
    AZURE_COSMOS_DB_ENDPOINT   = try(azurerm_cosmosdb_account.cosmos[0].endpoint, "")
    AZURE_COSMOS_DB_DATABASE   = var.cosmos_db_database_name
    AZURE_COSMOS_DB_CONTAINER  = var.cosmos_db_container_name
    # Bing Search settings (using managed identity - no API key needed) - DEPRECATED
    BING_SEARCH_ENDPOINT    = try(azurerm_cognitive_account.bing_search[0].endpoint, "")
    # Azure AI Agent Service settings (Modern replacement for Bing Search)
    AZURE_AI_PROJECT_ENDPOINT = try(azurerm_cognitive_account.ai_foundry[0].endpoint, "")
    AZURE_AI_PROJECT_NAME     = try(azurerm_cognitive_account.ai_foundry[0].name, "")
  # Deprecated services removed: Azure AI Search
    # Log Analytics workspace for software inventory  
    LOG_ANALYTICS_WORKSPACE_ID          = var.workspace_guid
    LOG_ANALYTICS_WORKSPACE_RESOURCE_ID = var.workspace_resource_id
    # Azure resource information for portal links
    SUBSCRIPTION_ID     = data.azurerm_client_config.current.subscription_id
    RESOURCE_GROUP_NAME = var.resource_group_name
    # Teams bot integration placeholders
    BOT_ID       = var.bot_app_id
    BOT_PASSWORD = var.bot_app_password
  }

  tags = var.tags
}

# Link Web App to VNet via integration subnet
resource "azurerm_app_service_virtual_network_swift_connection" "app_integ" {
  count          = var.deploy_agentic_app ? 1 : 0
  app_service_id = azurerm_linux_web_app.app[0].id
  subnet_id      = coalesce(var.nongen_appsvc_integration_subnet_id, var.nongen_app_subnet_id)

  depends_on = [azurerm_linux_web_app.app]
}

# Role assignment for App Service to access Azure OpenAI
resource "azurerm_role_assignment" "app_aoai_user" {
  count                = var.deploy_agentic_app ? 1 : 0
  scope                = azurerm_cognitive_account.aoai[0].id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_linux_web_app.app[0].identity[0].principal_id
  depends_on           = [azurerm_linux_web_app.app]
}

# Role assignment for App Service to access Log Analytics workspace
resource "azurerm_role_assignment" "app_log_analytics_reader" {
  count                = var.deploy_agentic_app ? 1 : 0
  scope                = var.workspace_resource_id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_linux_web_app.app[0].identity[0].principal_id
  depends_on           = [azurerm_linux_web_app.app]
}

# Role assignment for App Service to access Cosmos DB
resource "azurerm_role_assignment" "app_cosmos_contributor" {
  count                = var.deploy_agentic_app && var.deploy_cosmos_db ? 1 : 0
  scope                = azurerm_cosmosdb_account.cosmos[0].id
  role_definition_name = "Cosmos DB Built-in Data Contributor"
  principal_id         = azurerm_linux_web_app.app[0].identity[0].principal_id
  depends_on           = [azurerm_linux_web_app.app, azurerm_cosmosdb_account.cosmos]
}

# Role assignment for App Service to access Bing Search with managed identity
resource "azurerm_role_assignment" "app_bing_search_user" {
  count                = var.deploy_agentic_app && var.deploy_bing_search ? 1 : 0
  scope                = azurerm_cognitive_account.bing_search[0].id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_linux_web_app.app[0].identity[0].principal_id
  depends_on           = [azurerm_linux_web_app.app, azurerm_cognitive_account.bing_search]
}


# Optional: Bot Channels Registration for Teams
resource "azurerm_bot_channels_registration" "bot" {
  count               = var.deploy_agentic_app && var.enable_teams_integration && var.bot_app_id != null && var.bot_app_password != null ? 1 : 0
  name                = "bot-${var.agentic_app_name}-${var.project_name}-${var.environment}"
  location            = "global"
  resource_group_name = var.resource_group_name
  microsoft_app_id    = var.bot_app_id
  sku                 = "F0"

  tags = var.tags
}

resource "azurerm_bot_channel_ms_teams" "bot_teams" {
  count               = var.deploy_agentic_app && var.enable_teams_integration && var.bot_app_id != null && var.bot_app_password != null ? 1 : 0
  bot_name            = azurerm_bot_channels_registration.bot[0].name
  location            = azurerm_bot_channels_registration.bot[0].location
  resource_group_name = var.resource_group_name
}

# ============================================================================
# AZURE CONTAINER REGISTRY
# ============================================================================

resource "azurerm_container_registry" "acr" {
  count                     = var.deploy_agentic_app && var.deploy_acr ? 1 : 0
  name                      = coalesce(var.acr_name, "acr${replace(var.project_name, "-", "")}${var.environment}")
  resource_group_name       = var.resource_group_name
  location                  = var.location
  sku                       = var.acr_sku
  admin_enabled             = var.acr_admin_enabled
  public_network_access_enabled = !var.deploy_agentic_private_endpoints
  
  tags = var.tags
}

# ============================================================================
# BING SEARCH API (COGNITIVE SERVICES) - DEPRECATED
# ============================================================================
# NOTE: Bing Search API is deprecated. Microsoft recommends migrating to
# "Grounding with Bing Search via Azure AI Agent Service"

resource "azurerm_cognitive_account" "bing_search" {
  count                         = var.deploy_agentic_app && var.deploy_bing_search ? 1 : 0
  name                          = coalesce(var.bing_search_name, "bing-${var.agentic_app_name}-${var.project_name}-${var.environment}")
  location                      = "global"  # Bing Search is a global service
  resource_group_name           = var.resource_group_name
  kind                          = "Bing.Search.v7"
  sku_name                      = var.bing_search_sku_name
  public_network_access_enabled = !var.deploy_agentic_private_endpoints
  tags                          = var.tags

  # Network ACLs not supported for Bing Search
}

# ============================================================================
# AZURE AI AGENT SERVICE (MODERN REPLACEMENT FOR BING SEARCH)
# ============================================================================

# Azure AI Services (Multi-service account for Azure AI Foundry)
resource "azurerm_cognitive_account" "ai_foundry" {
  count                         = var.deploy_agentic_app && var.deploy_azure_ai_agent ? 1 : 0
  name                          = coalesce(var.azure_ai_foundry_name, "ai-foundry-${var.agentic_app_name}-${var.project_name}-${var.environment}")
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "CognitiveServices"  # Multi-service account for Azure AI
  sku_name                      = var.azure_ai_foundry_sku_name
  custom_subdomain_name         = coalesce(var.azure_ai_foundry_name, "ai-foundry-${var.agentic_app_name}-${var.project_name}-${var.environment}")
  public_network_access_enabled = !var.deploy_agentic_private_endpoints
  tags                          = merge(var.tags, {
    Purpose = "Azure AI Agent Service with Grounding"
    Replaces = "Deprecated Bing Search API"
  })

  dynamic "network_acls" {
    for_each = var.deploy_agentic_private_endpoints ? [1] : []
    content {
      default_action = "Deny"
      virtual_network_rules {
        subnet_id = var.agentic_subnet_id
      }
    }
  }
}

# Role assignment for App Service to access Azure AI Foundry
resource "azurerm_role_assignment" "app_ai_foundry_user" {
  count                = var.deploy_agentic_app && var.deploy_azure_ai_agent ? 1 : 0
  scope                = azurerm_cognitive_account.ai_foundry[0].id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_linux_web_app.app[0].identity[0].principal_id
  depends_on           = [azurerm_linux_web_app.app, azurerm_cognitive_account.ai_foundry]
}
