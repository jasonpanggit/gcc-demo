#!/bin/bash

# SSH Connection Script
# Reads app configuration from appsettings.json and establishes SSH connection

set -e

# Parse environment parameter (default to production)
ENVIRONMENT=${1:-production}

echo "======================================="
echo "Azure App Service SSH Connection"
echo "Environment: $ENVIRONMENT"
echo "======================================="

# Determine which settings file to use
SCRIPT_DIR="$(dirname "$0")"
SETTINGS_FILE="$SCRIPT_DIR/appsettings.$ENVIRONMENT.json"

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "⚠️  Settings file not found: $SETTINGS_FILE"
    echo "   Falling back to default appsettings.json"
    SETTINGS_FILE="$SCRIPT_DIR/appsettings.json"
fi

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "❌ No settings file found. Please ensure appsettings.json exists."
    exit 1
fi

echo "📄 Reading configuration from $(basename "$SETTINGS_FILE")..."

# Extract configuration values from JSON
RESOURCE_GROUP=$(jq -r '.RESOURCE_GROUP_NAME' "$SETTINGS_FILE")
APP_NAME=$(jq -r '.APP_NAME' "$SETTINGS_FILE")

if [[ "$RESOURCE_GROUP" == "null" || "$APP_NAME" == "null" ]]; then
    echo "❌ Failed to read RESOURCE_GROUP_NAME or APP_NAME from $SETTINGS_FILE"
    echo "   Please check the JSON format and required fields."
    exit 1
fi

echo "Resource Group: $RESOURCE_GROUP"
echo "App Name: $APP_NAME"
echo ""
echo "🔗 Establishing SSH connection..."
echo "   Note: SSH connection may take 30-60 seconds to establish"
echo "   You'll see the Azure App Service banner when connected"
echo ""

# Establish SSH connection
az webapp ssh --resource-group "$RESOURCE_GROUP" --name "$APP_NAME"