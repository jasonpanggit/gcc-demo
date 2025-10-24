# ============================================================================
# ROUTING MODULE VARIABLES
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

# ============================================================================
# DEPLOYMENT FLAGS
# ============================================================================

variable "deploy_hub_vnet" {
  description = "Whether to deploy the hub virtual network"
  type        = bool
}

variable "deploy_expressroute_gateway" {
  description = "Whether to deploy ExpressRoute gateway"
  type        = bool
}

variable "deploy_vpn_gateway" {
  description = "Whether to deploy VPN gateway"
  type        = bool
}

variable "deploy_hub_firewall" {
  description = "Whether to deploy Azure Firewall in hub VNet"
  type        = bool
}

variable "deploy_nongen_vnet" {
  description = "Whether to deploy Non-Gen VNet"
  type        = bool
}

variable "deploy_nongen_firewall" {
  description = "Whether to deploy firewall in Non-Gen VNet"
  type        = bool
}

variable "deploy_gen_vnet" {
  description = "Whether to deploy Gen VNet"
  type        = bool
}

variable "deploy_squid_proxy" {
  description = "Whether to deploy Squid proxy server"
  type        = bool
}

variable "hub_firewall_force_tunneling" {
  description = "Whether to enable force tunneling for Azure Firewall"
  type        = bool
}

variable "route_internet_to_nongen_firewall" {
  description = "Whether to route Gen VNet internet traffic through Non-Gen firewall"
  type        = bool
}

# ============================================================================
# FIREWALL IP ADDRESSES
# ============================================================================

variable "hub_firewall_private_ip" {
  description = "The private IP address of the hub Azure Firewall"
  type        = string
}

variable "nongen_firewall_private_ip" {
  description = "The private IP address of the Non-Gen Azure Firewall"
  type        = string
  default     = null
}

# ============================================================================
# NETWORK CONFIGURATION
# ============================================================================

variable "nva_bgp_advertised_routes" {
  description = "List of routes to be advertised by the NVA via BGP"
  type        = list(string)
  default     = []
}

variable "nongen_vnet_address_space" {
  description = "Address space for the Non-Gen VNet"
  type        = list(string)
  default     = []
}

variable "gen_vnet_address_space" {
  description = "Address space for the Gen VNet"
  type        = list(string)
  default     = []
}

# ============================================================================
# SUBNET IDS (FROM NETWORKING MODULE)
# ============================================================================

variable "gateway_subnet_id" {
  description = "The ID of the gateway subnet"
  type        = string
  default     = ""
}

variable "firewall_subnet_id" {
  description = "The ID of the Azure Firewall subnet"
  type        = string
  default     = ""
}

variable "squid_subnet_id" {
  description = "The ID of the Squid proxy subnet"
  type        = string
  default     = ""
}

variable "gen_workload_subnet_id" {
  description = "The ID of the Gen workload subnet"
  type        = string
  default     = ""
}

variable "nongen_appsvc_integration_subnet_id" {
  description = "The ID of the Non-Gen App Service VNet integration subnet"
  type        = string
  default     = ""
}

variable "nongen_container_apps_subnet_id" {
  description = "The ID of the Non-Gen Container Apps subnet"
  type        = string
  default     = ""
}
