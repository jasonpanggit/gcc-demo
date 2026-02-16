#!/bin/bash

# ============================================================================
# Generate appsettings.json from Terraform outputs
# ============================================================================
# This script reads Terraform outputs and generates an appsettings.json file
# for the agentic EOL application based on the deployed infrastructure.
# 
# Generates Azure AI Agent Service configuration from Terraform outputs.
# Requires deploy_azure_ai_agent=true in Terraform variables for Azure AI
# settings to be populated, otherwise they will show as "NOT_SET".
#
# Usage:
#   ./generate-appsettings.sh [output-file]
#
# Arguments:
#   output-file: Optional path to output file (default: appsettings.json)
#
# Requirements:
#   - terraform must be available in PATH
#   - jq must be available in PATH
#   - Must be run from the terraform project root directory
# ============================================================================

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"

# Handle output file argument
if [[ $# -gt 0 ]]; then
    # If argument provided, check if it's a relative path or absolute path
    if [[ "$1" = /* ]]; then
        # Absolute path - use as-is
        OUTPUT_FILE="$1"
    else
        # Relative path or filename - place in script directory
        OUTPUT_FILE="${SCRIPT_DIR}/$1"
    fi
else
    # No argument provided - use default
    OUTPUT_FILE="${SCRIPT_DIR}/appsettings.json"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Utility functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check requirements
check_requirements() {
    log_info "Checking requirements..."
    
    if ! command -v terraform &> /dev/null; then
        log_error "terraform is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        log_error "jq is not installed or not in PATH"
        log_info "Install jq: brew install jq (macOS) or apt-get install jq (Ubuntu)"
        exit 1
    fi
    
    if [[ ! -f "${PROJECT_ROOT}/main.tf" ]]; then
        log_error "main.tf not found at ${PROJECT_ROOT}/main.tf"
        log_error "Please run this script from the terraform project root or adjust PROJECT_ROOT"
        exit 1
    fi
    
    log_info "Requirements check passed"
}

# Get terraform outputs
get_terraform_outputs() {
    log_info "Getting Terraform outputs from ${PROJECT_ROOT}..."
    
    cd "${PROJECT_ROOT}"
    
    if ! terraform output -json > /tmp/tf_outputs.json 2>/dev/null; then
        log_error "Failed to get Terraform outputs"
        log_error "Make sure terraform init and terraform apply have been run successfully"
        exit 1
    fi
    
    log_info "Successfully retrieved Terraform outputs"
}

# Generate appsettings.json
generate_appsettings() {
    log_info "Generating appsettings.json..."
    
    # Read terraform outputs
    local tf_outputs="/tmp/tf_outputs.json"
    
    # Extract values with fallbacks
    local subscription_id=$(jq -r '.subscription_id.value // "NOT_SET"' "$tf_outputs")
    local tenant_id=$(jq -r '.tenant_id.value // "NOT_SET"' "$tf_outputs")
    local resource_group_name=$(jq -r '.hub_resource_group_name.value // "NOT_SET"' "$tf_outputs")
    local location=$(jq -r '.location.value // "australiaeast"' "$tf_outputs")
    local environment=$(jq -r '.environment.value // "production"' "$tf_outputs")
    local container_app_name=$(jq -r '.agentic_app_service_name.value // "NOT_SET"' "$tf_outputs")
    local container_app_fqdn=$(jq -r '.agentic_app_hostname.value // "NOT_SET"' "$tf_outputs")
    local container_app_url=$(jq -r '.agentic_app_url.value // "NOT_SET"' "$tf_outputs")
    local container_app_env_name=$(jq -r '.container_apps_environment_name.value // "NOT_SET"' "$tf_outputs")
    local azure_openai_endpoint=$(jq -r '.agentic_aoai_endpoint.value // "NOT_SET"' "$tf_outputs")
    local azure_openai_deployment=$(jq -r '.agentic_aoai_deployment_name.value // "NOT_SET"' "$tf_outputs")
    local azure_openai_api_version="2024-08-01-preview"
    local log_analytics_workspace_id=$(jq -r '.log_analytics_workspace_guid.value // .log_analytics_workspace_id.value // "NOT_SET"' "$tf_outputs")
    local cosmos_db_endpoint=$(jq -r '(.agentic_cosmos_db_endpoint.value // .cosmos_db_endpoint.value) // "NOT_SET"' "$tf_outputs")
    local cosmos_db_database=$(jq -r '(.agentic_cosmos_db_database_name.value // .cosmos_db_database_name.value) // "NOT_SET"' "$tf_outputs")
    local cosmos_db_container=$(jq -r '(.agentic_cosmos_db_container_name.value // .cosmos_db_container_name.value) // "NOT_SET"' "$tf_outputs")
    local managed_identity_client_id=$(jq -r '.agentic_app_principal_id.value // "NOT_SET"' "$tf_outputs")
    local environment=$(jq -r '.environment.value // "production"' "$tf_outputs")
    
    # Service Principal credentials (if configured)
    local sp_client_id=$(jq -r '.service_principal_client_id.value // "NOT_SET"' "$tf_outputs")
    local sp_client_secret=$(jq -r '.service_principal_client_secret.value // "NOT_SET"' "$tf_outputs")
    
    # Extract ACR values
    local acr_name=$(jq -r '.agentic_acr_name.value // "NOT_SET"' "$tf_outputs")
    local acr_login_server=$(jq -r '.agentic_acr_login_server.value // "NOT_SET"' "$tf_outputs")
    
    # Azure AI Agent Service settings (optional)
    local azure_ai_project_name=$(jq -r '.agentic_azure_ai_foundry_name.value // "NOT_SET"' "$tf_outputs")
    local azure_ai_endpoint=$(jq -r '.agentic_azure_ai_foundry_endpoint.value // "NOT_SET"' "$tf_outputs")
    local azure_ai_sre_agent_name=$(jq -r '.agentic_azure_ai_sre_agent_name.value // "gccsreagent"' "$tf_outputs")
    local azure_ai_sre_agent_id=$(jq -r '.agentic_azure_ai_sre_agent_id.value // "NOT_SET"' "$tf_outputs")

    # Check if agentic module outputs are available
    local has_agentic_outputs=$(jq -r 'has("agentic_app_url")' "$tf_outputs")
    
    if [[ "$has_agentic_outputs" != "true" ]]; then
        log_warn "Agentic module outputs not found. Make sure deploy_agentic_app is set to true."
        log_warn "Some values will use placeholder defaults."
    fi
    
    # Check if Azure AI Agent Service is enabled
    local azure_ai_enabled=$(jq -r '.agentic_azure_ai_foundry_name.value != null and .agentic_azure_ai_foundry_name.value != "NOT_SET"' "$tf_outputs")
    if [[ "$azure_ai_enabled" != "true" ]]; then
        log_warn "Azure AI Agent Service not deployed. Set deploy_azure_ai_agent=true to enable."
    fi
    
    # Generate the appsettings.json content with nested structure
    cat > "$OUTPUT_FILE" << EOF
{
  "Azure": {
    "SubscriptionId": "${subscription_id}",
    "TenantId": "${tenant_id}",
    "ResourceGroup": "${resource_group_name}",
    "Location": "${location}"
  },
  "Deployment": {
    "ContainerApp": {
      "Name": "${container_app_name}",
      "Environment": "${container_app_env_name}",
      "Url": "${container_app_url}"
    },
    "ContainerRegistry": {
      "Name": "${acr_name}",
      "ImageName": "eol-app",
      "DefaultTag": "latest"
    }
  },
  "ServicePrincipal": {
    "ClientId": "${sp_client_id}",
    "ClientSecret": "${sp_client_secret}",
    "UseServicePrincipal": $([[ "${sp_client_id}" != "NOT_SET" ]] && echo "true" || echo "false"),
    "Comment": "Set UseServicePrincipal to false to use Managed Identity instead"
  },
  "ManagedIdentity": {
    "ClientId": "${managed_identity_client_id}",
    "Comment": "Used when UseServicePrincipal is false"
  },
  "AzureServices": {
    "OpenAI": {
      "Endpoint": "${azure_openai_endpoint}",
      "Deployment": "${azure_openai_deployment}",
      "ApiVersion": "${azure_openai_api_version}"
    },
    "CosmosDB": {
      "Endpoint": "${cosmos_db_endpoint}",
      "Database": "${cosmos_db_database}",
      "Container": "${cosmos_db_container}"
    },
    "LogAnalytics": {
      "WorkspaceId": "${log_analytics_workspace_id}"
    },
    "AIFoundry": {
      "ProjectName": "${azure_ai_project_name}",
      "Endpoint": "${azure_ai_endpoint}",
      "ProjectEndpoint": "${azure_ai_endpoint}",
      "SREAgentName": "${azure_ai_sre_agent_name}",
      "SREAgentId": "${azure_ai_sre_agent_id}",
      "SREEnabled": "$([[ \"${azure_ai_endpoint}\" != \"NOT_SET\" && \"${azure_ai_endpoint}\" != \"null\" ]] && echo \"true\" || echo \"false\")",
      "Comment": "Azure AI Agent Service configuration for Azure AI SRE agent integration"
    },
    "Kusto": {
      "ClusterUri": "https://data-explorer.azure.com",
      "Database": "ARG",
      "Description": "Azure Resource Graph endpoint for KQL queries"
    }
  },
  "TeamsBot": {
    "AppId": "_PLACEHOLDER_REPLACE_WITH_YOUR_TEAMS_BOT_APP_ID_",
    "AppPassword": "_PLACEHOLDER_REPLACE_WITH_YOUR_TEAMS_BOT_APP_PASSWORD_",
    "_comment": "Replace with your Microsoft Teams Bot credentials for SRE notifications"
  },
  "AppSettings": {
    "WEBSITES_PORT": "8000",
    "PYTHONUNBUFFERED": "1",
    "DEBUG_MODE": "false",
    "ENVIRONMENT": "${environment}",
    "CONTAINER_MODE": "true",
    "PlaywrightLLMExtraction": "false"
  },
  "McpSettings": {
    "AzureCliExecutorEnabled": false
  }
}
EOF
    
    # Cleanup temp file
    rm -f "$tf_outputs"
    
    log_info "Generated appsettings.json at: ${OUTPUT_FILE}"
}

# Validate generated JSON
validate_json() {
    log_info "Validating generated JSON..."
    
    if jq empty "$OUTPUT_FILE" 2>/dev/null; then
        log_info "✓ Generated JSON is valid"
    else
        log_error "✗ Generated JSON is invalid"
        exit 1
    fi
}

# Show summary
show_summary() {
    log_info "=== Generation Summary ==="
    echo "Output file: ${OUTPUT_FILE}"
    echo "File size: $(wc -c < "$OUTPUT_FILE") bytes"
    
    # Check for placeholder values
    local placeholders=$(grep -o 'NOT_SET\|PLACEHOLDER' "$OUTPUT_FILE" || true)
    if [[ -n "$placeholders" ]]; then
        log_warn "⚠️  Some values contain placeholders. Review and update manually:"
        grep -n 'NOT_SET\|PLACEHOLDER' "$OUTPUT_FILE" || true
    else
        log_info "✓ All values populated from Terraform outputs"
    fi
    
    echo ""
    log_info "Next steps:"
    echo "1. Review the generated appsettings.json"
    echo "2. Update any placeholder values if needed"
    echo "3. Deploy or copy to your app service"
    echo ""
    echo "To view the file contents:"
    echo "  cat ${OUTPUT_FILE}"
}

# Main execution
main() {
    log_info "Starting appsettings.json generation..."
    echo "Project root: ${PROJECT_ROOT}"
    echo "Output file: ${OUTPUT_FILE}"
    echo ""
    
    check_requirements
    get_terraform_outputs
    generate_appsettings
    validate_json
    show_summary
    
    log_info "✅ appsettings.json generation completed successfully!"
}

# Run main function
main "$@"
