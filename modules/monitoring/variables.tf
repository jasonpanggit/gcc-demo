# ============================================================================
# MONITORING MODULE VARIABLES
# ============================================================================

variable "project_name" {
  description = "The name of the project"
  type        = string
}

variable "environment" {
  description = "The environment (e.g., dev, staging, prod)"
  type        = string
}

variable "location" {
  description = "The Azure region for resources"
  type        = string
}

variable "resource_group_name" {
  description = "The name of the resource group"
  type        = string
}

variable "deploy_hub_vnet" {
  description = "Whether to deploy hub VNet"
  type        = bool
  default     = true
}

variable "deploy_azure_monitor_private_link_scope" {
  description = "Whether to deploy Azure Monitor private link scope"
  type        = bool
  default     = false
}

variable "log_analytics_workspace_sku" {
  description = "The SKU for the Log Analytics Workspace"
  type        = string
  default     = "PerGB2018"
}

variable "log_analytics_workspace_retention_days" {
  description = "The retention in days for the Log Analytics Workspace"
  type        = number
  default     = 30
}

variable "private_endpoint_subnet_id" {
  description = "The subnet ID for private endpoints"
  type        = string
}

variable "hub_vnet_id" {
  description = "The ID of the hub virtual network"
  type        = string
}

variable "deploy_onprem_vnet" {
  description = "Whether to deploy on-premises VNet"
  type        = bool
  default     = false
}

variable "onprem_windows_arc_onboarding" {
  description = "Whether to enable Arc onboarding for on-premises Windows"
  type        = bool
  default     = false
}

variable "onprem_vnet_id" {
  description = "The ID of the on-premises virtual network"
  type        = string
  default     = null
}

# ============================================================================
# AZURE MONITOR ACCESS MODE VARIABLES
# ============================================================================

variable "azure_monitor_query_access_mode" {
  description = "The query access mode for Azure Monitor Private Link Scope. Valid values are 'Open' or 'PrivateOnly'"
  type        = string
  default     = "Open"
  
  validation {
    condition     = contains(["Open", "PrivateOnly"], var.azure_monitor_query_access_mode)
    error_message = "The azure_monitor_query_access_mode must be either 'Open' or 'PrivateOnly'."
  }
}

variable "azure_monitor_ingestion_access_mode" {
  description = "The ingestion access mode for Azure Monitor Private Link Scope. Valid values are 'Open' or 'PrivateOnly'"
  type        = string
  default     = "Open"
  
  validation {
    condition     = contains(["Open", "PrivateOnly"], var.azure_monitor_ingestion_access_mode)
    error_message = "The azure_monitor_ingestion_access_mode must be either 'Open' or 'PrivateOnly'."
  }
}
