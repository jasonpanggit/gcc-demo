# ============================================================================
# GATEWAYS MODULE VARIABLES
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

variable "gateway_subnet_id" {
  description = "The ID of the gateway subnet"
  type        = string
}

variable "deploy_expressroute_gateway" {
  description = "Whether to deploy ExpressRoute gateway"
  type        = bool
  default     = false
}

variable "deploy_vpn_gateway" {
  description = "Whether to deploy VPN gateway"
  type        = bool
  default     = false
}

variable "expressroute_gateway_sku" {
  description = "SKU for ExpressRoute gateway"
  type        = string
  default     = "Standard"
}

variable "vpn_gateway_sku" {
  description = "SKU for VPN gateway"
  type        = string
  default     = "VpnGw1"
}

variable "vpn_gateway_generation" {
  description = "Generation for VPN gateway"
  type        = string
  default     = "Generation1"
}

variable "vpn_gateway_bgp_enabled" {
  description = "Whether BGP is enabled for VPN gateway"
  type        = bool
  default     = false
}

variable "deploy_onprem_simulation" {
  description = "Whether to deploy on-premises simulation"
  type        = bool
  default     = false
}

variable "onprem_address_space" {
  description = "Address space for on-premises simulation"
  type        = list(string)
  default     = []
}

variable "onprem_bgp_asn" {
  description = "BGP ASN for on-premises"
  type        = number
  default     = 65000
}

variable "onprem_bgp_peer_ip" {
  description = "BGP peer IP for on-premises"
  type        = string
  default     = ""
}

variable "onprem_public_ip" {
  description = "Public IP for on-premises VPN"
  type        = string
  default     = ""
}

variable "vpn_shared_key" {
  description = "Shared key for VPN connection"
  type        = string
  default     = ""
  sensitive   = true
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

variable "deploy_expressroute_connection" {
  description = "Deploy ExpressRoute connection"
  type        = bool
  default     = false
}

variable "deploy_onprem_vnet" {
  description = "Deploy on-premises virtual network"
  type        = bool
  default     = false
}

variable "onprem_windows_vpn_setup" {
  description = "Setup Windows VPN for on-premises"
  type        = bool
  default     = false
}

variable "enable_expressroute_gateway_bgp" {
  description = "Enable BGP for ExpressRoute gateway"
  type        = bool
  default     = false
}

variable "expressroute_gateway_bgp_asn" {
  description = "BGP ASN for ExpressRoute gateway"
  type        = number
  default     = 65515
}

variable "enable_vpn_gateway_bgp" {
  description = "Enable BGP for VPN gateway"
  type        = bool
  default     = false
}

variable "vpn_gateway_bgp_asn" {
  description = "BGP ASN for VPN gateway"
  type        = number
  default     = 65515
}

variable "express_route_circuit_service_provider" {
  description = "ExpressRoute circuit service provider"
  type        = string
  default     = "Equinix"
}

variable "express_route_circuit_peering_location" {
  description = "ExpressRoute circuit peering location"
  type        = string
  default     = "Silicon Valley"
}

variable "express_route_circuit_bandwidth" {
  description = "ExpressRoute circuit bandwidth in Mbps"
  type        = number
  default     = 50
}

variable "onprem_vnet_address_space" {
  description = "On-premises VNet address space"
  type        = list(string)
  default     = ["192.168.0.0/16"]
}

variable "onprem_vpn_shared_key" {
  description = "Shared key for VPN connection"
  type        = string
  default     = "AzureA1b2C3"
  sensitive   = true
}

variable "enable_local_network_gateway_bgp" {
  description = "Enable BGP for local network gateway"
  type        = bool
  default     = false
}

variable "local_network_gateway_bgp_asn" {
  description = "BGP ASN for local network gateway"
  type        = number
  default     = 65001
}

variable "onprem_windows_2016_private_ip" {
  description = "Private IP address of the Windows Server 2016 VM for BGP peering"
  type        = string
  default     = null
}

# ExpressRoute gateway now creates its own public IP internally
