# ============================================================================
# EOL AGENTIC DEMO CONFIGURATION
# ============================================================================
# This configuration enables the EOL agentic application with all required
# infrastructure components including Azure Container Registry and Bing Search.

# ============================================================================
# GENERAL CONFIGURATION
# ============================================================================
project_name = "gcc-demo"
environment  = "prod"
location     = "Australia East"

# ============================================================================
# FEATURE DEPLOYMENT FLAGS
# ============================================================================
deploy_hub                = true
deploy_nongen_vnet        = true
deploy_azure_firewall     = true
deploy_monitoring         = true

# ============================================================================
# AGENTIC APP CONFIGURATION
# ============================================================================
deploy_agentic_app                  = true
agentic_app_name                    = "eol-agentic"
deploy_agentic_private_endpoints    = false

# Azure OpenAI configuration
deploy_aoai = true

# Cosmos DB configuration for EOL response caching
deploy_cosmos_db            = true
cosmos_db_serverless        = true
cosmos_db_consistency_level = "Session"

# ============================================================================
# AZURE CONTAINER REGISTRY CONFIGURATION
# ============================================================================
deploy_acr        = true
acr_sku           = "Basic"
acr_admin_enabled = true

# ============================================================================
# BING SEARCH API CONFIGURATION
# ============================================================================
deploy_bing_search   = true
bing_search_sku_name = "S0"

# ============================================================================
# OTHER SERVICES
# ============================================================================
deploy_arc = false
deploy_avd = false