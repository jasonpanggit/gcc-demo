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

# Script Storage - Required for Arc onboarding and VM extensions
deploy_script_storage = true

# ==============================================================================
# HUB FIREWALL CONFIGURATION
# ==============================================================================
# Azure Firewall with explicit proxy for both Agentic app egress and Arc onboarding

deploy_hub_firewall                    = true
hub_firewall_explicit_proxy            = true
hub_firewall_explicit_proxy_nat        = true
hub_firewall_dns_proxy_enabled         = true
hub_firewall_explicit_proxy_http_port  = 8080
hub_firewall_explicit_proxy_https_port = 8443
hub_firewall_arc_rules                 = true

# ==============================================================================
# AGENTIC APPLICATION CONFIGURATION
# ==============================================================================
# EOL software inventory management application with AI capabilities

# Non-Gen VNet - Dedicated network for agentic workloads
deploy_nongen_vnet = true

# Non-Gen Firewall - Dedicated firewall for agentic app egress
deploy_nongen_firewall = true

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
deploy_arc_private_link_scope = true # Private link scope for Arc services

# Arc Service Principal for automated onboarding
deploy_arc_service_principal             = true # Service principal for Arc onboarding
arc_service_principal_subscription_scope = true # Subscription-level permissions

# ==============================================================================
# ON-PREMISES SIMULATION 
# ==============================================================================
# Optional simulated on-premises environment for testing Arc connectivity
# Enable these if you want to test with a simulated on-premises Windows Server

# On-premises VNet and connectivity
deploy_onprem_vnet        = true # On-premises simulation VNet
deploy_hub_onprem_peering = true # Hub-to-OnPrem VNet peering

# Windows Server with Azure Arc (for testing)
deploy_onprem_windows_server_2025 = true # Windows Server 2025 VM
onprem_windows_arc_onboarding     = true # Arc onboarding via Hub Firewall proxy
onprem_windows_arc_auto_upgrade   = true # Automatic Arc agent upgrades