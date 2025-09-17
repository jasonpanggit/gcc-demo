# ============================================================================
# GCC DEMO - MAIN CONFIGURATION
# ============================================================================
# Modular Azure infrastructure with 7 specialized modules:
# networking, compute, gateways, firewall, storage, identity, arc
# ============================================================================

# ============================================================================
# DATA SOURCES
# ============================================================================

data "azurerm_client_config" "current" {}

# ============================================================================
# RESOURCE GROUP
# ============================================================================

resource "azurerm_resource_group" "rg_hub" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.location

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# ============================================================================
# NETWORKING MODULE - VNets, Subnets, Peering
# ============================================================================

module "networking" {
  source = "./modules/networking"
  count  = var.deploy_hub_vnet || var.deploy_onprem_vnet || var.deploy_gen_vnet || var.deploy_nongen_vnet ? 1 : 0

  project_name                       = var.project_name
  environment                        = var.environment
  location                           = azurerm_resource_group.rg_hub.location
  resource_group_name                = azurerm_resource_group.rg_hub.name
  hub_vnet_address_space             = var.hub_vnet_address_space
  hub_gateway_subnet_prefix          = var.hub_gateway_subnet_prefix
  hub_firewall_subnet_prefix         = var.hub_firewall_subnet_prefix
  hub_route_server_subnet_prefix     = var.hub_route_server_subnet_prefix
  hub_nva_subnet_prefix              = var.hub_nva_subnet_prefix
  hub_bastion_subnet_prefix          = var.hub_bastion_subnet_prefix
  hub_squid_subnet_prefix            = var.hub_squid_subnet_prefix
  hub_private_endpoint_subnet_prefix = var.hub_private_endpoint_subnet_prefix
  deploy_expressroute_gateway        = var.deploy_expressroute_gateway
  deploy_vpn_gateway                 = var.deploy_vpn_gateway
  deploy_hub_firewall                = var.deploy_hub_firewall
  deploy_route_server                = var.deploy_route_server
  deploy_linux_nva                   = var.deploy_linux_nva
  deploy_bastion                     = var.deploy_bastion
  deploy_squid_proxy                 = var.deploy_squid_proxy
  deploy_arc_private_link_scope      = var.deploy_arc_private_link_scope
  deploy_agentic_app                 = var.deploy_agentic_app

  # Route table related variables
  deploy_nongen_vnet        = var.deploy_nongen_vnet
  deploy_nongen_firewall    = var.deploy_nongen_firewall
  deploy_gen_vnet           = var.deploy_gen_vnet
  nongen_vnet_address_space = var.nongen_vnet_address_space
  gen_vnet_address_space    = var.gen_vnet_address_space

  # Spoke networks variables
  nongen_firewall_subnet_prefix           = var.nongen_firewall_subnet_prefix
  nongen_private_endpoint_subnet_prefix   = var.nongen_private_endpoint_subnet_prefix
  nongen_app_subnet_prefix                = var.nongen_app_subnet_prefix
  gen_workload_subnet_prefix              = var.gen_workload_subnet_prefix
  deploy_onprem_vnet                      = var.deploy_onprem_vnet
  onprem_vnet_address_space               = var.onprem_vnet_address_space
  onprem_workload_subnet_prefix           = var.onprem_workload_subnet_prefix
  deploy_onprem_windows_server_2025       = var.deploy_onprem_windows_server_2025
  deploy_onprem_windows_server_2016       = var.deploy_onprem_windows_server_2016
  deploy_gen_nongen_peering               = var.deploy_gen_nongen_peering
  deploy_hub_gen_peering                  = var.deploy_hub_gen_peering
  deploy_hub_onprem_peering               = var.deploy_hub_onprem_peering
  deploy_hub_nongen_peering               = var.deploy_hub_nongen_peering
  deploy_azure_monitor_private_link_scope = var.deploy_azure_monitor_private_link_scope
}

# ============================================================================
# GATEWAYS MODULE
# ============================================================================

module "gateways" {
  source = "./modules/gateways"
  count  = (var.deploy_expressroute_gateway || var.deploy_vpn_gateway) ? 1 : 0

