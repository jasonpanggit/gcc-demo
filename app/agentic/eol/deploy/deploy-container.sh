#!/bin/bash

# Azure Container Apps Deployment Script with Service Principal Authentication
# Builds Docker image and deploys EOL application to Azure Container Apps
# Reads configuration from appsettings.json (or file provided via --config)

# To rebuild and deploy:
#   ./deploy-container.sh [--config <file>] [version] [build-only] [force-rebuild]
# Parameters:
#   --config/-c: Optional appsettings file name (in deploy/) or absolute path
#   version: Optional version/tag for the Docker image (default: git commit or timestamp)
#   build-only: If "true", only build and push the Docker image without deploying (default: false)
#   force-rebuild: If "true", forces Docker to rebuild the image without cache (default: false)
# Example:
#   ./deploy-container.sh --config appsettings.staging.json "" false true

set -e

# Parse parameters
APPSETTINGS_INPUT="appsettings.json"
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config|-c)
            if [[ -z "$2" ]]; then
                echo "❌ Missing value for $1"
                exit 1
            fi
            APPSETTINGS_INPUT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./deploy-container.sh [--config <file>] [version] [build-only] [force-rebuild]"
            echo "  --config/-c: appsettings file name in deploy/ (e.g. appsettings.staging.json) or absolute path"
            echo "  version: optional image version/tag"
            echo "  build-only: true|false"
            echo "  force-rebuild: true|false"
            exit 0
            ;;
        --*)
            echo "❌ Unknown option: $1"
            exit 1
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done

