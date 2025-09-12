# ==============================================================================
# Azure ExpressRoute Landing Zone Demo Configuration
# ==============================================================================
# This configuration demonstrates a complete ExpressRoute-enabled environment with:
# - Hub VNet with ExpressRoute Gateway and Route Server
# - Advanced BGP routing with Network Virtual Appliances
# - ExpressRoute circuit configuration and connection
# - Azure Firewall with force tunneling for hybrid traffic control
# - Private connectivity between on-premises and Azure via ExpressRoute
#
# HOW TO DEPLOY THIS DEMO:
# 1. Prerequisites: ExpressRoute circuit from service provider (Equinix, etc.)
# 2. Credentials: Copy credentials.tfvars.example to credentials.tfvars and update with your values
# 3. Initialize: terraform init
# 4. Plan: terraform plan -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
# 5. Deploy: terraform apply -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
# 6. Configure: Provide Service Key to ExpressRoute provider
# 7. Cleanup: terraform destroy -var-file="credentials.tfvars" -var-file="demos/expressroute/expressroute-demo.tfvars"
#
# ESTIMATED COST: ~$800-2,000/month (depending on circuit bandwidth)
# DEPLOYMENT TIME: ~30-45 minutes (plus provider setup time)
#
# ⚠️  IMPORTANT: Requires actual ExpressRoute circuit provisioning
# For detailed documentation, see: demos/expressroute/README.md

# ==============================================================================
# GENERAL CONFIGURATION
# ==============================================================================
# Base settings that affect all deployed resources
location     = "Australia East" # Primary Azure region for all resources
environment  = "demo"           # Environment tag and naming suffix
project_name = "gcc"            # Project identifier for resource naming

# ==============================================================================
# HUB VNET INFRASTRUCTURE
# ==============================================================================
# Core hub networking components providing centralized connectivity and routing

# Hub VNet and Essential Services
deploy_hub_vnet     = true # Deploy hub VNet with all standard subnets
deploy_hub_firewall = true # Deploy Azure Firewall for traffic inspection and control
deploy_bastion      = true # Deploy Azure Bastion for secure VM management

# ==============================================================================
# EXPRESSROUTE CONFIGURATION
# ==============================================================================
# ExpressRoute components for private connectivity to Azure

# ExpressRoute Gateway
deploy_expressroute_gateway    = true      # Deploy ExpressRoute Virtual Network Gateway
deploy_expressroute_connection = false     # Demo mode - connection simulation only
express_route_gateway_sku      = "ErGw1AZ" # Zone-redundant gateway SKU with BGP support

# ExpressRoute Circuit Settings (for reference/simulation)
express_route_circuit_bandwidth        = "100"       # Mbps bandwidth
express_route_circuit_peering_location = "Singapore" # ExpressRoute peering location
express_route_circuit_service_provider = "Equinix"   # Service provider

# ==============================================================================
# AZURE ROUTE SERVER & BGP CONFIGURATION
# ==============================================================================
# Advanced routing capabilities with BGP support

# Route Server Deployment
deploy_route_server           = true # Deploy Azure Route Server for BGP routing
route_server_branch_to_branch = true # Enable branch-to-branch connectivity

# BGP Configuration
enable_expressroute_gateway_bgp = true  # Enable BGP routing capabilities
enable_bgp_route_propagation    = true  # Enable BGP route propagation on route tables
expressroute_gateway_bgp_asn    = 65515 # Azure default ASN for ExpressRoute Gateway

# ==============================================================================
# NETWORK VIRTUAL APPLIANCES
# ==============================================================================
# Network Virtual Appliances for advanced routing and traffic control

# Linux NVA with BGP
deploy_linux_nva = true # Deploy Linux NVA for BGP peering with Route Server

# NVA BGP Configuration
nva_bgp_asn               = 65001           # BGP ASN for the NVA
nva_bgp_advertised_routes = ["10.0.0.0/16"] # Routes advertised by NVA

# ==============================================================================
# AZURE FIREWALL ADVANCED FEATURES
# ==============================================================================
# Enhanced Azure Firewall capabilities for hybrid environments

# Force Tunneling (ExpressRoute Scenario)
hub_firewall_force_tunneling = false # Set to true for full on-premises inspection

# DNS and Proxy Configuration
hub_firewall_dns_proxy_enabled = true # Enable DNS proxy for centralized DNS resolution

# ==============================================================================
# ARCHITECTURE SUMMARY
# ==============================================================================
# This configuration creates:
# 1. Hub VNet (172.16.0.0/16) with ExpressRoute Gateway and Route Server
# 2. ExpressRoute Gateway (ErGw1AZ) for private connectivity
# 3. Azure Route Server with BGP for advanced routing
# 4. Linux NVA with BGP peering to Route Server
# 5. Azure Firewall for traffic inspection and security
# 6. Azure Bastion for secure VM management
#
# ExpressRoute Connectivity Flow:
# On-Premises → ExpressRoute Circuit → ExpressRoute Gateway → Hub VNet → Spoke VNets
#
# BGP Routing Flow:
# ExpressRoute Gateway ↔ Route Server ↔ Linux NVA (BGP Peering)

# ==============================================================================
# DEPLOYMENT INSTRUCTIONS
# ==============================================================================
# 1. Copy credentials.tfvars.example to credentials.tfvars
# 2. Update credentials.tfvars with your Azure credentials
# 3. Deploy with: terraform apply -var-file="credentials.tfvars" -var-file="expressroute-demo.tfvars"
#
# Note: This demo creates the ExpressRoute Gateway but not the actual ExpressRoute
# circuit connection. For production, you would need to:
# 1. Order an ExpressRoute circuit from a service provider
# 2. Set deploy_expressroute_connection = true
# 3. Configure the ExpressRoute circuit details
