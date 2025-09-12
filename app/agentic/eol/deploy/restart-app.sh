#!/usr/bin/env zsh

# Restart an Azure Web App using values from appsettings.json (located next to this script by default).
# Usage: ./restart-app.sh [path/to/appsettings.json]
# Environment variables APP_NAME and RESOURCE_GROUP_NAME take precedence over values in appsettings.json.

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

APP_NAME_FROM_FILE=""
RESOURCE_GROUP_FROM_FILE=""

if command -v jq >/dev/null 2>&1; then
	APP_NAME_FROM_FILE=$(jq -r '.APP_NAME // empty' "$SETTINGS_FILE")
	RESOURCE_GROUP_FROM_FILE=$(jq -r '.RESOURCE_GROUP_NAME // empty' "$SETTINGS_FILE")
else
	# Fallback to python if jq isn't available
	if command -v python3 >/dev/null 2>&1; then
		parsed=$(python3 - <<PYTHON "$SETTINGS_FILE"
import sys, json
fn = sys.argv[1]
with open(fn) as f:
		j = json.load(f)
print(j.get('APP_NAME','') + ':::' + j.get('RESOURCE_GROUP_NAME',''))
PYTHON
)
		IFS=':::' read -r APP_NAME_FROM_FILE RESOURCE_GROUP_FROM_FILE <<< "$parsed"
	else
		echo "Neither jq nor python3 found; cannot parse $SETTINGS_FILE" >&2
		exit 3
	fi
fi

# Allow environment overrides
APP_NAME="${APP_NAME:-${APP_NAME_FROM_FILE:-}}"
RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-${RESOURCE_GROUP_FROM_FILE:-}}"

if [[ -z "$APP_NAME" || -z "$RESOURCE_GROUP_NAME" ]]; then
	echo "Missing required values. APP_NAME='$APP_NAME' RESOURCE_GROUP_NAME='$RESOURCE_GROUP_NAME'" >&2
	echo "Set environment variables APP_NAME and RESOURCE_GROUP_NAME or provide them in $SETTINGS_FILE" >&2
	exit 4
fi

echo "Restarting webapp '$APP_NAME' in resource group '$RESOURCE_GROUP_NAME'..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP_NAME"

echo "Restart requested."