REQUESTED_VERSION=${POSITIONAL_ARGS[0]:-}
BUILD_ONLY=${POSITIONAL_ARGS[1]:-false}
FORCE_REBUILD=${POSITIONAL_ARGS[2]:-false}

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
if [[ "$APPSETTINGS_INPUT" = /* ]]; then
    APPSETTINGS_FILE="$APPSETTINGS_INPUT"
else
    APPSETTINGS_FILE="$DEPLOYMENT_DIR/$APPSETTINGS_INPUT"
fi

# Check if appsettings file exists
if [ ! -f "$APPSETTINGS_FILE" ]; then
    echo "❌ Appsettings file not found at $APPSETTINGS_FILE"
    exit 1
fi

echo "📖 Reading configuration from $(basename "$APPSETTINGS_FILE")..."

# Read configuration from appsettings.json using jq
SUBSCRIPTION_ID=$(jq -r '.Azure.SubscriptionId' "$APPSETTINGS_FILE")
TENANT_ID=$(jq -r '.Azure.TenantId' "$APPSETTINGS_FILE")
RESOURCE_GROUP=$(jq -r '.Azure.ResourceGroup' "$APPSETTINGS_FILE")
CONTAINER_APP_NAME=$(jq -r '.Deployment.ContainerApp.Name' "$APPSETTINGS_FILE")
CONFIGURED_CONTAINER_NAME=$(jq -r '.Deployment.ContainerApp.ContainerName // empty' "$APPSETTINGS_FILE")
ACR_NAME=$(jq -r '.Deployment.ContainerRegistry.Name' "$APPSETTINGS_FILE")
ACR_RESOURCE_GROUP=$(jq -r '.Deployment.ContainerRegistry.ResourceGroup // .Azure.ResourceGroup' "$APPSETTINGS_FILE")
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
echo "ACR Resource Group: $ACR_RESOURCE_GROUP"
echo "Image: $FULL_IMAGE_NAME"
echo ""

# Check if Azure CLI is logged in
echo "🔐 Checking Azure CLI authentication..."

# If Service Principal auth is enabled in config, use it for Azure CLI operations.
if [[ "$USE_SERVICE_PRINCIPAL" == "true" ]] && [[ -n "$SP_CLIENT_ID" ]] && [[ -n "$SP_CLIENT_SECRET" ]]; then
    echo "🔑 Authenticating Azure CLI using configured Service Principal..."
    az login --service-principal \
        --username "$SP_CLIENT_ID" \
        --password "$SP_CLIENT_SECRET" \
        --tenant "$TENANT_ID" > /dev/null
else
    if ! az account show > /dev/null 2>&1; then
        echo "❌ Azure CLI not authenticated. Please run 'az login' first."
        exit 1
    fi
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
az acr login --name "$ACR_NAME" --resource-group "$ACR_RESOURCE_GROUP"

# Build and push Docker image
echo "🏗️  Building Docker image..."
echo "Image: $FULL_IMAGE_NAME"
echo "Build context: $APP_DIR"
echo "Dockerfile: $DEPLOYMENT_DIR/Dockerfile"

if [[ "$FORCE_REBUILD" == "true" ]]; then
    echo "Forcing Docker build without cache..."
fi

BUILD_COMMAND=(
    docker buildx build
    --platform linux/amd64
    -t "$FULL_IMAGE_NAME"
    -f "$DEPLOYMENT_DIR/Dockerfile"
)

if [[ "$FORCE_REBUILD" == "true" ]]; then
    BUILD_COMMAND+=(--no-cache)
fi

BUILD_COMMAND+=("$APP_DIR" "--push")

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
OPENAI_EMBEDDING_DEPLOYMENT=$(jq -r '.AzureServices.OpenAI.EmbeddingDeployment // empty' "$APPSETTINGS_FILE")
COSMOSDB_ENDPOINT=$(jq -r '.AzureServices.CosmosDB.Endpoint' "$APPSETTINGS_FILE")
COSMOSDB_DATABASE=$(jq -r '.AzureServices.CosmosDB.Database' "$APPSETTINGS_FILE")
COSMOSDB_CONTAINER=$(jq -r '.AzureServices.CosmosDB.Container' "$APPSETTINGS_FILE")
LOG_WORKSPACE_ID=$(jq -r '.AzureServices.LogAnalytics.WorkspaceId' "$APPSETTINGS_FILE")
AI_PROJECT_NAME=$(jq -r '.AzureServices.AIFoundry.ProjectName' "$APPSETTINGS_FILE")
AI_ENDPOINT=$(jq -r '.AzureServices.AIFoundry.Endpoint' "$APPSETTINGS_FILE")
AI_PROJECT_ENDPOINT=$(jq -r '.AzureServices.AIFoundry.ProjectEndpoint // .AzureServices.AIFoundry.Endpoint' "$APPSETTINGS_FILE")
PLAYWRIGHT_LLM_EXTRACTION=$(jq -r '.AppSettings.PlaywrightLLMExtraction // "false"' "$APPSETTINGS_FILE")
KUSTO_CLUSTER_URI=$(jq -r '.AzureServices.Kusto.ClusterUri // empty' "$APPSETTINGS_FILE")
KUSTO_DATABASE=$(jq -r '.AzureServices.Kusto.Database // empty' "$APPSETTINGS_FILE")
AZURE_CLI_EXECUTOR_ENABLED=$(jq -r '.McpSettings.AzureCliExecutorEnabled // true' "$APPSETTINGS_FILE")
GITHUB_TOKEN=$(jq -r '.AppSettings.GITHUB_TOKEN // empty' "$APPSETTINGS_FILE")
TEAMS_BOT_APP_ID=$(jq -r '.TeamsBot.AppId // empty' "$APPSETTINGS_FILE")
TEAMS_BOT_APP_PASSWORD=$(jq -r '.TeamsBot.AppPassword // empty' "$APPSETTINGS_FILE")

# Normalize project endpoint for Azure AI Foundry agents if appsettings contains base endpoint
if [[ -n "$AI_PROJECT_NAME" ]] && [[ "$AI_PROJECT_NAME" != "null" ]] && [[ "$AI_PROJECT_ENDPOINT" != *"/api/projects/"* ]]; then
    AI_PROJECT_BASE="${AI_PROJECT_ENDPOINT%/}"
    AI_PROJECT_BASE="${AI_PROJECT_BASE/.cognitiveservices.azure.com/.services.ai.azure.com}"
    AI_PROJECT_ENDPOINT="${AI_PROJECT_BASE}/api/projects/${AI_PROJECT_NAME}"
    echo "ℹ️ Normalized Azure AI project endpoint: $AI_PROJECT_ENDPOINT"
fi

if [[ "$AI_PROJECT_ENDPOINT" == *"/api/projects/"* ]]; then
    EP_PROJECT_NAME="${AI_PROJECT_ENDPOINT##*/api/projects/}"
    if [[ -n "$EP_PROJECT_NAME" ]] && [[ "$EP_PROJECT_NAME" != "$AI_PROJECT_NAME" ]]; then
        AI_PROJECT_NAME="$EP_PROJECT_NAME"
        echo "ℹ️ Synced Azure AI project name from endpoint: $AI_PROJECT_NAME"
    fi
fi

# Determine authentication method
if [[ "$USE_SERVICE_PRINCIPAL" == "true" ]] && [[ -n "$SP_CLIENT_ID" ]] && [[ -n "$SP_CLIENT_SECRET" ]]; then
    echo "✅ Using Service Principal authentication (from appsettings.json)"
    AUTH_MODE="Service Principal"
    # Build environment variable string with Service Principal
    ENV_VARS="SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
    ENV_VARS="$ENV_VARS RESOURCE_GROUP_NAME=$RESOURCE_GROUP"
    ENV_VARS="$ENV_VARS AZURE_TENANT_ID=$TENANT_ID"
    ENV_VARS="$ENV_VARS TENANT_ID=$TENANT_ID"
    ENV_VARS="$ENV_VARS MANAGED_IDENTITY_CLIENT_ID=$MANAGED_IDENTITY_CLIENT_ID"
    # Standard env names required by DefaultAzureCredential EnvironmentCredential.
    ENV_VARS="$ENV_VARS AZURE_CLIENT_ID=$SP_CLIENT_ID"
    ENV_VARS="$ENV_VARS AZURE_CLIENT_SECRET=$SP_CLIENT_SECRET"
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
    ENV_VARS="$ENV_VARS TENANT_ID=$TENANT_ID"
    ENV_VARS="$ENV_VARS MANAGED_IDENTITY_CLIENT_ID=$MANAGED_IDENTITY_CLIENT_ID"
    # When user-assigned MI is configured, AZURE_CLIENT_ID helps SDK credential selection.
    if [[ -n "$MANAGED_IDENTITY_CLIENT_ID" ]] && [[ "$MANAGED_IDENTITY_CLIENT_ID" != "null" ]]; then
        ENV_VARS="$ENV_VARS AZURE_CLIENT_ID=$MANAGED_IDENTITY_CLIENT_ID"
    fi
fi

# Add Azure Services configuration
ENV_VARS="$ENV_VARS AZURE_OPENAI_ENDPOINT=$OPENAI_ENDPOINT"
ENV_VARS="$ENV_VARS AZURE_OPENAI_DEPLOYMENT=$OPENAI_DEPLOYMENT"
ENV_VARS="$ENV_VARS AZURE_OPENAI_API_VERSION=$OPENAI_API_VERSION"
if [[ -n "$OPENAI_EMBEDDING_DEPLOYMENT" ]] && [[ "$OPENAI_EMBEDDING_DEPLOYMENT" != "null" ]]; then
    ENV_VARS="$ENV_VARS AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$OPENAI_EMBEDDING_DEPLOYMENT"
    echo "✅ OpenAI embedding deployment configured: $OPENAI_EMBEDDING_DEPLOYMENT"
fi
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_ENDPOINT=$COSMOSDB_ENDPOINT"
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_DATABASE=$COSMOSDB_DATABASE"
ENV_VARS="$ENV_VARS AZURE_COSMOS_DB_CONTAINER=$COSMOSDB_CONTAINER"
ENV_VARS="$ENV_VARS LOG_ANALYTICS_WORKSPACE_ID=$LOG_WORKSPACE_ID"
ENV_VARS="$ENV_VARS AZURE_AI_PROJECT_NAME=$AI_PROJECT_NAME"
ENV_VARS="$ENV_VARS AZURE_AI_ENDPOINT=$AI_ENDPOINT"
ENV_VARS="$ENV_VARS AZURE_AI_PROJECT_ENDPOINT=$AI_PROJECT_ENDPOINT"


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

# Add Routing Telemetry configuration
ROUTING_TELEMETRY_ENABLED=$(jq -r '.RoutingTelemetry.ROUTING_TELEMETRY_ENABLED // "false"' "$APPSETTINGS_FILE")
ROUTING_TELEMETRY_LOG_DIR=$(jq -r '.RoutingTelemetry.ROUTING_TELEMETRY_LOG_DIR // "/mnt/routing_logs"' "$APPSETTINGS_FILE")
ROUTING_TELEMETRY_SAMPLE_RATE=$(jq -r '.RoutingTelemetry.ROUTING_TELEMETRY_SAMPLE_RATE // "1.0"' "$APPSETTINGS_FILE")
ENV_VARS="$ENV_VARS ROUTING_TELEMETRY_ENABLED=$ROUTING_TELEMETRY_ENABLED"
ENV_VARS="$ENV_VARS ROUTING_TELEMETRY_LOG_DIR=$ROUTING_TELEMETRY_LOG_DIR"
ENV_VARS="$ENV_VARS ROUTING_TELEMETRY_SAMPLE_RATE=$ROUTING_TELEMETRY_SAMPLE_RATE"
if [[ "$ROUTING_TELEMETRY_ENABLED" == "true" ]]; then
    echo "✅ Routing Telemetry enabled (log dir: $ROUTING_TELEMETRY_LOG_DIR, sample rate: $ROUTING_TELEMETRY_SAMPLE_RATE)"
fi

# Add Teams Bot credentials if configured
if [[ -n "$TEAMS_BOT_APP_ID" ]] && [[ "$TEAMS_BOT_APP_ID" != "null" ]] && [[ "$TEAMS_BOT_APP_ID" != "empty" ]]; then
    ENV_VARS="$ENV_VARS TEAMS_BOT_APP_ID=$TEAMS_BOT_APP_ID"
    echo "✅ Teams Bot App ID configured"
fi

if [[ -n "$TEAMS_BOT_APP_PASSWORD" ]] && [[ "$TEAMS_BOT_APP_PASSWORD" != "null" ]] && [[ "$TEAMS_BOT_APP_PASSWORD" != "empty" ]]; then
    ENV_VARS="$ENV_VARS TEAMS_BOT_APP_PASSWORD=$TEAMS_BOT_APP_PASSWORD"
    echo "✅ Teams Bot App Password configured"
fi

# Add Teams Webhook URL for alert notifications if configured
if [[ -n "$TEAMS_WEBHOOK_URL" ]] && [[ "$TEAMS_WEBHOOK_URL" != "null" ]] && [[ "$TEAMS_WEBHOOK_URL" != "empty" ]]; then
    ENV_VARS="$ENV_VARS TEAMS_WEBHOOK_URL=$TEAMS_WEBHOOK_URL"
    echo "✅ Teams Webhook URL configured for alert notifications"
fi

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
echo "   To change authentication, edit 'ServicePrincipal.UseServicePrincipal' in this file"
echo ""
echo "🧪 Test Azure MCP connection:"
echo "   curl $APP_URL/api/azure-mcp/status"
echo ""
