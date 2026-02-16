# ==============================================================================
# AZURE LANDING ZONE VARIABLES
# ==============================================================================
# This file defines all variables for the Azure Landing Zone infrastructure.
# Variables are organized by functional area for easy navigation and maintenance.

# ==============================================================================
# AZURE PROVIDER CONFIGURATION
# ==============================================================================
# Authentication variables for Azure Resource Manager provider

variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
}

variable "tenant_id" {
  description = "Azure Tenant ID"
  type        = string
}

variable "client_id" {
  description = "Azure Client ID (Service Principal Application ID)"
  type        = string
}

variable "client_secret" {
  description = "Azure Client Secret (Service Principal Password)"
  type        = string
  sensitive   = true
}

# ==============================================================================
# GENERAL CONFIGURATION
# ==============================================================================
# Base settings that affect all deployed resources

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "Australia East"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "network"
}

# ==============================================================================
# HUB VIRTUAL NETWORK CONFIGURATION
# ==============================================================================
# Core hub networking components providing centralized connectivity

variable "hub_vnet_address_space" {
  description = "Address space for the hub virtual network"
  type        = list(string)
  default     = ["172.16.0.0/16"]
}

# ==============================================================================
# HUB SUBNET CONFIGURATION
# ==============================================================================
# Subnet definitions for various services within the hub VNet

variable "hub_firewall_subnet_prefix" {
  description = "Address prefix for Azure Firewall subnet (AzureFirewallSubnet)"
  type        = string
  default     = "172.16.0.0/25"
}

variable "hub_firewall_management_subnet_prefix" {
  description = "Address prefix for Azure Firewall Management subnet (required for force tunneling)"
  type        = string
  default     = "172.16.0.128/25"
}

variable "hub_bastion_subnet_prefix" {
  description = "Address prefix for Azure Bastion subnet"
  type        = string
  default     = "172.16.1.0/24"
}

variable "hub_gateway_subnet_prefix" {
  description = "Address prefix for Gateway subnet"
  type        = string
  default     = "172.16.2.0/24"
}

variable "hub_route_server_subnet_prefix" {
  description = "Address prefix for Route Server subnet"
  type        = string
  default     = "172.16.3.0/24"
}

variable "hub_nva_subnet_prefix" {
  description = "Address prefix for NVA subnet"
  type        = string
  default     = "172.16.4.0/24"
}

variable "hub_squid_subnet_prefix" {
  description = "Address prefix for Squid proxy subnet"
  type        = string
  default     = "172.16.5.0/24"
}

variable "hub_private_endpoint_subnet_prefix" {
  description = "Address prefix for Private Endpoint subnet"
  type        = string
  default     = "172.16.6.0/24"
}

# ExpressRoute Configuration
variable "express_route_circuit_bandwidth" {
  description = "ExpressRoute circuit bandwidth in Mbps"
  type        = string
  default     = "50"
}

variable "express_route_circuit_peering_location" {
  description = "ExpressRoute circuit peering location"
  type        = string
  default     = "Singapore"
}

variable "express_route_circuit_service_provider" {
  description = "ExpressRoute circuit service provider"
  type        = string
  default     = "Equinix"
}

variable "express_route_gateway_sku" {
  description = "ExpressRoute Gateway SKU. Note: Standard SKU does NOT support BGP. Use HighPerformance, UltraPerformance, or ErGw1AZ/ErGw2AZ/ErGw3AZ for BGP support with Route Server"
  type        = string
  default     = "ErGw1AZ"

  validation {
    condition = contains([
      "Standard", "HighPerformance", "UltraPerformance",
      "ErGw1AZ", "ErGw2AZ", "ErGw3AZ"
    ], var.express_route_gateway_sku)
    error_message = "ExpressRoute Gateway SKU must be one of: Standard, HighPerformance, UltraPerformance, ErGw1AZ, ErGw2AZ, ErGw3AZ. Note: Standard does not support BGP."
  }
}

