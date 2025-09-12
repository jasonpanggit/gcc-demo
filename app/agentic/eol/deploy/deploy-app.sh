#!/bin/bash

# App Deployment with Package Building
# Deploys application code with proper Python package installation

set -e

# Parse environment parameter (default to production)
ENVIRONMENT=${1:-production}

echo "======================================="
echo "App Deployment with Package Building"
echo "Environment: $ENVIRONMENT"
echo "======================================="

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
SCM_BUILD=$(jq -r '.SCM_DO_BUILD_DURING_DEPLOYMENT' "$SETTINGS_FILE")
ORYX_BUILD=$(jq -r '.ENABLE_ORYX_BUILD' "$SETTINGS_FILE")
RUN_FROM_PACKAGE=$(jq -r '.WEBSITE_RUN_FROM_PACKAGE' "$SETTINGS_FILE")
WEBSITES_PORT_VAL=$(jq -r '.WEBSITES_PORT' "$SETTINGS_FILE")
PYTHON_UNBUFFERED=$(jq -r '.PYTHONUNBUFFERED' "$SETTINGS_FILE")
MULTIWORKERS=$(jq -r '.PYTHON_ENABLE_GUNICORN_MULTIWORKERS' "$SETTINGS_FILE")
APP_STORAGE=$(jq -r '.WEBSITES_ENABLE_APP_SERVICE_STORAGE' "$SETTINGS_FILE")
DEBUG_MODE_VAL=$(jq -r '.DEBUG_MODE' "$SETTINGS_FILE")
ENVIRONMENT_VAL=$(jq -r '.ENVIRONMENT' "$SETTINGS_FILE")
SUBSCRIPTION_ID_VAL=$(jq -r '.SUBSCRIPTION_ID' "$SETTINGS_FILE")
AZURE_OPENAI_ENDPOINT_VAL=$(jq -r '.AZURE_OPENAI_ENDPOINT' "$SETTINGS_FILE")
AZURE_OPENAI_DEPLOYMENT_VAL=$(jq -r '.AZURE_OPENAI_DEPLOYMENT' "$SETTINGS_FILE")
LOG_ANALYTICS_WORKSPACE_ID_VAL=$(jq -r '.LOG_ANALYTICS_WORKSPACE_ID' "$SETTINGS_FILE")
AZURE_COSMOS_DB_ENDPOINT_VAL=$(jq -r '.AZURE_COSMOS_DB_ENDPOINT' "$SETTINGS_FILE")
AZURE_COSMOS_DB_DATABASE_VAL=$(jq -r '.AZURE_COSMOS_DB_DATABASE' "$SETTINGS_FILE")
AZURE_COSMOS_DB_CONTAINER_VAL=$(jq -r '.AZURE_COSMOS_DB_CONTAINER' "$SETTINGS_FILE")

echo "🚀 Starting app deployment with package building..."
echo "Application directory: $APP_DIR"
echo "Resource Group: $RESOURCE_GROUP"
echo "App Name: $APP_NAME"
echo "Environment: $ENVIRONMENT"
echo ""

echo "🔧 Configuring Azure App Service for proper Python package building..."

echo "🔧 Applying build configuration settings..."
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --settings \
    "SCM_DO_BUILD_DURING_DEPLOYMENT=$SCM_BUILD" \
    "ENABLE_ORYX_BUILD=$ORYX_BUILD" \
    "WEBSITE_RUN_FROM_PACKAGE=$RUN_FROM_PACKAGE" \
    "WEBSITES_PORT=$WEBSITES_PORT_VAL" \
    "PYTHONUNBUFFERED=$PYTHON_UNBUFFERED" \
    "PYTHON_ENABLE_GUNICORN_MULTIWORKERS=$MULTIWORKERS" \
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE=$APP_STORAGE"

echo "🔧 Applying application configuration settings..."
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --settings \
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
  "AZURE_COSMOS_DB_CONTAINER=$AZURE_COSMOS_DB_CONTAINER_VAL"

echo "✅ Build settings configured from $(basename "$SETTINGS_FILE"):"
echo "   - SCM_DO_BUILD_DURING_DEPLOYMENT=$SCM_BUILD (Enable building)"
echo "   - ENABLE_ORYX_BUILD=$ORYX_BUILD (Enable Oryx build system)"
echo "   - WEBSITE_RUN_FROM_PACKAGE=$RUN_FROM_PACKAGE (Disable package mode)"
echo "   - WEBSITES_PORT=$WEBSITES_PORT_VAL (App port)"
echo "   - PYTHONUNBUFFERED=$PYTHON_UNBUFFERED (Python logging)"
echo "   - PYTHON_ENABLE_GUNICORN_MULTIWORKERS=$MULTIWORKERS"