  project_name                           = var.project_name
  environment                            = var.environment
  location                               = azurerm_resource_group.rg_hub.location
  resource_group_name                    = azurerm_resource_group.rg_hub.name
  gateway_subnet_id                      = var.deploy_hub_vnet ? module.networking[0].gateway_subnet_id : ""
  deploy_hub_vnet                        = var.deploy_hub_vnet
  deploy_expressroute_gateway            = var.deploy_expressroute_gateway
  deploy_expressroute_connection         = var.deploy_expressroute_connection
  deploy_vpn_gateway                     = var.deploy_vpn_gateway
  deploy_onprem_vnet                     = var.deploy_onprem_vnet
  onprem_windows_vpn_setup               = var.onprem_windows_vpn_setup
  expressroute_gateway_sku               = var.express_route_gateway_sku
  enable_expressroute_gateway_bgp        = var.enable_expressroute_gateway_bgp
  expressroute_gateway_bgp_asn           = var.expressroute_gateway_bgp_asn
  vpn_gateway_sku                        = var.vpn_gateway_sku
  enable_vpn_gateway_bgp                 = var.enable_vpn_gateway_bgp
  vpn_gateway_bgp_asn                    = var.vpn_gateway_bgp_asn
  express_route_circuit_service_provider = var.express_route_circuit_service_provider
  express_route_circuit_peering_location = var.express_route_circuit_peering_location
  express_route_circuit_bandwidth        = var.express_route_circuit_bandwidth
  onprem_vnet_address_space              = var.onprem_vnet_address_space
  onprem_vpn_shared_key                  = var.onprem_vpn_shared_key
  enable_local_network_gateway_bgp       = var.enable_local_network_gateway_bgp
  local_network_gateway_bgp_asn          = var.local_network_gateway_bgp_asn
  onprem_windows_2016_private_ip         = var.deploy_onprem_windows_server_2016 ? module.compute[0].onprem_windows_2016_private_ip : null

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [module.networking, module.compute]
}

# ============================================================================
# FIREWALL MODULE
# ============================================================================

module "firewall" {
  source = "./modules/firewall"
  count  = (var.deploy_hub_firewall || var.deploy_nongen_firewall) ? 1 : 0

  project_name                           = var.project_name
  environment                            = var.environment
  location                               = azurerm_resource_group.rg_hub.location
  resource_group_name                    = azurerm_resource_group.rg_hub.name
  firewall_subnet_id                     = var.deploy_hub_vnet ? module.networking[0].firewall_subnet_id : ""
  deploy_hub_vnet                        = var.deploy_hub_vnet
  deploy_hub_firewall                    = var.deploy_hub_firewall
  hub_firewall_dns_proxy_enabled         = var.hub_firewall_dns_proxy_enabled
  hub_firewall_explicit_proxy            = var.hub_firewall_explicit_proxy
  hub_firewall_explicit_proxy_nat        = var.hub_firewall_explicit_proxy_nat
  hub_firewall_explicit_proxy_http_port  = var.hub_firewall_explicit_proxy_http_port
  hub_firewall_explicit_proxy_https_port = var.hub_firewall_explicit_proxy_https_port
  hub_firewall_arc_rules                 = var.hub_firewall_arc_rules

  # Non-Gen firewall variables
  deploy_nongen_vnet                   = var.deploy_nongen_vnet
  deploy_nongen_firewall               = var.deploy_nongen_firewall
  nongen_firewall_subnet_id            = var.deploy_hub_vnet && var.deploy_nongen_vnet ? module.networking[0].nongen_firewall_subnet_id : null
  nongen_firewall_avd_rules            = var.deploy_nongen_avd
  nongen_firewall_agentic_rules        = var.nongen_firewall_agentic_rules
  nongen_firewall_dns_proxy_enabled    = var.nongen_firewall_dns_proxy_enabled
  deploy_agentic_app                   = var.deploy_agentic_app
  onprem_vnet_address_space            = var.onprem_vnet_address_space
  hub_vnet_address_space               = var.hub_vnet_address_space

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [module.networking]
}

# ============================================================================
# ROUTING MODULE - Route Tables with Firewall Dependencies
# ============================================================================

module "routing" {
  source = "./modules/routing"
  count  = var.deploy_hub_vnet && var.deploy_hub_firewall ? 1 : 0

  project_name        = var.project_name
  environment         = var.environment
  location            = azurerm_resource_group.rg_hub.location
  resource_group_name = azurerm_resource_group.rg_hub.name

