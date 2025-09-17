# ============================================================================
# EOL AGENTIC DEMO CONFIGURATION
# ============================================================================
# This configuration enables the EOL agentic application with all required
# infrastructure components including Azure Container Registry and Bing Search.

# ============================================================================
# GENERAL CONFIGURATION
# ============================================================================
location     = "Australia East" # Primary Azure region for all resources
environment  = "demo"           # Environment tag and naming suffix
project_name = "gcc"            # Project identifier for resource naming

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
deploy_agentic_private_endpoints    = true

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
acr_name          = "acreolggcdemo"  # Match existing ACR
acr_sku           = "Basic"
acr_admin_enabled = true

# ==============================================================================
# AZURE AI AGENT SERVICE CONFIGURATION (Modern replacement for Bing Search)
# ==============================================================================
deploy_azure_ai_agent        = true   # Enable Azure AI Foundry with grounding capabilities
azure_ai_foundry_sku_name    = "S0"   # Standard pricing tier
# azure_ai_foundry_name      = null   # Auto-generated if not specified

# ==============================================================================
# AZURE ARC
# ==============================================================================
deploy_arc_private_link_scope            = true
deploy_arc_service_principal             = true
arc_service_principal_subscription_scope = true