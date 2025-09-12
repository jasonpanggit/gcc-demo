# ==============================================================================
# Hub-Spoke Basic Network Architecture Demo Configuration
# ==============================================================================
# This configuration demonstrates a complete hub-spoke network topology with:
# - Hub VNet 
# - On-Prem VNet for non-generative workloads with network segmentation
# - VNet peering 
#
# HOW TO DEPLOY THIS DEMO:
# 1. Prerequisites: Ensure you have Azure CLI logged in and Terraform installed
# 2. Credentials: Copy credentials.tfvars.example to credentials.tfvars and update with your values
# 3. Initialize: terraform init
# 4. Plan: terraform plan -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-onprem-basic-demo.tfvars"
# 5. Deploy: terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-onprem-basic-demo.tfvars"
# 6. Cleanup: terraform destroy -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-onprem-basic-demo.tfvars"
#
# ESTIMATED COST: 0/month
# DEPLOYMENT TIME: ~5 minutes
#
# For detailed documentation, see: demos/hub-spoke/README.md

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
deploy_hub_vnet = true # Deploy hub VNet with all standard subnets

# ==============================================================================
# ON-PREM VNET INFRASTRUCTURE
# ==============================================================================
# Dedicated On-Prem VNet for specialized workloads requiring separate network controls

# On-Prem VNet Core Settings
deploy_onprem_vnet = true # Deploy On-Prem VNet

# ==============================================================================
# VNET PEERING CONFIGURATION
# ==============================================================================

# Hub-to-OnPrem Peering
deploy_hub_onprem_peering = true # Enable bidirectional peering between Hub and On-Prem VNets