  # Deployment flags
  deploy_hub_vnet                   = var.deploy_hub_vnet
  deploy_expressroute_gateway       = var.deploy_expressroute_gateway
  deploy_vpn_gateway                = var.deploy_vpn_gateway
  deploy_hub_firewall               = var.deploy_hub_firewall
  deploy_nongen_vnet                = var.deploy_nongen_vnet
  deploy_nongen_firewall            = var.deploy_nongen_firewall
  deploy_gen_vnet                   = var.deploy_gen_vnet
  deploy_squid_proxy                = var.deploy_squid_proxy
  hub_firewall_force_tunneling      = var.hub_firewall_force_tunneling
  route_internet_to_nongen_firewall = var.route_internet_to_nongen_firewall

  # Firewall IP addresses - using actual outputs from firewall module
  hub_firewall_private_ip    = var.deploy_hub_firewall && length(module.firewall) > 0 ? module.firewall[0].firewall_private_ip : var.hub_firewall_private_ip
  nongen_firewall_private_ip = var.deploy_nongen_firewall && length(module.firewall) > 0 ? module.firewall[0].nongen_firewall_private_ip : null

  # Network configuration
  nva_bgp_advertised_routes = var.nva_bgp_advertised_routes
  nongen_vnet_address_space = var.nongen_vnet_address_space
  gen_vnet_address_space    = var.gen_vnet_address_space

  # Subnet IDs from networking module
  gateway_subnet_id                   = var.deploy_hub_vnet ? module.networking[0].gateway_subnet_id : ""
  firewall_subnet_id                  = var.deploy_hub_vnet ? module.networking[0].firewall_subnet_id : ""
  squid_subnet_id                     = var.deploy_hub_vnet ? module.networking[0].squid_subnet_id : ""
  gen_workload_subnet_id              = var.deploy_gen_vnet ? module.networking[0].gen_workload_subnet_id : ""
  nongen_appsvc_integration_subnet_id = var.deploy_nongen_vnet ? module.networking[0].nongen_appsvc_integration_subnet_id : ""

  depends_on = [module.networking, module.firewall]
}

# ============================================================================
# STORAGE MODULE
# ============================================================================

module "storage" {
  source = "./modules/storage"
  count  = var.deploy_script_storage ? 1 : 0

  project_name                  = var.project_name
  environment                   = var.environment
  location                      = azurerm_resource_group.rg_hub.location
  resource_group_name           = azurerm_resource_group.rg_hub.name
  deploy_script_storage         = var.deploy_script_storage
  onprem_windows_arc_onboarding = var.onprem_windows_arc_onboarding
  onprem_windows_vpn_setup      = var.onprem_windows_vpn_setup
  deploy_vpn_gateway            = var.deploy_vpn_gateway

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# ============================================================================
# COMPUTE MODULE - Windows Server 2016/2025 VMs
# ============================================================================

module "compute" {
  source = "./modules/compute"
  count  = var.deploy_onprem_windows_server_2025 || var.deploy_onprem_windows_server_2016 || var.deploy_linux_nva || var.deploy_squid_proxy ? 1 : 0

  project_name        = var.project_name
  environment         = var.environment
  location            = azurerm_resource_group.rg_hub.location
  resource_group_name = azurerm_resource_group.rg_hub.name

  # Deployment flags
  deploy_route_server               = var.deploy_route_server
  deploy_linux_nva                  = var.deploy_linux_nva
  deploy_squid_proxy                = var.deploy_squid_proxy
  deploy_onprem_vnet                = var.deploy_onprem_vnet
  deploy_onprem_windows_server_2025 = var.deploy_onprem_windows_server_2025
  deploy_onprem_windows_server_2016 = var.deploy_onprem_windows_server_2016

  # Subnet IDs from networking module
  nva_subnet_id             = var.deploy_hub_vnet && var.deploy_linux_nva ? coalesce(module.networking[0].nva_subnet_id, "") : ""
  squid_subnet_id           = var.deploy_hub_vnet && var.deploy_squid_proxy ? coalesce(module.networking[0].squid_subnet_id, "") : ""
  onprem_workload_subnet_id = var.deploy_hub_vnet && var.deploy_onprem_vnet ? coalesce(module.networking[0].onprem_workload_subnet_id, "") : ""

