# ============================================================================
# COMPUTE MODULE VARIABLES
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

variable "onprem_vnet_id" {
  description = "The ID of the on-premises VNet"
  type        = string
}

variable "onprem_workload_subnet_id" {
  description = "The ID of the on-premises workload subnet"
  type        = string
}

variable "onprem_vm_size" {
  description = "Size of the on-premises VM"
  type        = string
  default     = "Standard_B2s"
}

variable "onprem_vm_admin_username" {
  description = "Admin username for on-premises VM"
  type        = string
  default     = "azureuser"
}

variable "onprem_vm_admin_password" {
  description = "Admin password for on-premises VM"
  type        = string
  sensitive   = true
}

variable "onprem_windows_arc_onboarding" {
  description = "Whether to enable Arc onboarding for Windows VM"
  type        = bool
  default     = false
}

variable "deploy_onprem_vpn_vm" {
  description = "Whether to deploy on-premises VPN VM"
  type        = bool
  default     = false
}

variable "onprem_vpn_vm_size" {
  description = "Size of the on-premises VPN VM"
  type        = string
  default     = "Standard_B2s"
}

variable "onprem_address_space" {
  description = "Address space for on-premises networks"
  type        = list(string)
}

variable "hub_address_space" {
  description = "Address space for hub network"
  type        = list(string)
}

variable "storage_account_name" {
  description = "Name of the storage account for scripts"
  type        = string
}

variable "storage_container_name" {
  description = "Name of the storage container for scripts"
  type        = string
}

variable "arc_setup_command" {
  description = "Command to set up Arc onboarding"
  type        = string
  default     = ""
}

# Additional variables needed for the module
variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}

# Deployment flags
variable "deploy_route_server" {
  description = "Deploy route server"
  type        = bool
  default     = false
}

variable "deploy_linux_nva" {
  description = "Deploy Linux NVA"
  type        = bool
  default     = false
}

variable "deploy_squid_proxy" {
  description = "Deploy Squid proxy"
  type        = bool
  default     = false
}

variable "deploy_onprem_vnet" {
  description = "Deploy on-premises VNet"
  type        = bool
  default     = false
}

variable "deploy_onprem_windows_server_2025" {
  description = "Deploy on-premises Windows Server 2025"
  type        = bool
  default     = false
}

variable "deploy_onprem_windows_server_2016" {
  description = "Deploy on-premises Windows Server 2016"
  type        = bool
  default     = false
}

# Subnet IDs
variable "nva_subnet_id" {
  description = "NVA subnet ID"
  type        = string
  default     = ""
}

variable "squid_subnet_id" {
  description = "Squid subnet ID"
  type        = string
  default     = ""
}

# NSG IDs
variable "nva_nsg_id" {
  description = "NVA NSG ID"
  type        = string
  default     = ""
}

variable "squid_nsg_id" {
  description = "Squid NSG ID"
  type        = string
  default     = ""
}

variable "onprem_windows_nsg_id" {
  description = "On-premises Windows NSG ID"
  type        = string
  default     = ""
}

# VM Configuration
variable "nva_vm_size" {
  description = "NVA VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "nva_admin_username" {
  description = "NVA admin username"
  type        = string
  default     = "azureuser"
}

variable "nva_admin_password" {
  description = "NVA admin password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "squid_vm_size" {
  description = "Squid VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "squid_admin_username" {
  description = "Squid admin username"
  type        = string
  default     = "azureuser"
}

variable "squid_admin_password" {
  description = "Squid admin password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "onprem_windows_vm_size" {
  description = "On-premises Windows VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "onprem_windows_admin_username" {
  description = "On-premises Windows admin username"
  type        = string
  default     = "azureuser"
}

variable "onprem_windows_admin_password" {
  description = "On-premises Windows admin password"
  type        = string
  sensitive   = true
  default     = ""
}

# BGP and Route Server Configuration
variable "nva_bgp_asn" {
  description = "NVA BGP ASN"
  type        = number
  default     = 65001
}

variable "route_server_ip_1" {
  description = "Route server IP 1"
  type        = string
  default     = ""
}

variable "route_server_ip_2" {
  description = "Route server IP 2"
  type        = string
  default     = ""
}

variable "nva_bgp_advertised_routes" {
  description = "NVA BGP advertised routes"
  type        = list(string)
  default     = []
}

# VM Extensions Configuration (only new variables)
variable "deploy_script_storage" {
  description = "Whether script storage is deployed"
  type        = bool
  default     = false
}

variable "storage_scripts_sas_url" {
  description = "SAS URL for scripts storage"
  type        = string
  default     = ""
}

variable "onprem_windows_vpn_setup" {
  description = "Whether to enable VPN setup for on-premises Windows"
  type        = bool
  default     = false
}

variable "deploy_vpn_gateway" {
  description = "Whether VPN gateway is deployed"
  type        = bool
  default     = false
}

variable "onprem_vpn_shared_key" {
  description = "Shared key for VPN connection"
  type        = string
  sensitive   = true
  default     = ""
}
