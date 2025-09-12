# ============================================================================
# NETWORKING MODULE VARIABLES
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

variable "hub_vnet_address_space" {
  description = "Address space for the hub virtual network"
  type        = list(string)
}

variable "hub_gateway_subnet_prefix" {
  description = "Address prefix for the gateway subnet"
  type        = string
  default     = null
}

variable "hub_firewall_subnet_prefix" {
  description = "Address prefix for the firewall subnet"
  type        = string
  default     = null
}

variable "hub_route_server_subnet_prefix" {
  description = "Address prefix for the route server subnet"
  type        = string
  default     = null
}

variable "hub_nva_subnet_prefix" {
  description = "Address prefix for the NVA subnet"
  type        = string
  default     = null
}

variable "hub_bastion_subnet_prefix" {
  description = "Address prefix for the bastion subnet"
  type        = string
  default     = null
}

variable "hub_squid_subnet_prefix" {
  description = "Address prefix for the squid proxy subnet"
  type        = string
  default     = null
}

variable "hub_private_endpoint_subnet_prefix" {
  description = "Address prefix for the private endpoint subnet"
  type        = string
  default     = null
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

variable "deploy_hub_firewall" {
  description = "Whether to deploy Azure Firewall"
  type        = bool
  default     = false
}

variable "deploy_route_server" {
  description = "Whether to deploy Route Server"
  type        = bool
  default     = false
}

variable "deploy_linux_nva" {
  description = "Whether to deploy Linux NVA"
  type        = bool
  default     = false
}

variable "deploy_bastion" {
  description = "Whether to deploy Azure Bastion"
  type        = bool
  default     = false
}

variable "deploy_squid_proxy" {
  description = "Whether to deploy Squid proxy"
  type        = bool
  default     = false
}

variable "deploy_arc_private_link_scope" {
  description = "Whether to deploy Arc private link scope"
  type        = bool
  default     = false
}

variable "deploy_azure_monitor_private_link_scope" {
  description = "Whether to deploy Azure Monitor private link scope"
  type        = bool
  default     = false
}

# Additional variables for enhanced networking
variable "deploy_hub_vnet" {
  description = "Deploy hub virtual network"
  type        = bool
  default     = true
}

variable "route_server_branch_to_branch" {
  description = "Enable branch to branch traffic on route server"
  type        = bool
  default     = true
}

# Route table related variables
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

variable "deploy_nongen_avd" {
  description = "Whether to deploy Non-Gen AVD"
  type        = bool
  default     = false
}

variable "deploy_agentic_app" {
  description = "Whether to deploy the agentic app network resources"
  type        = bool
  default     = false
}

variable "deploy_gen_vnet" {
  description = "Whether to deploy Gen VNet"
  type        = bool
  default     = false
}

variable "nongen_vnet_address_space" {
  description = "Address space for Non-Gen VNet"
  type        = list(string)
  default     = []
}

variable "gen_vnet_address_space" {
  description = "Address space for Gen VNet"
  type        = list(string)
  default     = []
}

# ============================================================================
# SPOKE NETWORKS VARIABLES
# ============================================================================

variable "nongen_firewall_subnet_prefix" {
  description = "Address prefix for Non-Gen firewall subnet"
  type        = string
  default     = null
}

variable "nongen_avd_subnet_prefix" {
  description = "Address prefix for Non-Gen AVD subnet"
  type        = string
  default     = null
}

variable "nongen_private_endpoint_subnet_prefix" {
  description = "Address prefix for Non-Gen Private Endpoint subnet"
  type        = string
  default     = null
}

variable "nongen_web_subnet_prefix" {
  description = "Address prefix for Non-Gen Web subnet"
  type        = string
  default     = null
}

variable "nongen_app_subnet_prefix" {
  description = "Address prefix for Non-Gen App subnet"
  type        = string
  default     = null
}

variable "nongen_db_subnet_prefix" {
  description = "Address prefix for Non-Gen DB subnet"
  type        = string
  default     = null
}

variable "nongen_apim_subnet_prefix" {
  description = "Address prefix for Non-Gen API Management subnet"
  type        = string
  default     = null
}

variable "gen_workload_subnet_prefix" {
  description = "Address prefix for Gen workload subnet"
  type        = string
  default     = null
}

variable "deploy_onprem_vnet" {
  description = "Whether to deploy on-premises VNet"
  type        = bool
  default     = false
}

variable "onprem_vnet_address_space" {
  description = "Address space for on-premises VNet"
  type        = list(string)
  default     = []
}

variable "onprem_workload_subnet_prefix" {
  description = "Address prefix for on-premises workload subnet"
  type        = string
  default     = null
}

variable "deploy_onprem_windows_server_2025" {
  description = "Whether to deploy on-premises Windows Server 2025"
  type        = bool
  default     = false
}

variable "deploy_onprem_windows_server_2016" {
  description = "Whether to deploy on-premises Windows Server 2016"
  type        = bool
  default     = false
}

variable "deploy_gen_nongen_peering" {
  description = "Whether to deploy peering between Gen and Non-Gen VNets"
  type        = bool
  default     = false
}

variable "deploy_hub_gen_peering" {
  description = "Whether to deploy peering between Hub and Gen VNets"
  type        = bool
  default     = false
}

variable "deploy_hub_onprem_peering" {
  description = "Whether to deploy peering between Hub and On-premises VNets"
  type        = bool
  default     = false
}

variable "deploy_hub_nongen_peering" {
  description = "Whether to deploy peering between Hub and Non-Gen VNets"
  type        = bool
  default     = false
}