  # NSG IDs from networking module
  # NSGs disabled; do not pass NSG IDs
  nva_nsg_id            = ""
  squid_nsg_id          = ""
  onprem_windows_nsg_id = ""

  # VM Configuration
  nva_vm_size                   = var.nva_vm_size
  nva_admin_username            = var.nva_admin_username
  nva_admin_password            = var.nva_admin_password
  squid_vm_size                 = var.squid_vm_size
  squid_admin_username          = var.squid_admin_username
  squid_admin_password          = var.squid_admin_password
  onprem_windows_vm_size        = var.onprem_windows_vm_size
  onprem_windows_admin_username = var.onprem_windows_admin_username
  onprem_windows_admin_password = var.onprem_windows_admin_password

  # BGP Configuration
  nva_bgp_asn               = var.nva_bgp_asn
  route_server_ip_1         = var.deploy_route_server && var.deploy_hub_vnet && length(module.networking) > 0 && length(module.networking[0].route_server_virtual_router_ips) > 0 ? module.networking[0].route_server_virtual_router_ips[0] : ""
  route_server_ip_2         = var.deploy_route_server && var.deploy_hub_vnet && length(module.networking) > 0 && length(module.networking[0].route_server_virtual_router_ips) > 1 ? module.networking[0].route_server_virtual_router_ips[1] : ""
  nva_bgp_advertised_routes = var.nva_bgp_advertised_routes

  # Additional required variables
  onprem_vnet_id           = var.deploy_onprem_vnet && var.deploy_hub_vnet && length(module.networking) > 0 ? module.networking[0].onprem_vnet_id : ""
  onprem_vm_admin_password = var.onprem_windows_admin_password
  storage_account_name     = var.deploy_script_storage ? module.storage[0].storage_account_name : ""
  storage_container_name   = var.deploy_script_storage ? module.storage[0].storage_container_name : ""
  storage_scripts_sas_url  = var.deploy_script_storage ? module.storage[0].scripts_sas_token : ""
  onprem_address_space     = var.onprem_vnet_address_space
  hub_address_space        = var.hub_vnet_address_space

  # Arc onboarding command (only meaningful if Arc onboarding enabled)
  arc_setup_command = var.onprem_windows_arc_onboarding && var.deploy_onprem_windows_server_2025 && var.deploy_script_storage && var.deploy_arc_private_link_scope ? join(" ", [
    "powershell.exe", "-ExecutionPolicy", "Bypass", "-File", "./arc/windows-server-2025-arc-setup.ps1",
    "-ServicePrincipalId", "\"${module.arc[0].service_principal_client_id}\"",
    "-ServicePrincipalSecret", "\"${module.arc[0].service_principal_secret}\"",
    "-SubscriptionId", "\"${data.azurerm_client_config.current.subscription_id}\"",
    "-ResourceGroup", "\"${azurerm_resource_group.rg_hub.name}\"",
    "-TenantId", "\"${data.azurerm_client_config.current.tenant_id}\"",
    "-Location", "\"${azurerm_resource_group.rg_hub.location}\"",
    "-ArcPrivateLinkScopeId", "\"${module.arc[0].private_link_scope_id}\""
  ]) : ""

  # VPN Gateway Configuration
  deploy_vpn_gateway       = var.deploy_vpn_gateway
  onprem_vpn_shared_key    = var.onprem_vpn_shared_key
  onprem_windows_vpn_setup = var.onprem_windows_vpn_setup

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  depends_on = [module.networking, module.storage]
}

# ============================================================================
# MONITORING MODULE
# ============================================================================

module "monitoring" {
  source = "./modules/monitoring"
  count  = var.deploy_azure_monitor_private_link_scope ? 1 : 0

