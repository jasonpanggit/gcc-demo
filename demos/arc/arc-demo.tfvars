# ==============================================================================
# Azure Arc Landing Zone Demo Configuration
# ==============================================================================
# This configuration demonstrates a complete Azure Arc-enabled environment with:
# - Hub VNet with Azure Firewall and explicit proxy
# - On-premises simulation VNet with Windows Server 2025
# - Azure Arc connectivity with private endpoints and service principal
# - Azure Monitor Private Link Scope for secure monitoring
# - Full Hub-to-OnPrem connectivity for Arc onboarding through private endpoints
#
# HOW TO DEPLOY THIS DEMO:
# 1. Prerequisites: Ensure you have Azure CLI logged in and Terraform installed
# 2. Credentials: Copy credentials.tfvars.example to credentials.tfvars and update with your values
# 3. Initialize: terraform init
# 4. Plan: terraform plan -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
# 5. Deploy: terraform apply -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
# 6. Cleanup: terraform destroy -var-file="credentials.tfvars" -var-file="demos/arc/arc-demo.tfvars"
#
# ESTIMATED COST: ~$150/month
# DEPLOYMENT TIME: ~30-40 minutes
#
# For detailed documentation, see: demos/arc/README.md

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
# Core hub networking components providing centralized connectivity and security

# Hub VNet and Essential Services
deploy_hub_vnet     = true # Deploy hub VNet with all standard subnets
deploy_hub_firewall = true # Deploy Azure Firewall Premium for traffic inspection
deploy_bastion      = true # Deploy Azure Bastion for secure VM management

# ==============================================================================
# AZURE FIREWALL ADVANCED FEATURES
# ==============================================================================
# Enhanced Azure Firewall capabilities for enterprise-grade security

# Explicit Proxy Configuration
hub_firewall_explicit_proxy     = true # Enable explicit proxy for advanced web filtering
hub_firewall_explicit_proxy_nat = true # Enable NAT for explicit proxy for onboarding via public endpoints (requires generation of onboarding script via Azure Portal)
hub_firewall_dns_proxy_enabled  = true # Enable DNS proxy for centralized DNS resolution
hub_firewall_arc_rules          = true # Enable Azure Arc connectivity firewall rules

# ==============================================================================
# AZURE ARC CONFIGURATION
# ==============================================================================
# Complete Azure Arc setup with private connectivity and service principal

# Arc Private Connectivity
deploy_arc_private_link_scope = true # Deploy private link scope for Arc services (secure connectivity)

# Arc Service Principal (for automated onboarding)
deploy_arc_service_principal             = true # Create service principal for Arc onboarding
arc_service_principal_subscription_scope = true # Grant subscription-level permissions

# ==============================================================================
# AZURE MONITOR PRIVATE LINK SCOPE
# ==============================================================================
# Secure monitoring configuration for Arc-enabled servers
deploy_azure_monitor_private_link_scope = true # Deploy Azure Monitor Private Link Scope

# ==============================================================================
# ON-PREMISES SIMULATION
# ==============================================================================
# Simulated on-premises environment for testing Arc connectivity

# On-premises VNet
deploy_onprem_vnet = true # Deploy on-premises simulation VNet

# Windows Server with Azure Arc
deploy_onprem_windows_server_2025 = true # Deploy Windows Server 2025 VM
onprem_windows_arc_onboarding     = true # Enable Arc onboarding via Hub Firewall proxy
onprem_windows_arc_auto_upgrade   = true # Enable automatic Arc agent upgrades

# ==============================================================================
# NETWORK CONNECTIVITY
# ==============================================================================
# VNet peering for Hub-to-OnPremises connectivity
deploy_hub_onprem_peering = true # Enable peering between Hub and On-premises VNets

# ==============================================================================
# ARCHITECTURE SUMMARY
# ==============================================================================
# This configuration creates:
# 1. Hub VNet (172.16.0.0/16) with Azure Firewall and Bastion
# 2. On-premises VNet (192.168.0.0/16) with Windows Server 2025
# 3. Azure Arc private endpoints for secure Arc connectivity
# 4. Service principal for automated Arc onboarding
# 5. Azure Monitor Private Link Scope for secure monitoring
# 6. Hub Firewall explicit proxy for Arc traffic routing
# 7. VNet peering for Hub-OnPrem connectivity
#
# Arc Connectivity Flow:
# Windows Server → Hub Firewall Proxy → Arc Private Endpoints → Azure Arc Services

# ==============================================================================
# STORAGE CONFIGURATION
# ==============================================================================
# Storage account for scripts and VM extensions

# Script Storage
deploy_script_storage = true # Required for Arc onboarding with VM extensions

# ==============================================================================
# DEPLOYMENT INSTRUCTIONS
# ==============================================================================
# 1. Copy credentials.tfvars.example to credentials.tfvars
# 2. Update credentials.tfvars with your Azure credentials
# 3. Deploy with: terraform apply -var-file="credentials.tfvars" -var-file="arc-demo.tfvars"
