#!/bin/bash
#
# create-teams-app-package.sh
# Creates a Teams app package with manifest and icons
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Read app URL from appsettings so webhook/status output is environment-specific.
APPSETTINGS_INPUT="../appsettings.json"
if [[ "$1" == "--config" || "$1" == "-c" ]]; then
    if [[ -z "$2" ]]; then
        echo "❌ Missing value for $1"
        echo "Usage: ./create-teams-app-package.sh [--config <appsettings.json>]"
        exit 1
    fi
    APPSETTINGS_INPUT="$2"
    shift 2
fi

if [[ "$APPSETTINGS_INPUT" = /* ]]; then
    APPSETTINGS_FILE="$APPSETTINGS_INPUT"
else
    APPSETTINGS_FILE="$SCRIPT_DIR/$APPSETTINGS_INPUT"
fi

if [ ! -f "$APPSETTINGS_FILE" ]; then
    echo "❌ Appsettings file not found at $APPSETTINGS_FILE"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "❌ jq is required to parse appsettings. Please install jq and retry."
    exit 1
fi

APP_URL=$(jq -r '.Deployment.ContainerApp.Url // empty' "$APPSETTINGS_FILE")
if [[ -z "$APP_URL" || "$APP_URL" == "null" ]]; then
    echo "❌ .Deployment.ContainerApp.Url is missing in $APPSETTINGS_FILE"
    exit 1
fi

# Remove trailing slash to avoid double slashes in endpoint paths.
APP_URL_BASE="${APP_URL%/}"
BOT_WEBHOOK_URL="$APP_URL_BASE/api/teams-bot/messages"
BOT_STATUS_URL="$APP_URL_BASE/api/teams-bot/status"

echo "=========================================="
echo "Teams App Package Creator"
echo "=========================================="
echo ""

# Check if ImageMagick is installed
if ! command -v convert &> /dev/null; then
    echo "⚠️  ImageMagick not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install imagemagick
    else
        echo "❌ Homebrew not found. Please install ImageMagick manually:"
        echo "   macOS: brew install imagemagick"
        echo "   Or download icons manually and place them in this directory"
        exit 1
    fi
fi

# Generate color icon (192x192) - Azure-style with geometric shapes
echo "🎨 Generating color icon (192x192)..."
convert -size 192x192 xc:'#0078D4' \
  -fill white \
  -draw "roundrectangle 48,60 144,100 8,8" \
  -draw "roundrectangle 48,108 144,148 8,8" \
  -draw "circle 76,128 76,118" \
  -draw "circle 116,128 116,118" \
  color.png

echo "✅ Created color.png (Azure-style with geometric shapes)"

# Generate outline icon (32x32) - Simple geometric design
echo "🎨 Generating outline icon (32x32)..."
convert -size 32x32 xc:transparent \
  -fill '#0078D4' \
  -draw "roundrectangle 8,10 24,16 2,2" \
  -draw "roundrectangle 8,18 24,24 2,2" \
  -draw "circle 12,21 12,19" \
  -draw "circle 20,21 20,19" \
  outline.png

echo "✅ Created outline.png (Simple geometric design)"

# Verify icon sizes
COLOR_SIZE=$(identify -format "%wx%h" color.png)
OUTLINE_SIZE=$(identify -format "%wx%h" outline.png)

if [ "$COLOR_SIZE" != "192x192" ]; then
    echo "❌ Error: color.png is $COLOR_SIZE, expected 192x192"
    exit 1
fi

if [ "$OUTLINE_SIZE" != "32x32" ]; then
    echo "❌ Error: outline.png is $OUTLINE_SIZE, expected 32x32"
    exit 1
fi

echo "✅ Icon sizes verified"

# Check if manifest exists
if [ ! -f "manifest.json" ]; then
    echo "❌ Error: manifest.json not found"
    exit 1
fi

# Validate manifest JSON
if ! python3 -m json.tool manifest.json > /dev/null 2>&1; then
    echo "❌ Error: manifest.json is not valid JSON"
    exit 1
fi

echo "✅ Manifest validated"

# Create the app package
PACKAGE_NAME="mcp-orchestrator-teams-app.zip"

if [ -f "$PACKAGE_NAME" ]; then
    echo "🗑️  Removing old package..."
    rm "$PACKAGE_NAME"
fi

echo "📦 Creating Teams app package..."
zip -q "$PACKAGE_NAME" manifest.json color.png outline.png

echo "✅ Created $PACKAGE_NAME"
echo ""

# Show package contents
echo "📋 Package contents:"
unzip -l "$PACKAGE_NAME"
echo ""

# Show installation instructions
echo "=========================================="
echo "✅ Teams App Package Created Successfully!"
echo "=========================================="
echo ""
echo "📦 Package location:"
echo "   $SCRIPT_DIR/$PACKAGE_NAME"
echo ""
echo "📥 To install in Microsoft Teams:"
echo ""
echo "1. Open Microsoft Teams"
echo "2. Click 'Apps' in the left sidebar"
echo "3. Click 'Manage your apps' or 'Upload an app'"
echo "4. Click 'Upload a custom app'"
echo "5. Select: $PACKAGE_NAME"
echo "6. Click 'Add' to install"
echo ""
echo "🤖 Once installed, try these commands:"
echo "   • Hello"
echo "   • List my resource groups"
echo "   • Show all container apps"
echo "   • Check health of my container app"
echo ""
echo "🔗 Bot webhook endpoint:"
echo "   $BOT_WEBHOOK_URL"
echo ""
echo "📊 Check bot status:"
echo "   curl $BOT_STATUS_URL"
echo ""