  project_name                            = var.project_name
  environment                             = var.environment
  location                                = azurerm_resource_group.rg_hub.location
  resource_group_name                     = azurerm_resource_group.rg_hub.name
  deploy_hub_vnet                         = var.deploy_hub_vnet
  deploy_azure_monitor_private_link_scope = var.deploy_azure_monitor_private_link_scope
  log_analytics_workspace_sku             = var.log_analytics_workspace_sku
  log_analytics_workspace_retention_days  = var.log_analytics_workspace_retention_days
  private_endpoint_subnet_id              = var.deploy_hub_vnet ? module.networking[0].private_endpoint_subnet_id : null
  hub_vnet_id                             = var.deploy_hub_vnet ? module.networking[0].vnet_id : null
  deploy_onprem_vnet                      = var.deploy_onprem_vnet
  onprem_windows_arc_onboarding           = var.onprem_windows_arc_onboarding
  onprem_vnet_id                          = var.deploy_onprem_vnet && var.deploy_hub_vnet ? module.networking[0].onprem_vnet_id : null
  azure_monitor_query_access_mode         = var.azure_monitor_query_access_mode
  azure_monitor_ingestion_access_mode     = var.azure_monitor_ingestion_access_mode

  depends_on = [module.networking]
}

# ============================================================================
# AGENTIC APP MODULE - EOL Agentic App
# ============================================================================

module "agentic" {
  source = "./modules/agentic"
  count  = var.deploy_agentic_app ? 1 : 0

  project_name                      = var.project_name
  environment                       = var.environment
  location                          = azurerm_resource_group.rg_hub.location
  resource_group_name               = azurerm_resource_group.rg_hub.name
  deploy_agentic_app                = var.deploy_agentic_app
  agentic_app_name                  = var.agentic_app_name
  deploy_nongen_vnet                = var.deploy_nongen_vnet
  nongen_vnet_id                    = var.deploy_nongen_vnet ? module.networking[0].nongen_vnet_id : null
  nongen_private_endpoint_subnet_id = var.deploy_nongen_vnet ? module.networking[0].nongen_private_endpoint_subnet_id : null
  # Use unified naming for App Service VNet integration subnet
  nongen_app_subnet_id  = var.deploy_nongen_vnet ? module.networking[0].nongen_appsvc_integration_subnet_id : null
  workspace_resource_id = length(module.monitoring) > 0 ? module.monitoring[0].log_analytics_workspace_id : null
  workspace_guid        = length(module.monitoring) > 0 ? module.monitoring[0].log_analytics_workspace_guid : null

  # Private endpoints for services
  deploy_aoai                      = var.deploy_aoai
  deploy_agentic_private_endpoints = var.deploy_agentic_private_endpoints

  # Cosmos DB configuration for EOL caching
  deploy_cosmos_db             = var.deploy_cosmos_db
  cosmos_db_serverless         = var.cosmos_db_serverless
  cosmos_db_consistency_level  = var.cosmos_db_consistency_level
  cosmos_db_throughput         = var.cosmos_db_throughput
  cosmos_db_automatic_failover = var.cosmos_db_automatic_failover
  cosmos_db_geo_location       = var.cosmos_db_geo_location

  # Azure Container Registry configuration
  deploy_acr       = var.deploy_acr
  acr_sku          = var.acr_sku
  acr_admin_enabled = var.acr_admin_enabled

  # Bing Search API configuration (DEPRECATED)
  deploy_bing_search    = var.deploy_bing_search
  bing_search_sku_name  = var.bing_search_sku_name

  # Azure AI Agent Service configuration (Modern replacement)
  deploy_azure_ai_agent        = var.deploy_azure_ai_agent
  azure_ai_foundry_sku_name    = var.azure_ai_foundry_sku_name
  azure_ai_foundry_name        = var.azure_ai_foundry_name

  enable_teams_integration = false

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "EOL Agentic App"
  }

  depends_on = [module.networking, module.firewall, module.monitoring]
}

# ============================================================================
# ARC MODULE
# ============================================================================

module "arc" {
  source                                   = "./modules/arc"
  count                                    = var.deploy_arc_private_link_scope ? 1 : 0
  project_name                             = var.project_name
  environment                              = var.environment
  location                                 = azurerm_resource_group.rg_hub.location
  resource_group_id                        = azurerm_resource_group.rg_hub.id
  subscription_id                          = data.azurerm_client_config.current.subscription_id
  arc_service_principal_subscription_scope = var.arc_service_principal_subscription_scope
  deploy_arc_private_link_scope            = var.deploy_arc_private_link_scope
  deploy_hub_vnet                          = var.deploy_hub_vnet
  hub_vnet_id                              = var.deploy_hub_vnet ? module.networking[0].vnet_id : null
  onprem_vnet_id                           = var.deploy_onprem_vnet && var.deploy_hub_vnet ? module.networking[0].onprem_vnet_id : null
  private_endpoint_subnet_id               = var.deploy_hub_vnet ? module.networking[0].private_endpoint_subnet_id : null
  deploy_onprem_vnet                       = var.deploy_onprem_vnet

