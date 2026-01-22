#!/bin/bash

# Azure Container Apps Deployment Script with Service Principal Authentication
# Builds Docker image and deploys EOL application to Azure Container Apps
# Reads configuration from appsettings.json

set -e

# Parse parameters
REQUESTED_VERSION=${1:-}
BUILD_ONLY=${2:-false}
FORCE_REBUILD=${3:-false}

# Navigate to parent directory (app root) from deployment folder
cd "$(dirname "$0")/.."
APP_DIR=$(pwd)

# Determine version/tag (use CLI argument, git commit, or timestamp)
DEFAULT_VERSION=$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)
if [[ -z "$REQUESTED_VERSION" ]]; then
    VERSION="$DEFAULT_VERSION"
    VERSION_SOURCE="auto"
else
    VERSION="$REQUESTED_VERSION"
    VERSION_SOURCE="manual"
fi
DEPLOYMENT_DIR="$APP_DIR/deploy"
APPSETTINGS_FILE="$DEPLOYMENT_DIR/appsettings.json"

# Check if appsettings.json exists
if [ ! -f "$APPSETTINGS_FILE" ]; then
    echo "❌ appsettings.json not found at $APPSETTINGS_FILE"
    exit 1
fi

echo "📖 Reading configuration from appsettings.json..."

# Read configuration from appsettings.json using jq
SUBSCRIPTION_ID=$(jq -r '.Azure.SubscriptionId' "$APPSETTINGS_FILE")
TENANT_ID=$(jq -r '.Azure.TenantId' "$APPSETTINGS_FILE")
RESOURCE_GROUP=$(jq -r '.Azure.ResourceGroup' "$APPSETTINGS_FILE")
CONTAINER_APP_NAME=$(jq -r '.Deployment.ContainerApp.Name' "$APPSETTINGS_FILE")
CONFIGURED_CONTAINER_NAME=$(jq -r '.Deployment.ContainerApp.ContainerName // empty' "$APPSETTINGS_FILE")
ACR_NAME=$(jq -r '.Deployment.ContainerRegistry.Name' "$APPSETTINGS_FILE")
IMAGE_NAME=$(jq -r '.Deployment.ContainerRegistry.ImageName' "$APPSETTINGS_FILE")
MANAGED_IDENTITY_CLIENT_ID=$(jq -r '.ManagedIdentity.ClientId' "$APPSETTINGS_FILE")
USE_SERVICE_PRINCIPAL=$(jq -r '.ServicePrincipal.UseServicePrincipal' "$APPSETTINGS_FILE")
SP_CLIENT_ID=$(jq -r '.ServicePrincipal.ClientId // empty' "$APPSETTINGS_FILE")
SP_CLIENT_SECRET=$(jq -r '.ServicePrincipal.ClientSecret // empty' "$APPSETTINGS_FILE")

# Use version parameter or default from config
IMAGE_TAG="v${VERSION}"

# Construct full image name
FULL_IMAGE_NAME="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo "=============================================="
echo "Azure Container Apps Build & Deploy"
echo "Version: $VERSION"
echo "Version Source: $VERSION_SOURCE"
echo "Build Only: $BUILD_ONLY"
echo "Force Rebuild: $FORCE_REBUILD"
echo "=============================================="

echo "🚀 Starting deployment process..."
echo "Application directory: $APP_DIR"
echo "Resource Group: $RESOURCE_GROUP"
echo "Container App: $CONTAINER_APP_NAME"
echo "Image: $FULL_IMAGE_NAME"
echo ""

# Check if Azure CLI is logged in
echo "🔐 Checking Azure CLI authentication..."
if ! az account show > /dev/null 2>&1; then
    echo "❌ Azure CLI not authenticated. Please run 'az login' first."
    exit 1
fi

# Set the subscription
echo "🔧 Setting Azure subscription..."
az account set --subscription "$SUBSCRIPTION_ID"

# Resolve container name (from config or existing template)
if [[ -n "$CONFIGURED_CONTAINER_NAME" ]]; then
    CONTAINER_NAME="$CONFIGURED_CONTAINER_NAME"
