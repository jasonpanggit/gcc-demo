# ============================================================================
# FIREWALL MODULE VARIABLES
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

variable "firewall_subnet_id" {
  description = "The ID of the firewall subnet"
  type        = string
}

variable "hub_firewall_sku_tier" {
  description = "SKU tier for Azure Firewall"
  type        = string
  default     = "Standard"
}

variable "hub_firewall_explicit_proxy" {
  description = "Whether to enable explicit proxy on Azure Firewall"
  type        = bool
  default     = false
}

variable "hub_firewall_explicit_proxy_nat" {
  description = "Whether to enable NAT rules for explicit proxy ports"
  type        = bool
  default     = false
}

variable "hub_firewall_explicit_proxy_http_port" {
  description = "HTTP port for explicit proxy"
  type        = number
  default     = 8080
}

variable "hub_firewall_explicit_proxy_https_port" {
  description = "HTTPS port for explicit proxy"
  type        = number
  default     = 8443
}

variable "spoke_address_spaces" {
  description = "Address spaces for spoke networks"
  type        = list(string)
  default     = []
}

variable "onprem_address_space" {
  description = "Address space for on-premises networks"
  type        = list(string)
  default     = []
}

# Additional variables needed for the module
variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default     = {}
}

variable "deploy_hub_vnet" {
  description = "Deploy hub virtual network"
  type        = bool
  default     = true
}

variable "deploy_hub_firewall" {
  description = "Deploy Azure Firewall in hub"
  type        = bool
  default     = false
}

variable "hub_firewall_dns_proxy_enabled" {
  description = "Enable DNS proxy on Azure Firewall"
  type        = bool
  default     = false
}

variable "hub_firewall_arc_rules" {
  description = "Deploy Azure Arc firewall rules"
  type        = bool
  default     = false
}

# ============================================================================
# NON-GEN FIREWALL VARIABLES
# ============================================================================

variable "deploy_nongen_vnet" {
  description = "Whether to deploy Non-Gen VNet"
  type        = bool
  default     = false
}

variable "deploy_nongen_firewall" {
  description = "Whether to deploy Non-Gen firewall"
  type        = bool
  default     = false
}

variable "nongen_firewall_subnet_id" {
  description = "The ID of the Non-Gen firewall subnet"
  type        = string
  default     = null
}

variable "nongen_firewall_avd_rules" {
  description = "Enable Azure Virtual Desktop specific firewall rules for Non-Gen firewall"
  type        = bool
  default     = true
}

variable "nongen_firewall_agentic_rules" {
  description = "Enable firewall policy rules required for the agentic app (e.g., endoflife.date)"
  type        = bool
  default     = false
}

variable "nongen_firewall_container_apps_rules" {
  description = "Enable firewall policy rules required for Container Apps (ACR, MCR, Azure services)"
  type        = bool
  default     = false
}

variable "nongen_firewall_dns_proxy_enabled" {
  description = "Enable DNS proxy on Non-Gen Azure Firewall"
  type        = bool
  default     = false
}

variable "deploy_agentic_app" {
  description = "Deploy the EOL agentic web app and dependencies"
  type        = bool
  default     = false
}

variable "onprem_vnet_address_space" {
  description = "Address space for on-premises VNet"
  type        = list(string)
  default     = []
}

variable "hub_vnet_address_space" {
  description = "Address space for hub VNet"
  type        = list(string)
  default     = []
}