variable "vpn_gateway_sku" {
  description = "VPN Gateway SKU. Choose Basic for simple scenarios, VpnGw1-5 for production with BGP support"
  type        = string
  default     = "Basic"

  validation {
    condition = contains([
      "Basic", "VpnGw1", "VpnGw2", "VpnGw3", "VpnGw4", "VpnGw5",
      "VpnGw1AZ", "VpnGw2AZ", "VpnGw3AZ", "VpnGw4AZ", "VpnGw5AZ"
    ], var.vpn_gateway_sku)
    error_message = "VPN Gateway SKU must be one of: Basic, VpnGw1-5, or VpnGw1AZ-5AZ for zone-redundant gateways."
  }
}

# NVA Configuration
variable "nva_vm_size" {
  description = "Size of the NVA virtual machine"
  type        = string
  default     = "Standard_B2s"
}

variable "nva_admin_username" {
  description = "Admin username for NVA VM"
  type        = string
  default     = "azureuser"
}

variable "nva_admin_password" {
  description = "Admin password for NVA VM"
  type        = string
  default     = "P@55w0rd1234"
  sensitive   = true
}

# Squid Proxy Configuration
variable "squid_vm_size" {
  description = "Size of the Squid proxy virtual machine"
  type        = string
  default     = "Standard_B2s"
}

variable "squid_admin_username" {
  description = "Admin username for Squid proxy VM"
  type        = string
  default     = "azureuser"
}

variable "squid_admin_password" {
  description = "Admin password for Squid proxy VM"
  type        = string
  default     = "P@55w0rd1234"
  sensitive   = true
}

# Feature Flags
variable "deploy_hub_vnet" {
  description = "Deploy Hub Virtual Network and its core components"
  type        = bool
  default     = false
}

variable "deploy_expressroute_gateway" {
  description = "Deploy ExpressRoute Virtual Network Gateway"
  type        = bool
  default     = false
}

variable "deploy_vpn_gateway" {
  description = "Deploy Site-to-Site VPN Gateway"
  type        = bool
  default     = false
}

variable "deploy_expressroute_connection" {
  description = "Deploy ExpressRoute Connection (requires deploy_expressroute_gateway to be true)"
  type        = bool
  default     = false
}

variable "deploy_route_server" {
  description = "Deploy Azure Route Server"
  type        = bool
  default     = false
}

variable "deploy_linux_nva" {
  description = "Deploy Linux NVA"
  type        = bool
  default     = false
}

variable "deploy_bastion" {
  description = "Deploy Azure Bastion"
  type        = bool
  default     = false
}

variable "deploy_squid_proxy" {
  description = "Deploy Linux Squid proxy VM in hub"
  type        = bool
  default     = false
}

variable "route_server_branch_to_branch" {
  description = "Enable branch-to-branch traffic on Azure Route Server"
  type        = bool
  default     = false
}

variable "deploy_hub_firewall" {
  description = "Deploy Azure Firewall in the hub VNet"
  type        = bool
  default     = false
}

variable "hub_firewall_force_tunneling" {
  description = "Enable force tunneling on Azure Firewall to route all internet traffic back to on-premises"
  type        = bool
  default     = false
}

variable "hub_firewall_explicit_proxy" {
  description = "Enable explicit proxy on Hub Azure Firewall for advanced web filtering and monitoring"
  type        = bool
  default     = false
}

variable "hub_firewall_explicit_proxy_nat" {
  description = "Enable NAT rules for Hub Azure Firewall explicit proxy ports to allow external access"
  type        = bool
  default     = false
}

variable "hub_firewall_explicit_proxy_http_port" {
  description = "HTTP port for Hub Azure Firewall explicit proxy"
  type        = number
  default     = 8080
}

variable "hub_firewall_explicit_proxy_https_port" {
  description = "HTTPS port for Hub Azure Firewall explicit proxy"
  type        = number
  default     = 8443
}

variable "hub_firewall_dns_proxy_enabled" {
  description = "Enable DNS proxy on Hub Azure Firewall"
  type        = bool
  default     = false
}

