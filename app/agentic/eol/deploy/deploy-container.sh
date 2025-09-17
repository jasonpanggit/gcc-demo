#!/bin/bash

# Container-based App Deployment Script
# Deploys application as Docker container to Azure App Service with WebSurfer/Playwright support

set -e

# Parse environment parameter (default to production)
ENVIRONMENT=${1:-production}

echo "=============================================="
echo "Container-based App Deployment with WebSurfer"
echo "Environment: $ENVIRONMENT"
echo "=============================================="

# Navigate to parent directory (app root) from deployment folder
cd "$(dirname "$0")/.."
APP_DIR=$(pwd)
DEPLOYMENT_DIR="$APP_DIR/deploy"

echo "🔧 Reading deployment configuration..."
# Apply app settings from environment-specific configuration file
SETTINGS_FILE="$DEPLOYMENT_DIR/appsettings.$ENVIRONMENT.json"

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "⚠️  Settings file not found: $SETTINGS_FILE"
    echo "   Falling back to default appsettings.json"
    SETTINGS_FILE="$DEPLOYMENT_DIR/appsettings.json"
fi

echo "📄 Reading configuration from $(basename "$SETTINGS_FILE")..."

# Extract ALL configuration values from JSON at once
RESOURCE_GROUP=$(jq -r '.RESOURCE_GROUP_NAME' "$SETTINGS_FILE")
APP_NAME=$(jq -r '.APP_NAME' "$SETTINGS_FILE")
SUBSCRIPTION_ID_VAL=$(jq -r '.SUBSCRIPTION_ID' "$SETTINGS_FILE")

# Container-specific settings
AZURE_CONTAINER_REGISTRY=$(jq -r '.AZURE_CONTAINER_REGISTRY // "defaultregistry"' "$SETTINGS_FILE")
IMAGE_NAME=$(jq -r '.IMAGE_NAME // "eol-app"' "$SETTINGS_FILE")
IMAGE_TAG=$(jq -r '.IMAGE_TAG // "latest"' "$SETTINGS_FILE")

# Application settings
WEBSITES_PORT_VAL=$(jq -r '.WEBSITES_PORT' "$SETTINGS_FILE")
PYTHON_UNBUFFERED=$(jq -r '.PYTHONUNBUFFERED' "$SETTINGS_FILE")
DEBUG_MODE_VAL=$(jq -r '.DEBUG_MODE' "$SETTINGS_FILE")
ENVIRONMENT_VAL=$(jq -r '.ENVIRONMENT' "$SETTINGS_FILE")
AZURE_OPENAI_ENDPOINT_VAL=$(jq -r '.AZURE_OPENAI_ENDPOINT' "$SETTINGS_FILE")
AZURE_OPENAI_DEPLOYMENT_VAL=$(jq -r '.AZURE_OPENAI_DEPLOYMENT' "$SETTINGS_FILE")
LOG_ANALYTICS_WORKSPACE_ID_VAL=$(jq -r '.LOG_ANALYTICS_WORKSPACE_ID' "$SETTINGS_FILE")
AZURE_COSMOS_DB_ENDPOINT_VAL=$(jq -r '.AZURE_COSMOS_DB_ENDPOINT' "$SETTINGS_FILE")
AZURE_COSMOS_DB_DATABASE_VAL=$(jq -r '.AZURE_COSMOS_DB_DATABASE' "$SETTINGS_FILE")
AZURE_COSMOS_DB_CONTAINER_VAL=$(jq -r '.AZURE_COSMOS_DB_CONTAINER' "$SETTINGS_FILE")

# Azure AI Agent Service settings
AZURE_AI_PROJECT_NAME_VAL=$(jq -r '.AZURE_AI_PROJECT_NAME' "$SETTINGS_FILE")
AZURE_AI_ENDPOINT_VAL=$(jq -r '.AZURE_AI_ENDPOINT' "$SETTINGS_FILE")

# Construct full image name
FULL_IMAGE_NAME="${AZURE_CONTAINER_REGISTRY}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo "🚀 Starting container-based deployment..."
echo "Application directory: $APP_DIR"
echo "Resource Group: $RESOURCE_GROUP"
echo "App Name: $APP_NAME"
echo "Environment: $ENVIRONMENT"
echo "Container Image: $FULL_IMAGE_NAME"
echo ""

# Check if Azure CLI is logged in
echo "🔐 Checking Azure CLI authentication..."
if ! az account show > /dev/null 2>&1; then
    echo "❌ Azure CLI not authenticated. Please run 'az login' first."
    exit 1
fi

# Set the subscription
echo "🔧 Setting Azure subscription to $SUBSCRIPTION_ID_VAL..."
az account set --subscription "$SUBSCRIPTION_ID_VAL"

# Check if the container registry exists
echo "🏗️ Checking Azure Container Registry..."
if ! az acr show --name "$AZURE_CONTAINER_REGISTRY" --resource-group "$RESOURCE_GROUP" > /dev/null 2>&1; then
    echo "⚠️ Azure Container Registry '$AZURE_CONTAINER_REGISTRY' not found."
    echo "Creating Azure Container Registry..."
    az acr create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$AZURE_CONTAINER_REGISTRY" \
        --sku Basic \
        --admin-enabled true
    echo "✅ Azure Container Registry created successfully"
else
    echo "✅ Azure Container Registry '$AZURE_CONTAINER_REGISTRY' found"
fi

