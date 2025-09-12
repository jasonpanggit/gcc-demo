# ============================================================================
# AGENTIC APP MODULE VARIABLES
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

variable "deploy_agentic_app" {
  description = "Whether to deploy the agentic app"
  type        = bool
  default     = false
}

variable "agentic_app_name" {
  description = "Base name of the agentic app"
  type        = string
  default     = "eol-agentic"
}

variable "app_service_sku" {
  description = "App Service Plan SKU"
  type        = string
  default     = "P1v3"
}

variable "deploy_nongen_vnet" {
  description = "Whether Non-Gen VNet is deployed (used for count logic)"
  type        = bool
  default     = false
}

variable "nongen_vnet_id" {
  description = "Non-Gen VNet ID for DNS linking (optional)"
  type        = string
  default     = null
}

variable "nongen_private_endpoint_subnet_id" {
  description = "Subnet ID for private endpoints in Non-Gen VNet"
  type        = string
}

variable "nongen_appsvc_integration_subnet_id" {
  description = "Subnet ID for App Service VNet integration in Non-Gen VNet. Required for private endpoint connectivity to Azure services like OpenAI and Log Analytics."
  type        = string
  default     = null
}

# Deprecated: use nongen_appsvc_integration_subnet_id
variable "nongen_app_subnet_id" {
  description = "(Deprecated) Subnet ID for App Service VNet integration in Non-Gen VNet"
  type        = string
  default     = null
}

variable "workspace_resource_id" {
  description = "Log Analytics Workspace resource ID used by the app to query software inventory"
  type        = string
  default     = null
}

variable "workspace_guid" {
  description = "Log Analytics Workspace GUID used by the app to query software inventory"
  type        = string
  default     = null
}

variable "deploy_aoai" {
  description = "Deploy Azure OpenAI account"
  type        = bool
  default     = true
}

variable "aoai_name" {
  description = "Azure OpenAI resource name"
  type        = string
  default     = null
}

variable "aoai_sku_name" {
  description = "Azure OpenAI SKU name"
  type        = string
  default     = "S0"
}

variable "aoai_deployment_name" {
  description = "Default model deployment name for chat (e.g., gpt-4o-mini)"
  type        = string
  default     = "gpt-4o-mini"
}

# ==============================================================================
# COSMOS DB CONFIGURATION
# ==============================================================================

variable "deploy_cosmos_db" {
  description = "Deploy Azure Cosmos DB for EOL response caching"
  type        = bool
  default     = false
}

variable "cosmos_db_name" {
  description = "Azure Cosmos DB account name"
  type        = string
  default     = null
}

variable "cosmos_db_database_name" {
  description = "Azure Cosmos DB database name"
  type        = string
  default     = "eol_cache"
}

variable "cosmos_db_container_name" {
  description = "Azure Cosmos DB container name for caching EOL responses"
  type        = string
  default     = "eol_responses"
}

variable "cosmos_db_offer_type" {
  description = "Cosmos DB offer type"
  type        = string
  default     = "Standard"
}

variable "cosmos_db_consistency_level" {
  description = "Cosmos DB consistency level"
  type        = string
  default     = "Session"
  validation {
    condition = contains([
      "BoundedStaleness",
      "Eventual",
      "Session",
      "Strong",
      "ConsistentPrefix"
    ], var.cosmos_db_consistency_level)
    error_message = "Invalid consistency level. Must be one of: BoundedStaleness, Eventual, Session, Strong, ConsistentPrefix."
  }
}

variable "cosmos_db_throughput" {
  description = "Cosmos DB container throughput (RU/s). Set to null to use serverless"
  type        = number
  default     = 400
}

variable "cosmos_db_serverless" {
  description = "Use Cosmos DB serverless instead of provisioned throughput"
  type        = bool
  default     = false
}

variable "cosmos_db_automatic_failover" {
  description = "Enable automatic failover for Cosmos DB"
  type        = bool
  default     = false
}

variable "cosmos_db_geo_location" {
  description = "Additional geo-location for Cosmos DB replication"
  type        = string
  default     = null
}

// Removed: Azure AI Search and old Cosmos DB variables (services no longer used)

variable "deploy_agentic_private_endpoints" {
  description = "Create private endpoints for AOAI"
  type        = bool
  default     = true
}

variable "enable_teams_integration" {
  description = "Provision Bot Channels Registration and Teams channel"
  type        = bool
  default     = false
}

variable "bot_app_id" {
  description = "Existing Entra App (Bot) Client ID for Teams integration"
  type        = string
  default     = null
}

variable "bot_app_password" {
  description = "Existing Entra App (Bot) Client Secret"
  type        = string
  default     = null
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