variable "hub_firewall_arc_rules" {
  description = "Enable Azure Arc connectivity firewall policy rules for Azure Arc connected machine agents"
  type        = bool
  default     = false
}

variable "hub_firewall_private_ip" {
  description = "Private IP address for the Hub Azure Firewall in the AzureFirewallSubnet"
  type        = string
  default     = "172.16.0.4"
}

variable "deploy_arc_private_link_scope" {
  description = "Enable private link scope for Azure Arc connectivity (requires private DNS zones and private endpoints)"
  type        = bool
  default     = false
}

# Azure Arc Service Principal Configuration
variable "deploy_arc_service_principal" {
  description = "Whether to deploy Azure AD service principal for Arc onboarding"
  type        = bool
  default     = false
}

variable "arc_service_principal_subscription_scope" {
  description = "Whether to assign Azure Connected Machine Onboarding role at subscription level (true) or resource group level (false)"
  type        = bool
  default     = false
}

# Azure Monitor Private Link Scope Configuration
variable "deploy_azure_monitor_private_link_scope" {
  description = "Deploy Azure Monitor Private Link Scope"
  type        = bool
  default     = false
}

variable "azure_monitor_query_access_mode" {
  description = "Access mode for Azure Monitor query operations. Valid values are 'Open' or 'PrivateOnly'"
  type        = string
  default     = "Open"
  validation {
    condition     = contains(["Open", "PrivateOnly"], var.azure_monitor_query_access_mode)
    error_message = "The azure_monitor_query_access_mode must be either 'Open' or 'PrivateOnly'."
  }
}

variable "azure_monitor_ingestion_access_mode" {
  description = "Access mode for Azure Monitor ingestion operations. Valid values are 'Open' or 'PrivateOnly'"
  type        = string
  default     = "Open"
  validation {
    condition     = contains(["Open", "PrivateOnly"], var.azure_monitor_ingestion_access_mode)
    error_message = "The azure_monitor_ingestion_access_mode must be either 'Open' or 'PrivateOnly'."
  }
}

# Agentic App Feature Flags
variable "deploy_agentic_app" {
  description = "Deploy the EOL agentic web app and dependencies"
  type        = bool
  default     = false
}

variable "agentic_app_name" {
  description = "Base name for the agentic app"
  type        = string
  default     = "eol-agentic"
}

variable "deploy_agentic_private_endpoints" {
  description = "Create private endpoints for agentic app services (e.g., AOAI)"
  type        = bool
  default     = false
}

variable "deploy_aoai" {
  description = "Deploy Azure OpenAI account for agentic app"
  type        = bool
  default     = false
}

# ============================================================================
# COSMOS DB CONFIGURATION FOR AGENTIC APP
# ============================================================================

variable "deploy_cosmos_db" {
  description = "Deploy Azure Cosmos DB for EOL response caching in agentic app"
  type        = bool
  default     = false
}

variable "cosmos_db_serverless" {
  description = "Use Cosmos DB serverless instead of provisioned throughput"
  type        = bool
  default     = false
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

# ============================================================================
# AZURE CONTAINER REGISTRY CONFIGURATION FOR AGENTIC APP
# ============================================================================

variable "deploy_acr" {
  description = "Deploy Azure Container Registry for agentic app container images"
  type        = bool
  default     = false
}

variable "acr_sku" {
  description = "Azure Container Registry SKU"
  type        = string
  default     = "Basic"
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }
}

variable "acr_admin_enabled" {
  description = "Enable admin user for Azure Container Registry"
  type        = bool
  default     = true
}

# ============================================================================
# BING SEARCH API CONFIGURATION FOR AGENTIC APP
# ============================================================================

variable "deploy_bing_search" {
  description = "Deploy Bing Search API (Cognitive Services) for agentic app web searches - DEPRECATED"
  type        = bool
  default     = false
}

variable "bing_search_sku_name" {
  description = "Bing Search Cognitive Services SKU"
  type        = string
  default     = "S0"
  validation {
    condition     = contains(["S0", "S1", "S2", "S3", "S4", "S5", "S6"], var.bing_search_sku_name)
    error_message = "Bing Search SKU must be a valid Cognitive Services SKU (S0-S6)."
  }
}

