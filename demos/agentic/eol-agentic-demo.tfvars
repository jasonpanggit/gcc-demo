# ==============================================================================
# EOL Agentic App with Azure Arc Demo Configuration
# ==============================================================================
# This configuration demonstrates:
# 1. EOL Agentic Application - Software inventory management with AI capabilities
# 2. Azure Arc Connectivity - External server onboarding through hub firewall
# 3. Secure Architecture - Private endpoints, firewall rules, and monitoring
#
# DEPLOYMENT: terraform apply -var-file="credentials.tfvars" -var-file="demos/agentic/eol-agentic-demo.tfvars"
# ESTIMATED COST: ~$200/month
# DEPLOYMENT TIME: ~25-35 minutes

# ==============================================================================
# GENERAL CONFIGURATION
# ==============================================================================
# Base settings that affect all deployed resources
location     = "Australia East" # Primary Azure region for all resources
environment  = "demo"           # Environment tag and naming suffix
project_name = "gcc"            # Project identifier for resource naming

# ==============================================================================
# CORE INFRASTRUCTURE
# ==============================================================================
# Shared infrastructure components used by both Arc and Agentic services

# Hub VNet - Central networking hub
deploy_hub_vnet = true

# Azure Bastion - Secure VM management
deploy_bastion = true

# Azure Monitor - Centralized logging and monitoring
deploy_azure_monitor_private_link_scope = true
azure_monitor_query_access_mode         = "Open"      # Open or PrivateOnly
azure_monitor_ingestion_access_mode     = "Open"      # Open or PrivateOnly

# Script Storage - Required for Arc onboarding and VM extensions
deploy_script_storage = true

# ==============================================================================
# HUB FIREWALL CONFIGURATION
# ==============================================================================
# Hub firewall configuration - Currently disabled as hub firewall is not deployed
# Only nongen firewall is deployed in the current Azure environment

deploy_hub_firewall                    = false # Hub firewall
hub_firewall_explicit_proxy            = false # Explicit proxy 
hub_firewall_explicit_proxy_nat        = false # Explicit proxy NAT 
hub_firewall_dns_proxy_enabled         = false # DNS proxy
hub_firewall_explicit_proxy_http_port  = 8080  # HTTP port
hub_firewall_explicit_proxy_https_port = 8443  # HTTPS port 
hub_firewall_arc_rules                 = false # Arc rules

# ==============================================================================
# AGENTIC APPLICATION CONFIGURATION
# ==============================================================================
# EOL software inventory management application with AI capabilities

# Non-Gen VNet - Dedicated network for agentic workloads
deploy_nongen_vnet = true

# Non-Gen Firewall - Dedicated firewall for agentic app egress
deploy_nongen_firewall = true

# Non-Gen Firewall DNS proxy - Enable to match deployed configuration
nongen_firewall_dns_proxy_enabled = true

# Enable agentic firewall rules for Azure App Service dependencies
nongen_firewall_agentic_rules = true

# Agentic Application
deploy_agentic_app = true
agentic_app_name   = "eol-agentic"

# AI Services for Agentic App
deploy_aoai      = true # Azure OpenAI for AI capabilities
deploy_cosmos_db = true # Azure Cosmos DB for EOL response caching (80%+ confidence)

# Private Endpoints for Agentic Services
deploy_agentic_private_endpoints = true

# ==============================================================================
# AZURE ARC CONFIGURATION
# ==============================================================================
# Azure Arc setup for external server onboarding through hub firewall

# Arc Private Connectivity
deploy_arc_private_link_scope = false # Private link scope for Arc services

# Arc Service Principal for automated onboarding
deploy_arc_service_principal             = true # Service principal for Arc onboarding
arc_service_principal_subscription_scope = true # Subscription-level permissions

# ==============================================================================
# ON-PREMISES SIMULATION 
# ==============================================================================
# Optional simulated on-premises environment for testing Arc connectivity
# Currently disabled as these resources are not deployed in Azure

# On-premises VNet and connectivity
deploy_onprem_vnet        = false # On-premises simulation VNet - NOT DEPLOYED
deploy_hub_onprem_peering = false # Hub-to-OnPrem VNet peering - NOT DEPLOYED

# Windows Server with Azure Arc (for testing)
deploy_onprem_windows_server_2025 = false # Windows Server 2025 VM - NOT DEPLOYED
onprem_windows_arc_onboarding     = false # Arc onboarding via Hub Firewall proxy - NOT DEPLOYED
onprem_windows_arc_auto_upgrade   = false # Automatic Arc agent upgrades - NOT DEPLOYED