# ============================================================================
# CONTAINER APPS MODULE - Multi-Container Deployment with Private Networking
# ============================================================================
# This module creates:
# 1. Container Apps Environment with VNet integration
# 2. Container App with multi-container support (main app + MCP sidecar)
# 3. Private endpoints for Azure services (AOAI, Cosmos DB, Log Analytics)
# 4. Azure Container Registry for container images
# 5. Managed identity for secure authentication

# Get current Azure context
data "azurerm_client_config" "current" {}

# ============================================================================
# AZURE CONTAINER REGISTRY
# ============================================================================

resource "azurerm_container_registry" "acr" {
  count               = var.deploy_container_apps && var.deploy_acr ? 1 : 0
  name                = var.acr_name != null ? var.acr_name : replace("acr${var.project_name}${var.environment}${var.app_name}", "-", "")
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.acr_sku
  admin_enabled       = var.acr_admin_enabled
  
  # Public network access control
  public_network_access_enabled = !var.deploy_private_endpoints
  
  # Network ACLs for private endpoint access
  dynamic "network_rule_set" {
    for_each = var.deploy_private_endpoints ? [1] : []
    content {
      default_action = "Deny"
      virtual_network_rule {
        action    = "Allow"
        subnet_id = var.container_apps_subnet_id
      }
    }
  }

  tags = var.tags
}

# ============================================================================
# CONTAINER APPS ENVIRONMENT
# ============================================================================

resource "azurerm_log_analytics_workspace" "law" {
  count               = var.deploy_container_apps && var.create_log_analytics_workspace ? 1 : 0
  name                = "law-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "cae" {
  count                          = var.deploy_container_apps ? 1 : 0
  name                           = "cae-${var.app_name}-${var.project_name}-${var.environment}"
  location                       = var.location
  resource_group_name            = var.resource_group_name
  log_analytics_workspace_id     = var.create_log_analytics_workspace ? azurerm_log_analytics_workspace.law[0].id : var.workspace_resource_id
  infrastructure_subnet_id       = var.container_apps_subnet_id
  internal_load_balancer_enabled = var.internal_load_balancer_enabled
  zone_redundancy_enabled        = var.zone_redundancy_enabled

  tags = var.tags
}

# ============================================================================
# APPLICATION INSIGHTS
# ============================================================================

resource "azurerm_application_insights" "appi" {
  count               = var.deploy_container_apps ? 1 : 0
  name                = "appi-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
  workspace_id        = var.create_log_analytics_workspace ? azurerm_log_analytics_workspace.law[0].id : var.workspace_resource_id
  tags                = var.tags
}

# ============================================================================
# AZURE OPENAI
# ============================================================================

resource "azurerm_cognitive_account" "aoai" {
  count                         = var.deploy_container_apps && var.deploy_aoai ? 1 : 0
  name                          = var.aoai_name != null ? var.aoai_name : "aoai-${var.app_name}-${var.project_name}-${var.environment}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "OpenAI"
  sku_name                      = var.aoai_sku_name
  custom_subdomain_name         = "${var.project_name}-${var.environment}-${var.app_name}"
  public_network_access_enabled = !var.deploy_private_endpoints
  tags                          = var.tags

  # Network ACLs for private endpoint access
  dynamic "network_acls" {
    for_each = var.deploy_private_endpoints ? [1] : []
    content {
      default_action = "Deny"
      ip_rules       = []
      virtual_network_rules {
        subnet_id = var.container_apps_subnet_id
      }
    }
  }
}

# Azure OpenAI Deployment
resource "azurerm_cognitive_deployment" "aoai_deployment" {
  count                = var.deploy_container_apps && var.deploy_aoai ? 1 : 0
  name                 = var.aoai_deployment_name
  cognitive_account_id = azurerm_cognitive_account.aoai[0].id

  model {
    format  = "OpenAI"
    name    = var.aoai_model_name
    version = var.aoai_model_version
  }

  sku {
    name     = var.aoai_deployment_sku_name
    capacity = var.aoai_deployment_capacity
  }
}

# ============================================================================
# COSMOS DB
# ============================================================================

