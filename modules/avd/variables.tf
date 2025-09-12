# ============================================================================
# BASIC CONFIGURATION
# ============================================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "avd-demo"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "Australia East"
}

variable "resource_group_id" {
  description = "Resource Group ID for AVD resources"
  type        = string
}

# ============================================================================
# NETWORK CONFIGURATION
# ============================================================================

variable "vnet_id" {
  description = "Virtual Network ID for AVD deployment"
  type        = string
}

variable "vnet_name" {
  description = "Virtual Network name"
  type        = string
}

variable "vnet_resource_group" {
  description = "Resource group name containing the VNet"
  type        = string
}

variable "session_host_subnet_prefix" {
  description = "Address prefix for session host subnet"
  type        = string
  default     = "100.0.10.0/24"
}

variable "private_endpoint_subnet_prefix" {
  description = "Address prefix for private endpoint subnet"
  type        = string
  default     = "100.0.11.0/24"
}

# ============================================================================
# FIREWALL CONFIGURATION
# ============================================================================

variable "deploy_nongen_firewall" {
  description = "Whether Non-Gen firewall is deployed for routing"
  type        = bool
  default     = false
}

variable "nongen_firewall_ip" {
  description = "Private IP of Non-Gen firewall for routing (when using Non-Gen VNet)"
  type        = string
  default     = null
}

# ============================================================================
# HOST POOL CONFIGURATION
# ============================================================================

variable "host_pool_type" {
  description = "Type of host pool (Personal or Pooled)"
  type        = string
  default     = "Pooled"
  validation {
    condition     = contains(["Personal", "Pooled"], var.host_pool_type)
    error_message = "Host pool type must be either 'Personal' or 'Pooled'."
  }
}

variable "host_pool_load_balancer_type" {
  description = "Load balancer type for pooled host pools"
  type        = string
  default     = "BreadthFirst"
  validation {
    condition     = contains(["BreadthFirst", "DepthFirst"], var.host_pool_load_balancer_type)
    error_message = "Load balancer type must be either 'BreadthFirst' or 'DepthFirst'."
  }
}

variable "host_pool_maximum_sessions" {
  description = "Maximum number of sessions per session host"
  type        = number
  default     = 10
}

variable "host_pool_start_vm_on_connect" {
  description = "Enable start VM on connect feature"
  type        = bool
  default     = true
}

# ============================================================================
# SESSION HOST CONFIGURATION
# ============================================================================

variable "session_host_count" {
  description = "Number of session hosts to deploy"
  type        = number
  default     = 2
}

variable "session_host_vm_size" {
  description = "Size of session host VMs"
  type        = string
  default     = "Standard_D4s_v5"
}

variable "session_host_image_publisher" {
  description = "Publisher of the VM image"
  type        = string
  default     = "MicrosoftWindowsDesktop"
}

variable "session_host_image_offer" {
  description = "Offer of the VM image"
  type        = string
  default     = "Windows-11"
}

variable "session_host_image_sku" {
  description = "SKU of the VM image"
  type        = string
  default     = "win11-23h2-avd"
}

variable "session_host_admin_username" {
  description = "Admin username for session hosts"
  type        = string
  default     = "avdadmin"
}

variable "session_host_admin_password" {
  description = "Admin password for session hosts"
  type        = string
  sensitive   = true
}

# ============================================================================
# AAD DOMAIN JOIN CONFIGURATION
# ============================================================================

variable "aad_join_enabled" {
  description = "Enable Azure AD domain join for session hosts"
  type        = bool
  default     = true
}

variable "domain_name" {
  description = "Domain name for AAD join (leave empty for Azure AD join)"
  type        = string
  default     = ""
}

variable "ou_path" {
  description = "Organizational Unit path for domain joined machines"
  type        = string
  default     = ""
}

# ============================================================================
# FSLOGIX CONFIGURATION
# ============================================================================

variable "fslogix_enabled" {
  description = "Enable FSLogix profile containers"
  type        = bool
  default     = true
}

variable "fslogix_storage_account_tier" {
  description = "Storage account tier for FSLogix profiles"
  type        = string
  default     = "Premium"
  validation {
    condition     = contains(["Standard", "Premium"], var.fslogix_storage_account_tier)
    error_message = "Storage account tier must be either 'Standard' or 'Premium'."
  }
}

variable "fslogix_storage_account_replication" {
  description = "Storage account replication type for FSLogix profiles"
  type        = string
  default     = "LRS"
  validation {
    condition     = contains(["LRS", "ZRS", "GRS", "RAGRS"], var.fslogix_storage_account_replication)
    error_message = "Storage account replication must be one of: LRS, ZRS, GRS, RAGRS."
  }
}

variable "fslogix_file_share_quota_gb" {
  description = "File share quota in GB for FSLogix profiles"
  type        = number
  default     = 1024
}

# ============================================================================
# PRIVATE ENDPOINTS CONFIGURATION
# ============================================================================

variable "private_endpoints_enabled" {
  description = "Enable private endpoints for AVD services"
  type        = bool
  default     = true
}

# ============================================================================
# MONITORING CONFIGURATION
# ============================================================================

variable "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID for AVD monitoring"
  type        = string
}

# ============================================================================
# TAGS
# ============================================================================

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