  depends_on = [
    module.networking,
    module.storage
  ]
}

# ============================================================================
# AVD MODULE - Azure Virtual Desktop for Non-Gen Environment
# ============================================================================

module "avd" {
  source = "./modules/avd"
  count  = var.deploy_nongen_avd ? 1 : 0

  # Basic Configuration
  project_name      = var.project_name
  environment       = var.environment
  location          = azurerm_resource_group.rg_hub.location
  resource_group_id = azurerm_resource_group.rg_hub.id

  # Network Configuration - Deploy in Non-Gen VNet
  vnet_id                        = var.deploy_nongen_vnet ? module.networking[0].nongen_vnet_id : (var.deploy_hub_vnet ? module.networking[0].vnet_id : "")
  vnet_name                      = var.deploy_nongen_vnet ? module.networking[0].nongen_vnet_name : (var.deploy_hub_vnet ? module.networking[0].vnet_name : "")
  vnet_resource_group            = azurerm_resource_group.rg_hub.name
  session_host_subnet_prefix     = var.nongen_avd_subnet_prefix
  private_endpoint_subnet_prefix = var.nongen_private_endpoint_subnet_prefix

  # Non-Gen Firewall Integration
  deploy_nongen_firewall = var.deploy_nongen_firewall
  nongen_firewall_ip     = var.deploy_nongen_firewall && length(module.firewall) > 0 ? module.firewall[0].nongen_firewall_private_ip : null

  # Host Pool Configuration
  host_pool_type                = var.avd_host_pool_type
  host_pool_load_balancer_type  = var.avd_host_pool_load_balancer_type
  host_pool_maximum_sessions    = var.avd_host_pool_maximum_sessions
  host_pool_start_vm_on_connect = var.avd_host_pool_start_vm_on_connect

  # Session Host Configuration
  session_host_count           = var.avd_session_host_count
  session_host_vm_size         = var.avd_session_host_vm_size
  session_host_admin_username  = var.avd_session_host_admin_username
  session_host_admin_password  = var.avd_session_host_admin_password
  session_host_image_publisher = var.avd_session_host_image_publisher
  session_host_image_offer     = var.avd_session_host_image_offer
  session_host_image_sku       = var.avd_session_host_image_sku

  # Enterprise Features
  aad_join_enabled          = var.avd_aad_join_enabled
  fslogix_enabled           = var.avd_fslogix_enabled
  private_endpoints_enabled = var.avd_private_endpoints_enabled

  # FSLogix Configuration
  fslogix_storage_account_tier        = var.avd_fslogix_storage_account_tier
  fslogix_storage_account_replication = var.avd_fslogix_storage_account_replication
  fslogix_file_share_quota_gb         = var.avd_fslogix_file_share_quota_gb

  # Monitoring Configuration
  log_analytics_workspace_id = var.deploy_azure_monitor_private_link_scope ? module.monitoring[0].log_analytics_workspace_id : null

  # Tags
  tags = merge(var.tags, {
    Workload  = "AVD"
    Component = "VirtualDesktop"
  })

  depends_on = [
    module.networking,
    module.firewall,
    module.monitoring
  ]
}

# ============================================================================
# VPN EXTENSION - Windows Server 2016 VPN Setup (Avoids Circular Dependencies)
# ============================================================================

resource "azurerm_virtual_machine_extension" "vpn_setup_windows_2016" {
  count                      = var.deploy_onprem_windows_server_2016 && var.onprem_windows_vpn_setup && var.deploy_vpn_gateway ? 1 : 0
  name                       = "VPN-Setup"
  virtual_machine_id         = module.compute[0].onprem_windows_2016_vm_id
  publisher                  = "Microsoft.Compute"
  type                       = "CustomScriptExtension"
  type_handler_version       = "1.10"
  auto_upgrade_minor_version = true

  settings = jsonencode({
    fileUris = [
      "https://${module.storage[0].storage_account_name}.blob.core.windows.net/scripts/vpn/windows-server-2016-vpn-setup.ps1${module.storage[0].scripts_sas_token}"
    ]
  })

  protected_settings = jsonencode({
    commandToExecute = "powershell.exe -ExecutionPolicy Unrestricted -File ./vpn/windows-server-2016-vpn-setup.ps1 -AzureVpnGatewayPublicIP '${module.gateways[0].vpn_gateway_public_ip}' -SharedKey '${var.onprem_vpn_shared_key}' -AzureNetworkCIDR '${var.hub_vnet_address_space[0]}' -ConnectionName 'Azure-S2S-VPN'"
  })

  timeouts {
    create = "15m"
    update = "15m"
    delete = "10m"
  }

  depends_on = [
    module.compute,
    module.gateways,
    module.storage,
    module.networking,
    module.firewall
  ]

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "VPN Setup"
    OS          = "Windows Server 2016"
  }
}