else
    echo "🔍 Discovering container name from existing Container App configuration..."
    set +e
    CONTAINER_NAME=$(az containerapp show \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.template.containers[0].name" -o tsv 2>/dev/null)
    SHOW_STATUS=$?
    set -e
    if (( SHOW_STATUS != 0 )) || [[ -z "$CONTAINER_NAME" || "$CONTAINER_NAME" == "" ]]; then
        echo "ℹ️  Falling back to default container name 'eol-app'."
        CONTAINER_NAME="eol-app"
    else
        echo "✅ Using detected container name: $CONTAINER_NAME"
    fi
fi

echo "Container Name: $CONTAINER_NAME"
echo ""

# Login to ACR
echo "🔐 Logging in to Azure Container Registry..."
az acr login --name "$ACR_NAME"

# Build and push Docker image
echo "🏗️  Building Docker image..."
echo "Image: $FULL_IMAGE_NAME"
cd "$DEPLOYMENT_DIR"

if [[ "$FORCE_REBUILD" == "true" ]]; then
    echo "Forcing Docker build without cache..."
fi

BUILD_COMMAND=(
    docker buildx build
    --platform linux/amd64
    -t "$FULL_IMAGE_NAME"
    -f Dockerfile
)

if [[ "$FORCE_REBUILD" == "true" ]]; then
    BUILD_COMMAND+=(--no-cache)
fi

BUILD_COMMAND+=(".." "--push")

"${BUILD_COMMAND[@]}"

echo "✅ Docker image built and pushed successfully"

# Exit if build-only mode
if [[ "$BUILD_ONLY" == "true" ]]; then
    echo "🎯 Build-only mode: Skipping deployment"
    exit 0
fi

# Prepare environment variables for Container App
echo "🔧 Preparing environment variables..."

# Read additional Azure services configuration
OPENAI_ENDPOINT=$(jq -r '.AzureServices.OpenAI.Endpoint' "$APPSETTINGS_FILE")
OPENAI_DEPLOYMENT=$(jq -r '.AzureServices.OpenAI.Deployment' "$APPSETTINGS_FILE")
OPENAI_API_VERSION=$(jq -r '.AzureServices.OpenAI.ApiVersion' "$APPSETTINGS_FILE")
COSMOSDB_ENDPOINT=$(jq -r '.AzureServices.CosmosDB.Endpoint' "$APPSETTINGS_FILE")
COSMOSDB_DATABASE=$(jq -r '.AzureServices.CosmosDB.Database' "$APPSETTINGS_FILE")
COSMOSDB_CONTAINER=$(jq -r '.AzureServices.CosmosDB.Container' "$APPSETTINGS_FILE")
LOG_WORKSPACE_ID=$(jq -r '.AzureServices.LogAnalytics.WorkspaceId' "$APPSETTINGS_FILE")
AI_PROJECT_NAME=$(jq -r '.AzureServices.AIFoundry.ProjectName' "$APPSETTINGS_FILE")
AI_ENDPOINT=$(jq -r '.AzureServices.AIFoundry.Endpoint' "$APPSETTINGS_FILE")
PLAYWRIGHT_LLM_EXTRACTION=$(jq -r '.AppSettings.PlaywrightLLMExtraction // "false"' "$APPSETTINGS_FILE")
KUSTO_CLUSTER_URI=$(jq -r '.AzureServices.Kusto.ClusterUri // empty' "$APPSETTINGS_FILE")
KUSTO_DATABASE=$(jq -r '.AzureServices.Kusto.Database // empty' "$APPSETTINGS_FILE")
AZURE_CLI_EXECUTOR_ENABLED=$(jq -r '.McpSettings.AzureCliExecutorEnabled // true' "$APPSETTINGS_FILE")

# Determine authentication method
if [[ "$USE_SERVICE_PRINCIPAL" == "true" ]] && [[ -n "$SP_CLIENT_ID" ]] && [[ -n "$SP_CLIENT_SECRET" ]]; then
    echo "✅ Using Service Principal authentication (from appsettings.json)"
    AUTH_MODE="Service Principal"
    # Build environment variable string with Service Principal
    ENV_VARS="SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
    ENV_VARS="$ENV_VARS RESOURCE_GROUP_NAME=$RESOURCE_GROUP"
    ENV_VARS="$ENV_VARS AZURE_TENANT_ID=$TENANT_ID"
    ENV_VARS="$ENV_VARS MANAGED_IDENTITY_CLIENT_ID=$MANAGED_IDENTITY_CLIENT_ID"
    ENV_VARS="$ENV_VARS AZURE_SP_CLIENT_ID=$SP_CLIENT_ID"
    ENV_VARS="$ENV_VARS AZURE_SP_CLIENT_SECRET=$SP_CLIENT_SECRET"
    ENV_VARS="$ENV_VARS USE_SERVICE_PRINCIPAL=true"
else
    echo "✅ Using Managed Identity authentication"
    AUTH_MODE="Managed Identity"
    # Build environment variable string without Service Principal
    ENV_VARS="SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
    ENV_VARS="$ENV_VARS RESOURCE_GROUP_NAME=$RESOURCE_GROUP"
    ENV_VARS="$ENV_VARS AZURE_TENANT_ID=$TENANT_ID"
    ENV_VARS="$ENV_VARS MANAGED_IDENTITY_CLIENT_ID=$MANAGED_IDENTITY_CLIENT_ID"
fi

# Add Azure Services configuration
ENV_VARS="$ENV_VARS AZURE_OPENAI_ENDPOINT=$OPENAI_ENDPOINT"
ENV_VARS="$ENV_VARS AZURE_OPENAI_DEPLOYMENT=$OPENAI_DEPLOYMENT"
ENV_VARS="$ENV_VARS AZURE_OPENAI_API_VERSION=$OPENAI_API_VERSION"
ENV_VARS="$ENV_VARS AOAI_ENDPOINT=$OPENAI_ENDPOINT"
ENV_VARS="$ENV_VARS AOAI_DEPLOYMENT=$OPENAI_DEPLOYMENT"
ENV_VARS="$ENV_VARS AOAI_API_VERSION=$OPENAI_API_VERSION"
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_ENDPOINT=$COSMOSDB_ENDPOINT"
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_DATABASE=$COSMOSDB_DATABASE"
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_CONTAINER=$COSMOSDB_CONTAINER"
ENV_VARS="$ENV_VARS LOG_ANALYTICS_WORKSPACE_ID=$LOG_WORKSPACE_ID"
ENV_VARS="$ENV_VARS AZURE_AI_PROJECT_NAME=$AI_PROJECT_NAME"
ENV_VARS="$ENV_VARS AZURE_AI_ENDPOINT=$AI_ENDPOINT"

# Add Kusto configuration if available
if [[ -n "$KUSTO_CLUSTER_URI" ]]; then
    ENV_VARS="$ENV_VARS KUSTO_CLUSTER_URI=$KUSTO_CLUSTER_URI"
fi
if [[ -n "$KUSTO_DATABASE" ]]; then
    ENV_VARS="$ENV_VARS KUSTO_DATABASE=$KUSTO_DATABASE"
fi

# Add app settings
ENV_VARS="$ENV_VARS WEBSITES_PORT=8000"
ENV_VARS="$ENV_VARS PYTHONUNBUFFERED=1"
ENV_VARS="$ENV_VARS CONTAINER_MODE=true"
ENV_VARS="$ENV_VARS ENVIRONMENT=production"
ENV_VARS="$ENV_VARS PLAYWRIGHT_LLM_EXTRACTION=$PLAYWRIGHT_LLM_EXTRACTION"
# Disable optional MCP servers that cause issues in ACA unless explicitly enabled
ENV_VARS="$ENV_VARS AZURE_CLI_EXECUTOR_ENABLED=$AZURE_CLI_EXECUTOR_ENABLED"

# Deploy to Container Apps
echo "🚀 Deploying to Azure Container Apps..."

# Compute revision suffix by incrementing latest numeric revision
echo "📈 Determining next revision suffix..."
REVISION_LIST=$(az containerapp revision list \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "[].name" -o tsv 2>/dev/null || true)

NEXT_REVISION_NUM=1
if [[ -n "$REVISION_LIST" ]]; then
    while IFS= read -r REVISION_NAME; do
        [[ -z "$REVISION_NAME" ]] && continue
        SUFFIX="${REVISION_NAME#${CONTAINER_APP_NAME}--}"
        if [[ "$SUFFIX" =~ ^rev-([0-9]+)$ ]]; then
            REV_NUM="${BASH_REMATCH[1]}"
            # Treat the captured number as base-10 to avoid octal parsing when it has leading zeros
            REV_NUM_DEC=$((10#$REV_NUM))
            if (( REV_NUM_DEC + 1 > NEXT_REVISION_NUM )); then
                NEXT_REVISION_NUM=$((REV_NUM_DEC + 1))
            fi
        fi
    done <<< "$REVISION_LIST"
fi

REVISION_SUFFIX=$(printf "rev-%04d" "$NEXT_REVISION_NUM")
echo "   Using revision suffix: $REVISION_SUFFIX"

OUT_FILE=$(mktemp)
ERR_FILE=$(mktemp)
cleanup_temp_files() {
    rm -f "$OUT_FILE" "$ERR_FILE"
}
trap cleanup_temp_files EXIT

run_update() {
    local suffix="$1"
    # shellcheck disable=SC2086
    az containerapp update \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$FULL_IMAGE_NAME" \
        --container-name "$CONTAINER_NAME" \
        --revision-suffix "$suffix" \
        --cpu 1.5 \
        --memory 3.0Gi \
        --min-replicas 1 \
        --set-env-vars $ENV_VARS \
        --query "{name:name, latestRevision:properties.latestRevisionName, status:properties.runningStatus}" \
        -o json >"$OUT_FILE" 2> >(tee "$ERR_FILE" >&2)
}

set +e
run_update "$REVISION_SUFFIX"
UPDATE_STATUS=$?
set -e

if (( UPDATE_STATUS != 0 )) && grep -qi "revision with suffix" "$ERR_FILE"; then
    echo "⚠️ Revision suffix $REVISION_SUFFIX already exists. Generating a unique suffix..."
    REVISION_SUFFIX="rev-$(date +%Y%m%d%H%M%S)"
    echo "   Retrying with revision suffix: $REVISION_SUFFIX"
    : >"$OUT_FILE"
    : >"$ERR_FILE"
    set +e
    run_update "$REVISION_SUFFIX"
    UPDATE_STATUS=$?
    set -e
fi

if (( UPDATE_STATUS != 0 )); then
    cat "$ERR_FILE" >&2
    exit $UPDATE_STATUS
fi

cat "$OUT_FILE"
trap - EXIT
cleanup_temp_files

REVISION=$(az containerapp show \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.latestRevisionName" -o tsv)

APP_URL=$(jq -r '.Deployment.ContainerApp.Url' "$APPSETTINGS_FILE")

echo "✅ Deployment completed successfully!"
echo ""
echo "📋 Deployment Summary:"
echo "   - Container App: $CONTAINER_APP_NAME"
echo "   - Resource Group: $RESOURCE_GROUP"
echo "   - Image: $IMAGE_TAG"
echo "   - Revision: $REVISION"
echo "   - Authentication: $AUTH_MODE"
echo "   - MCP Mode: stdio (Node.js/npx built-in)"
echo ""
echo "🔗 Application URL:"
echo "   $APP_URL"
echo ""
echo "� To view logs:"
echo "   az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --follow"
echo ""
echo "💡 Configuration:"
echo "   All settings are read from: $APPSETTINGS_FILE"
echo "   To change authentication, edit 'ServicePrincipal.UseServicePrincipal' in appsettings.json"
echo ""
echo "🧪 Test Azure MCP connection:"
echo "   curl $APP_URL/api/azure-mcp/status"
echo ""