# ============================================================================
# AZURE AI AGENT SERVICE VARIABLES
# ============================================================================

variable "deploy_azure_ai_agent" {
  description = "Deploy Azure AI Agent Service (Modern replacement for Bing Search)"
  type        = bool
  default     = true
}

variable "azure_ai_foundry_sku_name" {
  description = "Azure AI Foundry SKU"
  type        = string
  default     = "S0"
  validation {
    condition     = contains(["F0", "S0", "S1", "S2", "S3", "S4", "S5", "S6"], var.azure_ai_foundry_sku_name)
    error_message = "Azure AI Foundry SKU must be a valid Cognitive Services SKU (F0, S0-S6)."
  }
}

variable "azure_ai_foundry_name" {
  description = "Azure AI Foundry service name (optional, will be generated if not provided)"
  type        = string
  default     = null
}

# ============================================================================
# AZURE AI SRE AGENT VARIABLES
# ============================================================================

variable "azure_ai_sre_agent_name" {
  description = "Name of existing Azure AI SRE agent to connect to (e.g., gccsreagent)"
  type        = string
  default     = "gccsreagent"
}

variable "azure_ai_sre_agent_id" {
  description = "Resource ID of existing Azure AI SRE agent"
  type        = string
  default     = null
}

# ==============================================================================
# CONTAINER APPS CONFIGURATION
# ==============================================================================
# Azure Container Apps for modern containerized workloads with MCP sidecar

variable "deploy_container_apps" {
  description = "Deploy Container Apps instead of App Service (mutually exclusive with deploy_agentic_app)"
  type        = bool
  default     = false
}

variable "container_apps_app_image" {
  description = "Container image for the main application"
  type        = string
  default     = "your-acr.azurecr.io/eol-app:latest"
}

variable "container_apps_mcp_image" {
  description = "Container image for Azure MCP Server sidecar"
  type        = string
  default     = "mcr.microsoft.com/azure-mcp:latest"
}

variable "container_apps_app_cpu" {
  description = "CPU allocation for main app container"
  type        = number
  default     = 1.0
}

variable "container_apps_app_memory" {
  description = "Memory allocation for main app container"
  type        = string
  default     = "2Gi"
}

variable "container_apps_mcp_cpu" {
  description = "CPU allocation for MCP sidecar container"
  type        = number
  default     = 0.5
}

variable "container_apps_mcp_memory" {
  description = "Memory allocation for MCP sidecar container"
  type        = string
  default     = "1Gi"
}

variable "container_apps_min_replicas" {
  description = "Minimum number of container replicas"
  type        = number
  default     = 1
}

variable "container_apps_max_replicas" {
  description = "Maximum number of container replicas"
  type        = number
  default     = 3
}

variable "container_apps_internal_lb_enabled" {
  description = "Use internal load balancer for Container Apps"
  type        = bool
  default     = false
}

variable "container_apps_zone_redundancy_enabled" {
  description = "Enable zone redundancy for Container Apps Environment"
  type        = bool
  default     = false
}

variable "aoai_deployment_name" {
  description = "Azure OpenAI default deployment name"
  type        = string
  default     = "gpt-4o-mini"
}

variable "aoai_model_name" {
  description = "Azure OpenAI model name for deployment"
  type        = string
  default     = "gpt-4o-mini"
}

variable "aoai_model_version" {
  description = "Azure OpenAI model version"
  type        = string
  default     = "2024-07-18"
}

// variable "deploy_search" removed (Azure AI Search no longer used)

variable "log_analytics_workspace_retention_days" {
  description = "Log Analytics workspace data retention in days (30-730)"
  type        = number
  default     = 30
  validation {
    condition     = var.log_analytics_workspace_retention_days >= 30 && var.log_analytics_workspace_retention_days <= 730
    error_message = "Log Analytics workspace retention must be between 30 and 730 days."
  }
}

