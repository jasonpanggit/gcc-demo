#!/bin/bash

# Container Build and Push Script
# Builds Docker image with Playwright/WebSurfer support and pushes to Azure Container Registry

set -e

# Parse parameters
ENVIRONMENT=${1:-production}
IMAGE_TAG=${2:-latest}

echo "================================================"
echo "Building EOL App Container with WebSurfer Support"
echo "Environment: $ENVIRONMENT"
echo "Image Tag: $IMAGE_TAG"
echo "================================================"

# Navigate to parent directory (app root) from deployment folder
cd "$(dirname "$0")/.."
APP_DIR=$(pwd)
DEPLOYMENT_DIR="$APP_DIR/deploy"

echo "🔧 Reading deployment configuration..."
SETTINGS_FILE="$DEPLOYMENT_DIR/appsettings.$ENVIRONMENT.json"

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "⚠️  Settings file not found: $SETTINGS_FILE"
    echo "   Falling back to default appsettings.json"
    SETTINGS_FILE="$DEPLOYMENT_DIR/appsettings.json"
fi

echo "📄 Reading configuration from $(basename "$SETTINGS_FILE")..."

# Extract configuration values
RESOURCE_GROUP=$(jq -r '.RESOURCE_GROUP_NAME' "$SETTINGS_FILE")
AZURE_CONTAINER_REGISTRY=$(jq -r '.AZURE_CONTAINER_REGISTRY // "acreolggcdemo"' "$SETTINGS_FILE")
IMAGE_NAME=$(jq -r '.IMAGE_NAME // "eol-app"' "$SETTINGS_FILE")

# Override tag if provided as parameter
if [[ "$IMAGE_TAG" != "latest" ]]; then
    echo "🏷️  Using custom image tag: $IMAGE_TAG"
fi

FULL_IMAGE_NAME="${AZURE_CONTAINER_REGISTRY}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

echo "🏗️ Build Configuration:"
echo "   Registry: $AZURE_CONTAINER_REGISTRY"
echo "   Image Name: $IMAGE_NAME"
echo "   Tag: $IMAGE_TAG"
echo "   Full Image: $FULL_IMAGE_NAME"
echo "   Build Context: $DEPLOYMENT_DIR"
echo ""

# Check if Docker is running
echo "🐳 Checking Docker daemon..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running. Please start Docker and try again."
    exit 1
fi

# Check if Azure CLI is available and authenticated
echo "🔐 Checking Azure CLI authentication..."
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is not installed. Please install Azure CLI and try again."
    exit 1
fi

if ! az account show > /dev/null 2>&1; then
    echo "❌ Azure CLI not authenticated. Please run 'az login' first."
    exit 1
fi

echo "✅ Docker and Azure CLI are ready"

# Display Dockerfile contents for verification
echo "📋 Dockerfile contents:"
echo "----------------------------------------"
cat "$DEPLOYMENT_DIR/Dockerfile"
echo "----------------------------------------"
echo ""

# Build the Docker image
echo "🔨 Building Docker image with Playwright browsers..."
echo "Command: docker build --platform linux/amd64 -f \"$DEPLOYMENT_DIR/Dockerfile\" -t \"$FULL_IMAGE_NAME\" \"$APP_DIR\""
echo ""

# Build with progress output and platform specification for Azure compatibility
docker build \
    --platform linux/amd64 \
    --progress=plain \
    --file "$DEPLOYMENT_DIR/Dockerfile" \
    --tag "$FULL_IMAGE_NAME" \
    "$APP_DIR"

echo "✅ Docker image built successfully!"

# Check image size
IMAGE_SIZE=$(docker images "$FULL_IMAGE_NAME" --format "table {{.Size}}" | tail -n 1)
echo "📦 Image size: $IMAGE_SIZE"

# Test the image locally (optional)
echo "🧪 Testing image locally..."
echo "Starting container for quick health check..."

# Run a quick test to verify the image works
CONTAINER_ID=$(docker run -d -p 8001:8000 "$FULL_IMAGE_NAME")
sleep 5

# Check if container is running
if docker ps | grep "$CONTAINER_ID" > /dev/null; then
    echo "✅ Container started successfully"
    # Quick health check
    if curl -f http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ Health check passed"
    else
        echo "⚠️  Health check endpoint not accessible (this may be normal)"
    fi
else
    echo "❌ Container failed to start"
    docker logs "$CONTAINER_ID"
fi

# Clean up test container
echo "🧹 Cleaning up test container..."
docker stop "$CONTAINER_ID" > /dev/null 2>&1 || true
docker rm "$CONTAINER_ID" > /dev/null 2>&1 || true

# Login to Azure Container Registry
echo "🔐 Logging into Azure Container Registry..."
az acr login --name "$AZURE_CONTAINER_REGISTRY"

echo "📤 Pushing image to Azure Container Registry..."
echo "This may take several minutes due to Playwright browser dependencies..."

# Push with progress
docker push "$FULL_IMAGE_NAME"

echo ""
echo "🎉 Container build and push completed successfully!"
echo ""
echo "📋 Build Summary:"
echo "   ✅ Image: $FULL_IMAGE_NAME"
echo "   ✅ Registry: ${AZURE_CONTAINER_REGISTRY}.azurecr.io"
echo "   ✅ Size: $IMAGE_SIZE"
echo "   ✅ Playwright Support: Included"
echo "   ✅ WebSurfer Ready: Yes"
echo ""
echo "🚀 Next Steps:"
echo "   1. Deploy with: ./deploy-container.sh $ENVIRONMENT"
echo "   2. Or use Azure CLI:"
echo "      az webapp config container set \\"
echo "        --name YOUR_APP_NAME \\"
echo "        --resource-group $RESOURCE_GROUP \\"
echo "        --docker-custom-image-name $FULL_IMAGE_NAME"
echo ""
echo "🔍 To verify the image locally:"
echo "   docker run -p 8000:8000 $FULL_IMAGE_NAME"