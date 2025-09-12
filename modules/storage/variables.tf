# ============================================================================
# STORAGE MODULE VARIABLES
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
  description = "The Azure region to deploy to"
  type        = string
}

variable "resource_group_name" {
  description = "The name of the resource group"
  type        = string
}

# Storage deployment variables
variable "deploy_script_storage" {
  description = "Deploy script storage account"
  type        = bool
  default     = false
}

variable "onprem_windows_arc_onboarding" {
  description = "Deploy Arc onboarding for Windows"
  type        = bool
  default     = false
}

variable "onprem_windows_vpn_setup" {
  description = "Deploy VPN setup for Windows"
  type        = bool
  default     = false
}

variable "deploy_vpn_gateway" {
  description = "Deploy VPN gateway"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}