variable "log_analytics_workspace_sku" {
  description = "Log Analytics workspace pricing tier"
  type        = string
  default     = "PerGB2018"
  validation {
    condition     = contains(["Free", "Standard", "Premium", "PerNode", "PerGB2018", "Standalone", "CapacityReservation"], var.log_analytics_workspace_sku)
    error_message = "Log Analytics workspace SKU must be one of: Free, Standard, Premium, PerNode, PerGB2018, Standalone, CapacityReservation."
  }
}

# Azure Monitor Data Collection Configuration
variable "deploy_linux_dce_dcr" {
  description = "Deploy Linux Data Collection Endpoint and Data Collection Rule for Azure Monitor"
  type        = bool
  default     = false
}

variable "deploy_windows_dce_dcr" {
  description = "Deploy Windows Data Collection Endpoint and Data Collection Rule for Azure Monitor"
  type        = bool
  default     = false
}

# BGP Configuration
variable "enable_expressroute_gateway_bgp" {
  description = "Enable BGP on ExpressRoute Gateway and Route Server"
  type        = bool
  default     = false
}

variable "enable_vpn_gateway_bgp" {
  description = "Enable BGP on VPN Gateway (requires non-Basic SKU)"
  type        = bool
  default     = false
}

variable "nva_bgp_asn" {
  description = "BGP ASN for the Network Virtual Appliance (NVA)"
  type        = number
  default     = 65001
}