# Get ACR login server
ACR_LOGIN_SERVER=$(az acr show --name "$AZURE_CONTAINER_REGISTRY" --resource-group "$RESOURCE_GROUP" --query loginServer --output tsv)
echo "🔗 ACR Login Server: $ACR_LOGIN_SERVER"

# Build and push the container image
echo "🔨 Building container image with Playwright/WebSurfer support..."
docker build --platform linux/amd64 -f "$DEPLOYMENT_DIR/Dockerfile" -t "$FULL_IMAGE_NAME" "$APP_DIR"

# Login to ACR
echo "🔐 Logging into Azure Container Registry..."
az acr login --name "$AZURE_CONTAINER_REGISTRY"

# Push the image
echo "📦 Pushing container image to registry..."
docker push "$FULL_IMAGE_NAME"

echo "✅ Container image built and pushed successfully!"

# Configure the App Service to use the container
echo "🔧 Configuring App Service for container deployment..."
az webapp config container set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --docker-custom-image-name "$FULL_IMAGE_NAME" \
    --docker-registry-server-url "https://$ACR_LOGIN_SERVER"

# Get ACR credentials for App Service
ACR_USERNAME=$(az acr credential show --name "$AZURE_CONTAINER_REGISTRY" --query username --output tsv)
ACR_PASSWORD=$(az acr credential show --name "$AZURE_CONTAINER_REGISTRY" --query passwords[0].value --output tsv)

# Set registry credentials in App Service
echo "🔐 Setting container registry credentials..."
az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --settings \
        "DOCKER_REGISTRY_SERVER_URL=https://$ACR_LOGIN_SERVER" \
        "DOCKER_REGISTRY_SERVER_USERNAME=$ACR_USERNAME" \
        "DOCKER_REGISTRY_SERVER_PASSWORD=$ACR_PASSWORD"

# Configure container-specific application settings
echo "🔧 Applying container-specific application settings..."
az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$APP_NAME" \
    --settings \
        "CONTAINER_MODE=true" \
        "WEBSITES_PORT=$WEBSITES_PORT_VAL" \
        "PYTHONUNBUFFERED=$PYTHON_UNBUFFERED" \
        "DEBUG_MODE=$DEBUG_MODE_VAL" \
        "ENVIRONMENT=$ENVIRONMENT_VAL" \
        "SUBSCRIPTION_ID=$SUBSCRIPTION_ID_VAL" \
        "RESOURCE_GROUP_NAME=$RESOURCE_GROUP" \
        "APP_NAME=$APP_NAME" \
        "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT_VAL" \
        "AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT_VAL" \
        "LOG_ANALYTICS_WORKSPACE_ID=$LOG_ANALYTICS_WORKSPACE_ID_VAL" \
        "AZURE_COSMOS_DB_ENDPOINT=$AZURE_COSMOS_DB_ENDPOINT_VAL" \
        "AZURE_COSMOS_DB_DATABASE=$AZURE_COSMOS_DB_DATABASE_VAL" \
        "AZURE_COSMOS_DB_CONTAINER=$AZURE_COSMOS_DB_CONTAINER_VAL" \
        "AZURE_AI_PROJECT_NAME=$AZURE_AI_PROJECT_NAME_VAL" \
        "AZURE_AI_ENDPOINT=$AZURE_AI_ENDPOINT_VAL"

echo "✅ Container-specific settings configured:"
echo "   - CONTAINER_MODE=true (Enables WebSurfer in App Service)"
echo "   - WEBSITES_PORT=$WEBSITES_PORT_VAL (App port)"
echo "   - PYTHONUNBUFFERED=$PYTHON_UNBUFFERED (Python logging)"
echo "   - AZURE_AI_ENDPOINT=$AZURE_AI_ENDPOINT_VAL (Azure AI Agent Service endpoint)"
echo "   - Container Image: $FULL_IMAGE_NAME"
echo "   - Registry: $ACR_LOGIN_SERVER"

# Restart the app to pick up new container
echo "🔄 Restarting App Service to deploy new container..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP"

echo ""
echo "🎉 Container deployment completed successfully!"
echo ""
echo "📋 Deployment Summary:"
echo "   - Environment: $ENVIRONMENT"
echo "   - App Service: $APP_NAME"
echo "   - Resource Group: $RESOURCE_GROUP"
echo "   - Container Registry: $AZURE_CONTAINER_REGISTRY"
echo "   - Image: $IMAGE_NAME:$IMAGE_TAG"
echo "   - Full Image Name: $FULL_IMAGE_NAME"
echo "   - WebSurfer Support: ✅ ENABLED (Playwright browsers included)"
echo ""
echo "🔗 App URL: https://$APP_NAME.azurewebsites.net"
echo ""
echo "💡 Enhanced EOL Search is now available!"
echo "   Your app can now perform real-time web searches for EOL data using:"
echo "   - 🤖 Azure AI Agent Service (primary) - Modern AI-powered search with grounding"
echo "   - 🌐 WebSurfer (fallback) - Browser-based searches when needed"
echo "   - 📚 Static Knowledge Base (final fallback) - Curated EOL data"
echo "   All responses include proper source citations."
echo ""
echo "📊 To monitor deployment:"
echo "   az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "🔍 To verify the enhanced search is working, check the logs for:"
echo "   - 'Azure AI Agent Service initialized successfully with managed identity'"
echo "   - 'Using Azure AI Agent Service for [software] [version]'"
echo "   - 'WebSurfer health check: Azure App Service container mode detected'"
echo "   - 'Falling back to static EOL knowledge base' (if both fail)"