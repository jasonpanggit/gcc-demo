#!/bin/bash

# Show Logs Script
# Reads app configuration from appsettings.json and streams logs for Azure Container Apps or App Service

set -e

# Parse environment parameter (default to production)
ENVIRONMENT=${1:-production}
shift || true

EXTRA_ARGS=("$@")

# Determine which settings file to use
SCRIPT_DIR="$(dirname "$0")"
SETTINGS_FILE="$SCRIPT_DIR/appsettings.$ENVIRONMENT.json"
DEFAULT_SETTINGS_FILE="$SCRIPT_DIR/appsettings.json"

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "⚠️  Settings file not found: $SETTINGS_FILE"
    echo "   Falling back to default appsettings.json"
    SETTINGS_FILE="$DEFAULT_SETTINGS_FILE"
fi

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "❌ No settings file found. Please ensure appsettings.json exists."
    exit 1
fi

echo "======================================="
echo "Azure Logs Viewer"
echo "Environment: $ENVIRONMENT"
echo "Settings File: $(basename "$SETTINGS_FILE")"
echo "======================================="

# Extract configuration values from JSON, supporting both legacy and nested formats
RESOURCE_GROUP=$(jq -r '.Azure.ResourceGroup // .RESOURCE_GROUP_NAME // empty' "$SETTINGS_FILE")
CONTAINER_APP_NAME=$(jq -r '.Deployment.ContainerApp.Name // .CONTAINER_APP_NAME // empty' "$SETTINGS_FILE")
CONTAINER_NAME=$(jq -r '.Deployment.ContainerApp.ContainerName // empty' "$SETTINGS_FILE")
APP_SERVICE_NAME=$(jq -r '.Deployment.AppService.Name // .APP_NAME // empty' "$SETTINGS_FILE")
SUBSCRIPTION_ID=$(jq -r '.Azure.SubscriptionId // .SUBSCRIPTION_ID // empty' "$SETTINGS_FILE")

# Fall back to default configuration when specific values are missing
if [[ "$SETTINGS_FILE" != "$DEFAULT_SETTINGS_FILE" && -f "$DEFAULT_SETTINGS_FILE" ]]; then
    if [[ -z "$RESOURCE_GROUP" ]]; then
        RESOURCE_GROUP=$(jq -r '.Azure.ResourceGroup // .RESOURCE_GROUP_NAME // empty' "$DEFAULT_SETTINGS_FILE")
    fi
    if [[ -z "$CONTAINER_APP_NAME" ]]; then
        CONTAINER_APP_NAME=$(jq -r '.Deployment.ContainerApp.Name // .CONTAINER_APP_NAME // empty' "$DEFAULT_SETTINGS_FILE")
    fi
    if [[ -z "$CONTAINER_NAME" ]]; then
        CONTAINER_NAME=$(jq -r '.Deployment.ContainerApp.ContainerName // empty' "$DEFAULT_SETTINGS_FILE")
    fi
    if [[ -z "$APP_SERVICE_NAME" ]]; then
        APP_SERVICE_NAME=$(jq -r '.Deployment.AppService.Name // .APP_NAME // empty' "$DEFAULT_SETTINGS_FILE")
    fi
    if [[ -z "$SUBSCRIPTION_ID" ]]; then
        SUBSCRIPTION_ID=$(jq -r '.Azure.SubscriptionId // .SUBSCRIPTION_ID // empty' "$DEFAULT_SETTINGS_FILE")
    fi
fi

if [[ -z "$RESOURCE_GROUP" ]]; then
    echo "❌ Failed to resolve the resource group from $SETTINGS_FILE"
    echo "   Ensure Azure.ResourceGroup or RESOURCE_GROUP_NAME is specified."
    exit 1
fi

# Ensure Azure CLI is authenticated and target subscription is set
if ! az account show >/dev/null 2>&1; then
    echo "❌ Azure CLI is not authenticated. Run 'az login' or 'az login --tenant <tenant-id>' and try again."
    exit 1
fi

if [[ -n "$SUBSCRIPTION_ID" ]]; then
    az account set --subscription "$SUBSCRIPTION_ID" >/dev/null 2>&1 || {
        echo "❌ Failed to set subscription $SUBSCRIPTION_ID. Ensure you have access."
        exit 1
    }
fi