variable "nva_bgp_advertised_routes" {
  description = "List of routes to advertise via BGP from the Network Virtual Appliance (NVA)"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

# Advanced BGP Configuration
variable "expressroute_gateway_bgp_asn" {
  description = "BGP ASN for the ExpressRoute Gateway (default: 65515)"
  type        = number
  default     = 65515
}

variable "vpn_gateway_bgp_asn" {
  description = "BGP ASN for the VPN Gateway (default: 65516)"
  type        = number
  default     = 65516
}

variable "enable_bgp_route_propagation" {
  description = "Enable BGP route propagation on route tables"
  type        = bool
  default     = false
}

variable "bgp_peering_address" {
  description = "Custom BGP peering address for ExpressRoute Gateway (optional)"
  type        = string
  default     = null
}

# On-premises Configuration
variable "deploy_onprem_vnet" {
  description = "Deploy on-premises simulation VNet"
  type        = bool
  default     = false
}

variable "onprem_vnet_address_space" {
  description = "Address space for on-premises simulation VNet"
  type        = list(string)
  default     = ["192.168.0.0/16"]
}

variable "onprem_workload_subnet_prefix" {
  description = "Address prefix for on-premises workload subnet"
  type        = string
  default     = "192.168.0.0/24"
}

variable "deploy_hub_onprem_peering" {
  description = "Deploy VNet peering between Hub and on-premises VNets (requires both deploy_hub_vnet and deploy_onprem_vnet to be true)"
  type        = bool
  default     = false
}

# On-premises Windows Server Configuration
variable "deploy_onprem_windows_server_2025" {
  description = "Deploy Windows Server 2025 in on-premises VNet workload subnet"
  type        = bool
  default     = false
}

variable "deploy_onprem_windows_server_2016" {
  description = "Deploy Windows Server 2016 in on-premises VNet workload subnet"
  type        = bool
  default     = false
}

variable "onprem_windows_vm_size" {
  description = "VM size for on-premises Windows Server"
  type        = string
  default     = "Standard_B2s"
}

variable "onprem_windows_admin_username" {
  description = "Admin username for on-premises Windows Server"
  type        = string
  default     = "azureuser"
}

variable "onprem_windows_admin_password" {
  description = "Admin password for on-premises Windows Server"
  type        = string
  sensitive   = true
  default     = "P@55w0rd1234"
}

variable "onprem_windows_arc_onboarding" {
  description = "Enable Azure Arc onboarding for on-premises Windows Server 2025 with enhanced configuration"
  type        = bool
  default     = false
}

variable "onprem_windows_arc_auto_upgrade" {
  description = "Enable automatic upgrade for Azure Connected Machine Agent"
  type        = bool
  default     = false
}

variable "onprem_windows_vpn_setup" {
  description = "Setup Site-to-Site VPN tunnel from on-premises Windows server to Azure VPN Gateway"
  type        = bool
  default     = false
}

variable "onprem_vpn_shared_key" {
  description = "Shared key for Site-to-Site VPN connection"
  type        = string
  sensitive   = true
  default     = "VpnSharedKey123!"
}

variable "enable_local_network_gateway_bgp" {
  description = "Enable BGP on the Local Network Gateway"
  type        = bool
  default     = false
}

variable "local_network_gateway_bgp_asn" {
  description = "BGP ASN for the Local Network Gateway"
  type        = number
  default     = 65515
}

# Gen VNet Configuration
variable "deploy_gen_vnet" {
  description = "Deploy Gen VNet"
  type        = bool
  default     = false
}

variable "gen_vnet_address_space" {
  description = "Address space for Gen VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "gen_workload_subnet_prefix" {
  description = "Address prefix for Gen workload subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "route_internet_to_nongen_firewall" {
  description = "Route Gen workload subnet internet traffic (0.0.0.0/0) through Non-Gen firewall (requires deploy_gen_vnet and deploy_nongen_firewall to be true)"
  type        = bool
  default     = false
}

# Non-Gen VNet Configuration
variable "deploy_nongen_vnet" {
  description = "Deploy Non-Gen VNet"
  type        = bool
  default     = false
}

variable "deploy_nongen_firewall" {
  description = "Deploy Non-Gen Azure Firewall (requires deploy_nongen_vnet to be true)"
  type        = bool
  default     = false
}

variable "nongen_firewall_agentic_rules" {
  description = "Enable firewall policy rules required for the agentic app including Oryx SDK CDN"
  type        = bool
  default     = false
}

variable "nongen_firewall_dns_proxy_enabled" {
  description = "Enable DNS proxy on Non-Gen Azure Firewall"
  type        = bool
  default     = false
}

variable "deploy_hub_nongen_peering" {
  description = "Deploy VNet peering between Hub and Non-Gen VNets (requires both deploy_hub_vnet and deploy_nongen_vnet to be true)"
  type        = bool
  default     = false
}

variable "deploy_gen_nongen_peering" {
  description = "Deploy VNet peering between Gen and Non-Gen VNets (requires both deploy_gen_vnet and deploy_nongen_vnet to be true)"
  type        = bool
  default     = false
}

variable "deploy_hub_gen_peering" {
  description = "Deploy VNet peering between Hub and Gen VNets (requires both deploy_hub_vnet and deploy_gen_vnet to be true)"
  type        = bool
  default     = false
}

variable "nongen_vnet_address_space" {
  description = "Address space for Non-Gen VNet"
  type        = list(string)
  default     = ["100.0.0.0/16"]
}

variable "nongen_firewall_subnet_prefix" {
  description = "Address prefix for Non-Gen Azure Firewall Subnet"
  type        = string
  default     = "100.0.0.0/25"
}

variable "nongen_web_subnet_prefix" {
  description = "Address prefix for Non-Gen Web Subnet"
  type        = string
  default     = "100.0.1.0/24"
}

variable "nongen_app_subnet_prefix" {
  description = "Address prefix for Non-Gen App Subnet"
  type        = string
  default     = "100.0.2.0/24"
}

variable "nongen_db_subnet_prefix" {
  description = "Address prefix for Non-Gen Database Subnet"
  type        = string
  default     = "100.0.3.0/24"
}

variable "nongen_apim_subnet_prefix" {
  description = "Address prefix for Non-Gen API Management Subnet"
  type        = string
  default     = "100.0.4.0/24"
}

variable "nongen_avd_subnet_prefix" {
  description = "Address prefix for Non-Gen Azure Virtual Desktop Subnet"
  type        = string
  default     = "100.0.5.0/24"
}

variable "nongen_private_endpoint_subnet_prefix" {
  description = "Address prefix for Non-Gen Private Endpoint Subnet"
  type        = string
  default     = "100.0.6.0/24"
}

# Storage Configuration
variable "deploy_script_storage" {
  description = "Deploy storage account for scripts and VM extensions"
  type        = bool
  default     = false
}

# ==============================================================================
# AZURE VIRTUAL DESKTOP (AVD) CONFIGURATION
# ==============================================================================

variable "deploy_nongen_avd" {
  description = "Flag to control deployment of the Non-Gen Azure Virtual Desktop environment"
  type        = bool
  default     = false
}

# AVD Host Pool Configuration
variable "avd_host_pool_type" {
  description = "Type of AVD host pool (Personal or Pooled)"
  type        = string
  default     = "Pooled"
  validation {
    condition     = contains(["Personal", "Pooled"], var.avd_host_pool_type)
    error_message = "Host pool type must be either 'Personal' or 'Pooled'."
  }
}

variable "avd_host_pool_load_balancer_type" {
  description = "Load balancer type for AVD host pool (BreadthFirst, DepthFirst, or Persistent)"
  type        = string
  default     = "BreadthFirst"
  validation {
    condition     = contains(["BreadthFirst", "DepthFirst", "Persistent"], var.avd_host_pool_load_balancer_type)
    error_message = "Load balancer type must be 'BreadthFirst', 'DepthFirst', or 'Persistent'."
  }
}

variable "avd_host_pool_maximum_sessions" {
  description = "Maximum number of sessions allowed per AVD session host"
  type        = number
  default     = 10
}

variable "avd_host_pool_start_vm_on_connect" {
  description = "Whether to start AVD VMs automatically when users connect"
  type        = bool
  default     = false
}

# AVD Session Host Configuration
variable "avd_session_host_count" {
  description = "Number of AVD session host VMs to create"
  type        = number
  default     = 2
}

variable "avd_session_host_vm_size" {
  description = "VM size for AVD session hosts"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "avd_session_host_admin_username" {
  description = "Admin username for AVD session host VMs"
  type        = string
  default     = "avdadmin"
}

variable "avd_session_host_admin_password" {
  description = "Admin password for AVD session host VMs"
  type        = string
  sensitive   = true
  default     = "P@55w0rd1234"
}

variable "avd_session_host_image_publisher" {
  description = "Publisher of the AVD VM image"
  type        = string
  default     = "MicrosoftWindowsDesktop"
}

variable "avd_session_host_image_offer" {
  description = "Offer of the AVD VM image"
  type        = string
  default     = "Windows-11"
}

variable "avd_session_host_image_sku" {
  description = "SKU of the AVD VM image"
  type        = string
  default     = "win11-22h2-avd"
}

# AVD Enterprise Features
variable "avd_aad_join_enabled" {
  description = "Whether to enable Azure AD join for AVD session hosts"
  type        = bool
  default     = false
}

variable "avd_fslogix_enabled" {
  description = "Whether to enable FSLogix profile containers for AVD"
  type        = bool
  default     = false
}

variable "avd_private_endpoints_enabled" {
  description = "Whether to enable private endpoints for AVD storage accounts"
  type        = bool
  default     = false
}

# AVD FSLogix Configuration
variable "avd_fslogix_storage_account_tier" {
  description = "Storage account tier for FSLogix (Standard or Premium)"
  type        = string
  default     = "Standard"
  validation {
    condition     = contains(["Standard", "Premium"], var.avd_fslogix_storage_account_tier)
    error_message = "FSLogix storage account tier must be either 'Standard' or 'Premium'."
  }
}

variable "avd_fslogix_storage_account_replication" {
  description = "Storage account replication type for FSLogix"
  type        = string
  default     = "LRS"
  validation {
    condition     = contains(["LRS", "ZRS"], var.avd_fslogix_storage_account_replication)
    error_message = "FSLogix storage account replication must be 'LRS' or 'ZRS'."
  }
}

variable "avd_fslogix_file_share_quota_gb" {
  description = "Quota for FSLogix file share in GB"
  type        = number
  default     = 1024
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "Production"
    Project     = "Azure-Landing-Zone"
    Owner       = "IT-Team"
  }
}