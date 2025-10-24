# ============================================================================
# CONTAINER APPS MODULE VARIABLES
# ============================================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# ============================================================================
# CONTAINER APPS CONFIGURATION
# ============================================================================

variable "deploy_container_apps" {
  description = "Whether to deploy Container Apps"
  type        = bool
  default     = false
}

variable "app_name" {
  description = "Base name of the application"
  type        = string
  default     = "eol-agentic"
}

variable "app_port" {
  description = "Application port"
  type        = number
  default     = 8000
}

variable "mcp_port" {
  description = "Azure MCP Server port"
  type        = number
  default     = 5001
}

variable "min_replicas" {
  description = "Minimum number of replicas"
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum number of replicas"
  type        = number
  default     = 3
}

variable "app_container_image" {
  description = "Main application container image"
  type        = string
}

variable "app_container_cpu" {
  description = "CPU allocation for main app container"
  type        = number
  default     = 1.0
}

variable "app_container_memory" {
  description = "Memory allocation for main app container"
  type        = string
  default     = "2Gi"
}

variable "mcp_container_image" {
  description = "Azure MCP Server container image"
  type        = string
  default     = "mcr.microsoft.com/azure-sdk/azure-mcp:latest"
}

variable "mcp_container_cpu" {
  description = "CPU allocation for MCP sidecar container"
  type        = number
  default     = 0.5
}

variable "mcp_container_memory" {
  description = "Memory allocation for MCP sidecar container"
  type        = string
  default     = "1Gi"
}

variable "debug_mode" {
  description = "Enable debug mode"
  type        = bool
  default     = false
}

# ============================================================================
# NETWORKING
# ============================================================================

variable "container_apps_subnet_id" {
  description = "Subnet ID for Container Apps environment infrastructure"
  type        = string
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for private endpoints"
  type        = string
}

variable "internal_load_balancer_enabled" {
  description = "Enable internal load balancer (private Container Apps)"
  type        = bool
  default     = true
}

variable "zone_redundancy_enabled" {
  description = "Enable zone redundancy for Container Apps environment"
  type        = bool
  default     = false
}

# ============================================================================
# AZURE CONTAINER REGISTRY
# ============================================================================

variable "deploy_acr" {
  description = "Deploy Azure Container Registry"
  type        = bool
  default     = true
}

variable "acr_name" {
  description = "Azure Container Registry name (optional)"
  type        = string
  default     = null
}

variable "acr_sku" {
  description = "Azure Container Registry SKU"
  type        = string
  default     = "Premium"
}

variable "acr_admin_enabled" {
  description = "Enable ACR admin account"
  type        = bool
  default     = true
}

variable "acr_login_server" {
  description = "ACR login server (if using external ACR)"
  type        = string
  default     = null
}

variable "acr_username" {
  description = "ACR username (if using external ACR)"
  type        = string
  default     = null
}

variable "acr_password" {
  description = "ACR password (if using external ACR)"
  type        = string
  default     = null
  sensitive   = true
}

# ============================================================================
# LOG ANALYTICS
# ============================================================================

variable "create_log_analytics_workspace" {
  description = "Create a new Log Analytics workspace"
  type        = bool
  default     = true
}

variable "workspace_resource_id" {
  description = "Existing Log Analytics Workspace resource ID"
  type        = string
  default     = null
}

variable "workspace_guid" {
  description = "Log Analytics Workspace GUID"
  type        = string
  default     = null
}

# ============================================================================
# AZURE OPENAI
# ============================================================================

variable "deploy_aoai" {
  description = "Deploy Azure OpenAI account"
  type        = bool
  default     = true
}

variable "aoai_name" {
  description = "Azure OpenAI resource name (optional)"
  type        = string
  default     = null
}

variable "aoai_sku_name" {
  description = "Azure OpenAI SKU name"
  type        = string
  default     = "S0"
}

variable "aoai_deployment_name" {
  description = "Azure OpenAI deployment name"
  type        = string
  default     = "gpt-4o-mini"
}

variable "aoai_model_name" {
  description = "Azure OpenAI model name"
  type        = string
  default     = "gpt-4o-mini"
}

variable "aoai_model_version" {
  description = "Azure OpenAI model version"
  type        = string
  default     = "2024-07-18"
}

variable "aoai_deployment_sku_name" {
  description = "Azure OpenAI deployment SKU name"
  type        = string
  default     = "Standard"
}

variable "aoai_deployment_capacity" {
  description = "Azure OpenAI deployment capacity"
  type        = number
  default     = 10
}

# ============================================================================
# COSMOS DB
# ============================================================================

variable "deploy_cosmos_db" {
  description = "Deploy Cosmos DB"
  type        = bool
  default     = true
}

variable "cosmos_db_name" {
  description = "Cosmos DB account name (optional)"
  type        = string
  default     = null
}

variable "cosmos_db_serverless" {
  description = "Use Cosmos DB serverless mode"
  type        = bool
  default     = true
}

variable "cosmos_db_consistency_level" {
  description = "Cosmos DB consistency level"
  type        = string
  default     = "Session"
}

variable "cosmos_db_throughput" {
  description = "Cosmos DB throughput (RU/s, only for provisioned mode)"
  type        = number
  default     = 400
}

variable "cosmos_db_database_name" {
  description = "Cosmos DB database name"
  type        = string
  default     = "eol_cache"
}

variable "cosmos_db_container_name" {
  description = "Cosmos DB container name"
  type        = string
  default     = "eol_responses"
}

# ============================================================================
# AZURE AI FOUNDRY
# ============================================================================

variable "deploy_ai_foundry" {
  description = "Deploy Azure AI Foundry (AI Project)"
  type        = bool
  default     = true
}

variable "ai_project_name" {
  description = "Azure AI Foundry project name (optional)"
  type        = string
  default     = null
}

# ============================================================================
# PRIVATE ENDPOINTS
# ============================================================================

variable "deploy_private_endpoints" {
  description = "Deploy private endpoints for Azure services"
  type        = bool
  default     = true
}