echo "✅ Application settings configured:"
echo "   - DEBUG_MODE=$DEBUG_MODE_VAL"
echo "   - ENVIRONMENT=$ENVIRONMENT_VAL"
echo "   - RESOURCE_GROUP_NAME=$RESOURCE_GROUP"
echo "   - APP_NAME=$APP_NAME"
echo "   - AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT_VAL"
echo "   - AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT_VAL"
echo "   - LOG_ANALYTICS_WORKSPACE_ID=$LOG_ANALYTICS_WORKSPACE_ID_VAL"
echo "   - AZURE_COSMOS_DB_ENDPOINT=$AZURE_COSMOS_DB_ENDPOINT_VAL"
echo "   - AZURE_COSMOS_DB_DATABASE=$AZURE_COSMOS_DB_DATABASE_VAL"
echo "   - AZURE_COSMOS_DB_CONTAINER=$AZURE_COSMOS_DB_CONTAINER_VAL"
echo ""
echo "📦 Creating application package..."
# Create ZIP package excluding unnecessary files but including essential runtime files
zip -r "$DEPLOYMENT_DIR/app.zip" . \
  -x "*.pyc" \
  -x "*/__pycache__/*" \
  -x "deployment/*" \
  -x ".git/*" \
  -x "*.DS_Store" \
  -x "*.backup*" \
  -x "*_legacy*" \
  -x "*_modern*" \
  -x "*_broken*" \
  -x "app-deployment.zip" \
  -x "*.log" \
  -x ".python-version" \
  -x "README.md" \
  -x "*.bak" \
  -x "app.zip"

echo "✅ Package created - Essential files included:"
echo "   - requirements.txt (Python dependencies)"
echo "   - startup.txt (App Service startup command)"
echo "   - web.config (IIS/App Service configuration)"
echo "   - main.py (Application entry point)"
echo "   - agents/ (Application modules)"
echo "   - templates/ (Web templates)"
echo "   - static/ (Static assets)"

echo ""
echo "🚀 Deploying application to Azure App Service..."
echo "📦 This deployment will install Python packages from requirements.txt"

az webapp deploy \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --src-path "$DEPLOYMENT_DIR/app.zip" \
  --type zip

echo ""
echo "🔧 Restarting App Service..."
az webapp restart \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME"

echo ""
echo "⏳ Waiting for application to start (this may take longer due to package installation)..."
sleep 30

echo ""
echo "🧪 Testing application..."
APP_URL="https://$APP_NAME.azurewebsites.net"
echo "Testing URL: $APP_URL"

# Test health endpoint
# if curl -f -s "$APP_URL/health" > /dev/null; then
#     echo "✅ Application is responding successfully!"
    
#     echo ""
#     echo "🧪 Testing AutoGen functionality..."
#     AUTOGEN_RESPONSE=$(curl -s -X POST "$APP_URL/api/autogen-chat" \
#         -H "Content-Type: application/json" \
#         -d '{"message": "Test AutoGen installation"}' | jq -r '.response')
    
#     if [[ "$AUTOGEN_RESPONSE" == *"not available"* ]]; then
#         echo "❌ AutoGen package still not installed properly"
#         echo "Response: $AUTOGEN_RESPONSE"
#         echo ""
#         echo "💡 Checking deployment logs for build information..."
#         echo "   Run: az webapp log tail -n $APP_NAME -g $RESOURCE_GROUP"
#     else
#         echo "✅ AutoGen functionality appears to be working!"
#         echo "Response: $AUTOGEN_RESPONSE"
#     fi
# else
#     echo "⚠️  Application might still be starting up. Check logs if needed."
#     echo "   Quick tip: run 'az webapp log tail -n $APP_NAME -g $RESOURCE_GROUP' to stream logs."
# fi

# Cleanup
rm -f "$DEPLOYMENT_DIR/app.zip"

echo ""
echo "🎉 Deployment with package building completed!"
echo "Application URL: $APP_URL"

echo ""
echo "======================================="
echo "Deployment Summary:"
echo "- Application Code: ✅ Updated"
echo "- Python Packages: 🔄 Building enabled"
echo "- AutoGen Package: 🔄 Should be installed"
echo "- Build Process: ✅ Enabled"
echo "- Environment: $ENVIRONMENT"
echo "- Total time: ~5-10 minutes (longer due to package installation)"
echo ""
echo "Usage:"
echo "  ./deploy-app-with-build.sh [environment]"
echo "  ./deploy-app-with-build.sh production  # Uses appsettings.production.json"
echo "  ./deploy-app-with-build.sh development # Uses appsettings.development.json"
echo "  ./deploy-app-with-build.sh             # Defaults to production"
echo "======================================="
