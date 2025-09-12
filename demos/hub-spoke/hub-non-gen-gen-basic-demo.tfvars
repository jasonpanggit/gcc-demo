# ==============================================================================
# Hub-Spoke Basic Network Architecture Demo Configuration
# ==============================================================================
# This configuration demonstrates a complete hub-spoke network topology with:
# - Hub VNet 
# - Non-GEN VNet for non-generative workloads with network segmentation
# - GEN VNet for non-generative workloads with network segmentation
# - VNet peering 
#
# HOW TO DEPLOY THIS DEMO:
# 1. Prerequisites: Ensure you have Azure CLI logged in and Terraform installed
# 2. Credentials: Copy credentials.tfvars.example to credentials.tfvars and update with your values
# 3. Initialize: terraform init
# 4. Plan: terraform plan -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars"
# 5. Deploy: terraform apply -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars"
# 6. Cleanup: terraform destroy -var-file="credentials.tfvars" -var-file="demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars"
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
# NON-GEN VNET INFRASTRUCTURE
# ==============================================================================
# Dedicated Non-Gen VNet for specialized workloads requiring separate network controls

# Non-Gen VNet Core Settings
deploy_nongen_vnet = true # Deploy Non-Gen VNet

# ==============================================================================
# GEN VNET INFRASTRUCTURE
# ==============================================================================
# Dedicated GEN VNet for generative workloads requiring separate network controls

# GEN VNet Core Settings
deploy_gen_vnet = true # Deploy GEN VNet

# ==============================================================================
# VNET PEERING CONFIGURATION
# ==============================================================================
# Cross-VNet connectivity for unified network architecture

# Hub-to-NonGen Peering
deploy_hub_nongen_peering  = true # Enable bidirectional peering between Hub and Non-Gen VNets
deploy_non_gen_gen_peering = true # Enable bidirectional peering between Non-Gen and GEN VNets
