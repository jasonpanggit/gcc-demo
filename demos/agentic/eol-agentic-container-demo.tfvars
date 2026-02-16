# ============================================================================
# EOL AGENTIC APP DEMO - CONTAINER APPS DEPLOYMENT
# ============================================================================
# Modern containerized deployment with Azure Container Apps
# Multi-container architecture: Main app + Azure MCP sidecar
# Cost: ~$200-250/month | Deploy Time: ~35-45 minutes
# ============================================================================

# ==============================================================================
# GENERAL CONFIGURATION
# ==============================================================================
environment  = "prod"
project_name = "eol-agentic"
location     = "Australia East"

# ==============================================================================
# NETWORK CONFIGURATION - NON-GEN VNET
# ==============================================================================
deploy_hub_vnet               = false
deploy_gen_vnet               = false
deploy_nongen_vnet            = true
deploy_onprem_vnet            = false
nongen_vnet_address_space     = ["10.20.0.0/16"]
nongen_app_subnet_prefix      = "10.20.1.0/24"   # For Container Apps Environment
nongen_private_endpoint_subnet_prefix = "10.20.2.0/24"

# Peering Configuration
deploy_hub_nongen_peering     = false
deploy_hub_gen_peering        = false
deploy_gen_nongen_peering     = false
deploy_hub_onprem_peering     = false

# ==============================================================================
# CONTAINER APPS DEPLOYMENT (Primary)
# ==============================================================================
deploy_container_apps         = true
deploy_agentic_app            = false  # Mutually exclusive with Container Apps

# Container Images (Update with your ACR details after first deployment)
container_apps_app_image      = "your-acr.azurecr.io/eol-app:latest"
container_apps_mcp_image      = "mcr.microsoft.com/azure-mcp:latest"

# Resource Allocation
container_apps_app_cpu        = 1.0   # 1 vCPU for main app
container_apps_app_memory     = "2Gi" # 2 GiB RAM
container_apps_mcp_cpu        = 0.5   # 0.5 vCPU for MCP sidecar
container_apps_mcp_memory     = "1Gi" # 1 GiB RAM

# Scaling Configuration
container_apps_min_replicas   = 1     # Cost optimization: 1 minimum
container_apps_max_replicas   = 3     # Scale up to 3 for high load

# Networking
container_apps_internal_lb_enabled       = false  # Public access
container_apps_zone_redundancy_enabled   = false  # Cost optimization

# ==============================================================================
# AZURE SERVICES CONFIGURATION
# ==============================================================================

# Azure OpenAI
deploy_aoai                   = true
aoai_deployment_name          = "gpt-4o-mini"
aoai_model_name               = "gpt-4o-mini"
aoai_model_version            = "2024-07-18"

# Azure Cosmos DB (EOL Response Caching)
deploy_cosmos_db              = true
cosmos_db_serverless          = true   # Cost-effective for variable workloads
cosmos_db_consistency_level   = "Session"
cosmos_db_throughput          = null   # Serverless mode
cosmos_db_automatic_failover  = false  # Single region for cost savings
cosmos_db_geo_location        = null   # No geo-replication

# Azure Container Registry
deploy_acr                    = true
acr_sku                       = "Basic"  # $0.167/day
acr_admin_enabled             = true     # Enable for initial setup

# Azure AI Agent Service (Modern Bing Search replacement)
deploy_azure_ai_agent         = true
azure_ai_foundry_sku_name     = "S0"

# Azure AI SRE Agent (Existing gccsreagent)
azure_ai_sre_agent_name       = "gccsreagent"
azure_ai_sre_agent_id         = null  # Optional: Full resource ID if needed

# Private Endpoints (Recommended for production)
deploy_agentic_private_endpoints = true

# ==============================================================================
# MONITORING & LOGS
# ==============================================================================
deploy_azure_monitor_private_link_scope = true
log_analytics_workspace_retention_days  = 30

# ==============================================================================
# DEPRECATED/UNUSED SERVICES
# ==============================================================================
deploy_bing_search            = false  # Deprecated - use deploy_azure_ai_agent
deploy_hub_firewall           = false
deploy_nongen_firewall        = false
deploy_vpn_gateway            = false
deploy_expressroute_gateway   = false
deploy_route_server           = false
deploy_bastion                = false
deploy_linux_nva              = false
deploy_squid_proxy            = false
deploy_arc_private_link_scope = false
deploy_nongen_avd             = false

# ==============================================================================
# COMPUTE (Not needed for Container Apps)
# ==============================================================================
deploy_onprem_windows_server_2016 = false
deploy_onprem_windows_server_2025 = false
deploy_script_storage             = false

# ==============================================================================
# DEPLOYMENT NOTES
# ==============================================================================
# 
# FIRST TIME DEPLOYMENT:
# 1. Run terraform apply with this tfvars
# 2. Build and push container image:
#    ```bash
#    export ACR_NAME=$(terraform output -raw agentic_acr_name)
#    export ACR_LOGIN_SERVER=$(terraform output -raw agentic_acr_login_server)
#    
#    # Build image
#    cd app/agentic/eol
#    docker build -t ${ACR_LOGIN_SERVER}/eol-app:v1 .
#    
#    # Login to ACR
#    az acr login --name ${ACR_NAME}
#    
#    # Push image
#    docker push ${ACR_LOGIN_SERVER}/eol-app:v1
#    ```
# 
# 3. Update this tfvars with actual ACR image URL
# 4. Run terraform apply again to deploy container with actual image
#
# ENVIRONMENT VARIABLES:
# All required environment variables are automatically configured:
# - AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT
# - AZURE_COSMOS_DB_ENDPOINT, AZURE_COSMOS_DB_DATABASE, AZURE_COSMOS_DB_CONTAINER
# - LOG_ANALYTICS_WORKSPACE_ID, LOG_ANALYTICS_WORKSPACE_RESOURCE_ID
# - AZURE_MCP_URL (http://localhost:5001 for sidecar)
#
# COST ESTIMATION:
# - Container Apps Environment: ~$45/month (always on)
# - Container App (1 replica): ~$30-40/month
# - Azure OpenAI: ~$50/month (usage-based)
# - Cosmos DB Serverless: ~$25/month (usage-based)
# - ACR Basic: ~$5/month
# - Log Analytics: ~$10-15/month
# - AI Agent Service: ~$20/month
# Total: ~$200-250/month
#
# MONITORING:
# - Application Insights automatically configured
# - Container Apps metrics available in portal
# - Log streaming: az containerapp logs show --name <app-name> --resource-group <rg-name>
#
# SCALING:
# - Automatic: 1-3 replicas based on HTTP traffic
# - Manual: Update container_apps_min_replicas and container_apps_max_replicas
#
# ============================================================================