# Determine target platform (prefer Container Apps when configured)
if [[ -n "$CONTAINER_APP_NAME" ]]; then
    echo "Target: Azure Container App"
    echo "Resource Group: $RESOURCE_GROUP"
    echo "Container App: $CONTAINER_APP_NAME"
    [[ -n "$CONTAINER_NAME" ]] && echo "Container Name: $CONTAINER_NAME"
    echo ""

    # Verify access to the Container App before streaming logs to give clearer errors (e.g., 401)
    set +e
    CHECK_OUTPUT=$(az containerapp show \
        --name "$CONTAINER_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query id -o tsv 2>&1)
    CHECK_STATUS=$?
    set -e

    if (( CHECK_STATUS != 0 )); then
        if [[ "$CHECK_OUTPUT" == *"401"* || "$CHECK_OUTPUT" == *"Unauthorized"* ]]; then
            echo "❌ Authorization failure when accessing the Container App (HTTP 401)."
            echo "   Ensure your Azure identity has at least the 'Azure Container Apps Reader' role"
            echo "   (or Contributor/Owner) on the resource group or container app, and try again."
        fi
        printf '%s
' "$CHECK_OUTPUT"
        exit $CHECK_STATUS
    fi

    # Automatically add --follow unless caller specifies follow behaviour
    ADD_FOLLOW=true
    PARSED_ARGS=()
    for arg in "${EXTRA_ARGS[@]}"; do
        if [[ "$arg" == "--follow" || "$arg" == "--no-follow" ]]; then
            ADD_FOLLOW=false
        fi
        if [[ "$arg" == "--no-follow" ]]; then
            # Do not pass --no-follow through to az, it is only for local control
            continue
        fi
        PARSED_ARGS+=("$arg")
    done

    CMD=(az containerapp logs show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP")
    [[ -n "$CONTAINER_NAME" ]] && CMD+=(--container "$CONTAINER_NAME")
    if $ADD_FOLLOW; then
        CMD+=(--follow)
    fi
    CMD+=("${PARSED_ARGS[@]}")

    echo "📋 Streaming Container App logs..."
    echo "   Press Ctrl+C to stop"
    echo ""

    ERR_FILE=$(mktemp)
    trap 'rm -f "$ERR_FILE"' EXIT

    set +e
    "${CMD[@]}" 2> >(tee "$ERR_FILE" >&2)
    STATUS=$?
    set -e

    if (( STATUS == 130 || STATUS == 0 )); then
        exit $STATUS
    fi

    if grep -q "429" "$ERR_FILE"; then
        echo "❌ Received HTTP 429 (Too Many Requests) while streaming logs."
        echo "   Container Apps can throttle log stream connections for up to 10 minutes after repeated attempts."
    echo "   Suggestions: close other log streams, wait before retrying, and use \"--no-follow --tail 200\" for a single snapshot."  
    echo "   If the throttle persists, query Log Analytics for historical logs instead of reopening the stream immediately."  
    fi

    rm -f "$ERR_FILE"
    trap - EXIT
    exit $STATUS

elif [[ -n "$APP_SERVICE_NAME" ]]; then
    echo "Target: Azure App Service"
    echo "Resource Group: $RESOURCE_GROUP"
    echo "App Name: $APP_SERVICE_NAME"
    echo ""

    CMD=(az webapp log tail --name "$APP_SERVICE_NAME" --resource-group "$RESOURCE_GROUP")
    CMD+=("${EXTRA_ARGS[@]}")

    echo "📋 Streaming App Service logs..."
    echo "   Press Ctrl+C to stop"
    echo ""

    ERR_FILE=$(mktemp)
    trap 'rm -f "$ERR_FILE"' EXIT

    set +e
    "${CMD[@]}" 2> >(tee "$ERR_FILE" >&2)
    STATUS=$?
    set -e

    if (( STATUS == 130 || STATUS == 0 )); then
        exit $STATUS
    fi

    if grep -q "429" "$ERR_FILE"; then
        echo "❌ Received HTTP 429 (Too Many Requests) while streaming logs."
        echo "   For App Service: ensure diagnostic logging is enabled and avoid opening multiple log streams simultaneously."
    fi

    rm -f "$ERR_FILE"
    trap - EXIT
    exit $STATUS

else
    echo "❌ Neither Deployment.ContainerApp.Name nor Deployment.AppService.Name/APP_NAME is defined in $SETTINGS_FILE"
    exit 1
fi