resource "azurerm_cosmosdb_account" "cosmos" {
  count                         = var.deploy_container_apps && var.deploy_cosmos_db ? 1 : 0
  name                          = var.cosmos_db_name != null ? var.cosmos_db_name : "cosmos-${var.app_name}-${var.project_name}-${var.environment}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  public_network_access_enabled = !var.deploy_private_endpoints
  
  capabilities {
    name = var.cosmos_db_serverless ? "EnableServerless" : "EnableAggregationPipeline"
  }

  consistency_policy {
    consistency_level = var.cosmos_db_consistency_level
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "database" {
  count               = var.deploy_container_apps && var.deploy_cosmos_db ? 1 : 0
  name                = var.cosmos_db_database_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos[0].name
}

resource "azurerm_cosmosdb_sql_container" "container" {
  count               = var.deploy_container_apps && var.deploy_cosmos_db ? 1 : 0
  name                = var.cosmos_db_container_name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.cosmos[0].name
  database_name       = azurerm_cosmosdb_sql_database.database[0].name
  partition_key_paths = ["/cache_key"]
  partition_key_kind  = "Hash"
  default_ttl         = 2592000 # 30 days

  throughput = var.cosmos_db_serverless ? null : var.cosmos_db_throughput

  indexing_policy {
    indexing_mode = "consistent"
    included_path {
      path = "/*"
    }
  }
}

# ============================================================================
# AZURE AI FOUNDRY (AI Project)
# ============================================================================

resource "azurerm_cognitive_account" "ai_project" {
  count                         = var.deploy_container_apps && var.deploy_ai_foundry ? 1 : 0
  name                          = var.ai_project_name != null ? var.ai_project_name : "ai-foundry-${var.app_name}-${var.project_name}-${var.environment}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  kind                          = "AIServices"
  sku_name                      = "S0"
  public_network_access_enabled = !var.deploy_private_endpoints
  tags                          = var.tags

  dynamic "network_acls" {
    for_each = var.deploy_private_endpoints ? [1] : []
    content {
      default_action = "Deny"
      ip_rules       = []
      virtual_network_rules {
        subnet_id = var.container_apps_subnet_id
      }
    }
  }
}

# ============================================================================
# CONTAINER APP
# ============================================================================

resource "azurerm_container_app" "app" {
  count                        = var.deploy_container_apps ? 1 : 0
  name                         = "ca-${var.app_name}-${var.project_name}-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.cae[0].id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = var.deploy_acr ? azurerm_container_registry.acr[0].login_server : var.acr_login_server
    username = var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_username : var.acr_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = var.deploy_acr && var.acr_admin_enabled ? azurerm_container_registry.acr[0].admin_password : var.acr_password
  }

  ingress {
    external_enabled = !var.internal_load_balancer_enabled
    target_port      = var.app_port
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    # Main Application Container
    container {
      name   = "eol-app"
      image  = var.app_container_image
      cpu    = var.app_container_cpu
      memory = var.app_container_memory

      env {
        name  = "CONTAINER_MODE"
        value = "true"
      }

      env {
        name  = "DEBUG_MODE"
        value = var.debug_mode ? "true" : "false"
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "WEBSITES_PORT"
        value = tostring(var.app_port)
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      # Azure MCP Server Connection
      env {
        name  = "AZURE_MCP_URL"
        value = "http://localhost:${var.mcp_port}"
      }

      env {
        name  = "AZURE_MCP_ENABLED"
        value = "true"
      }

      # Azure Configuration
      env {
        name  = "SUBSCRIPTION_ID"
        value = data.azurerm_client_config.current.subscription_id
      }

      env {
        name  = "RESOURCE_GROUP_NAME"
        value = var.resource_group_name
      }

      env {
        name  = "APP_NAME"
        value = "ca-${var.app_name}-${var.project_name}-${var.environment}"
      }

      # Azure OpenAI
      dynamic "env" {
        for_each = var.deploy_aoai ? [1] : []
        content {
          name  = "AZURE_OPENAI_ENDPOINT"
          value = azurerm_cognitive_account.aoai[0].endpoint
        }
      }

      dynamic "env" {
        for_each = var.deploy_aoai ? [1] : []
        content {
          name  = "AZURE_OPENAI_DEPLOYMENT"
          value = var.aoai_deployment_name
        }
      }

      # Log Analytics
      dynamic "env" {
        for_each = var.workspace_guid != null ? [1] : []
        content {
          name  = "LOG_ANALYTICS_WORKSPACE_ID"
          value = var.workspace_guid
        }
      }

      # Cosmos DB
      dynamic "env" {
        for_each = var.deploy_cosmos_db ? [1] : []
        content {
          name  = "AZURE_COSMOS_DB_ENDPOINT"
          value = azurerm_cosmosdb_account.cosmos[0].endpoint
        }
      }

      dynamic "env" {
        for_each = var.deploy_cosmos_db ? [1] : []
        content {
          name  = "AZURE_COSMOS_DB_DATABASE"
          value = var.cosmos_db_database_name
        }
      }

      dynamic "env" {
        for_each = var.deploy_cosmos_db ? [1] : []
        content {
          name  = "AZURE_COSMOS_DB_CONTAINER"
          value = var.cosmos_db_container_name
        }
      }

      # AI Foundry
      dynamic "env" {
        for_each = var.deploy_ai_foundry ? [1] : []
        content {
          name  = "AZURE_AI_PROJECT_NAME"
          value = var.ai_project_name != null ? var.ai_project_name : "ai-foundry-${var.app_name}-${var.project_name}-${var.environment}"
        }
      }

      dynamic "env" {
        for_each = var.deploy_ai_foundry ? [1] : []
        content {
          name  = "AZURE_AI_ENDPOINT"
          value = azurerm_cognitive_account.ai_project[0].endpoint
        }
      }
    }

    # Azure MCP Server Sidecar Container
    container {
      name   = "azure-mcp"
      image  = var.mcp_container_image
      cpu    = var.mcp_container_cpu
      memory = var.mcp_container_memory

      env {
        name  = "PORT"
        value = tostring(var.mcp_port)
      }

      # Azure authentication will use Container App's managed identity
    }
  }

  tags = var.tags
}

# ============================================================================
# ROLE ASSIGNMENTS FOR MANAGED IDENTITY
# ============================================================================

# Reader role on subscription for Azure MCP
resource "azurerm_role_assignment" "reader_subscription" {
  count                = var.deploy_container_apps ? 1 : 0
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  role_definition_name = "Reader"
  principal_id         = azurerm_container_app.app[0].identity[0].principal_id
}

# Contributor role on resource group for Azure MCP
resource "azurerm_role_assignment" "contributor_rg" {
  count                = var.deploy_container_apps ? 1 : 0
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Contributor"
  principal_id         = azurerm_container_app.app[0].identity[0].principal_id
}

# Cognitive Services User role for Azure OpenAI
resource "azurerm_role_assignment" "cognitive_services_user" {
  count                = var.deploy_container_apps && var.deploy_aoai ? 1 : 0
  scope                = azurerm_cognitive_account.aoai[0].id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_container_app.app[0].identity[0].principal_id
}

# Cosmos DB Data Contributor role
resource "azurerm_role_assignment" "cosmos_contributor" {
  count                = var.deploy_container_apps && var.deploy_cosmos_db ? 1 : 0
  scope                = azurerm_cosmosdb_account.cosmos[0].id
  role_definition_name = "Cosmos DB Account Contributor"
  principal_id         = azurerm_container_app.app[0].identity[0].principal_id
}

# ACR Pull role for Container App
resource "azurerm_role_assignment" "acr_pull" {
  count                = var.deploy_container_apps && var.deploy_acr ? 1 : 0
  scope                = azurerm_container_registry.acr[0].id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_container_app.app[0].identity[0].principal_id
}

# ============================================================================
# PRIVATE ENDPOINTS
# ============================================================================

# Private Endpoint for Azure OpenAI
resource "azurerm_private_endpoint" "aoai_pe" {
  count               = var.deploy_container_apps && var.deploy_aoai && var.deploy_private_endpoints ? 1 : 0
  name                = "pe-aoai-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-aoai-${var.app_name}"
    private_connection_resource_id = azurerm_cognitive_account.aoai[0].id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  tags = var.tags
}

# Private Endpoint for Cosmos DB
resource "azurerm_private_endpoint" "cosmos_pe" {
  count               = var.deploy_container_apps && var.deploy_cosmos_db && var.deploy_private_endpoints ? 1 : 0
  name                = "pe-cosmos-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-cosmos-${var.app_name}"
    private_connection_resource_id = azurerm_cosmosdb_account.cosmos[0].id
    is_manual_connection           = false
    subresource_names              = ["Sql"]
  }

  tags = var.tags
}

# Private Endpoint for Azure Container Registry
resource "azurerm_private_endpoint" "acr_pe" {
  count               = var.deploy_container_apps && var.deploy_acr && var.deploy_private_endpoints ? 1 : 0
  name                = "pe-acr-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-acr-${var.app_name}"
    private_connection_resource_id = azurerm_container_registry.acr[0].id
    is_manual_connection           = false
    subresource_names              = ["registry"]
  }

  tags = var.tags
}

# Private Endpoint for AI Foundry
resource "azurerm_private_endpoint" "ai_project_pe" {
  count               = var.deploy_container_apps && var.deploy_ai_foundry && var.deploy_private_endpoints ? 1 : 0
  name                = "pe-ai-${var.app_name}-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-ai-${var.app_name}"
    private_connection_resource_id = azurerm_cognitive_account.ai_project[0].id
    is_manual_connection           = false
    subresource_names              = ["account"]
  }

  tags = var.tags
}