# ==========================================================================
# ARC EXTENSION - Windows Server 2025 Azure Arc Onboarding
# ==========================================================================

resource "azurerm_virtual_machine_extension" "arc_setup_windows_2025" {
  count                      = var.deploy_onprem_vnet && var.deploy_onprem_windows_server_2025 && var.onprem_windows_arc_onboarding && var.deploy_script_storage && var.deploy_arc_private_link_scope ? 1 : 0
  name                       = "ArcSetup"
  virtual_machine_id         = module.compute[0].onprem_windows_vm_id
  publisher                  = "Microsoft.Compute"
  type                       = "CustomScriptExtension"
  type_handler_version       = "1.10"
  auto_upgrade_minor_version = true

  settings = jsonencode({
    fileUris = [
      "https://${module.storage[0].storage_account_name}.blob.core.windows.net/scripts/arc/windows-server-2025-arc-setup.ps1${module.storage[0].scripts_sas_token}"
    ]
    # Forces extension re-run when script content or versioned path changes
    scriptHash = filesha256("${path.root}/scripts/arc/windows-server-2025-arc-setup.ps1")
  })

  protected_settings = jsonencode({
    # Simple direct execution with escaped parameters
    commandToExecute = "powershell.exe -ExecutionPolicy Bypass -File arc\\windows-server-2025-arc-setup.ps1 -ServicePrincipalId \"${module.arc[0].service_principal_client_id}\" -ServicePrincipalSecret \"${module.arc[0].service_principal_secret}\" -SubscriptionId \"${data.azurerm_client_config.current.subscription_id}\" -ResourceGroup \"${azurerm_resource_group.rg_hub.name}\" -TenantId \"${data.azurerm_client_config.current.tenant_id}\" -Location \"${azurerm_resource_group.rg_hub.location}\" -ArcPrivateLinkScopeId \"${module.arc[0].private_link_scope_id}\" -ProxyUrl \"${var.deploy_hub_firewall && length(module.firewall) > 0 && module.firewall[0].firewall_proxy_url != null ? module.firewall[0].firewall_proxy_url : ""}\""
  })

  timeouts {
    create = "10m"
    update = "10m"
    delete = "10m"
  }

  depends_on = [
    module.compute,
    module.arc,
    module.storage,
    module.networking,
    module.monitoring,
    module.firewall
  ]

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Purpose     = "Azure Arc Setup"
    OS          = "Windows Server 2025"
  }
}

# ============================================================================
# OUTPUTS
# ============================================================================

output "resource_group_name" {
  description = "The name of the resource group"
  value       = azurerm_resource_group.rg_hub.name
}

output "vnet_name" {
  description = "The name of the hub virtual network"
  value       = var.deploy_hub_vnet ? module.networking[0].vnet_name : null
}

# ============================================================================
# AVD OUTPUTS
# ============================================================================

output "avd_workspace_name" {
  description = "Name of the AVD workspace"
  value       = var.deploy_nongen_avd ? module.avd[0].workspace_name : null
}

output "avd_host_pool_name" {
  description = "Name of the AVD host pool"
  value       = var.deploy_nongen_avd ? module.avd[0].host_pool_name : null
}

output "avd_session_host_vm_names" {
  description = "Names of the AVD session host VMs"
  value       = var.deploy_nongen_avd ? module.avd[0].session_host_vm_names : []
}

output "avd_fslogix_storage_account_name" {
  description = "Name of the FSLogix storage account"
  value       = var.deploy_nongen_avd ? module.avd[0].fslogix_storage_account_name : null
}
