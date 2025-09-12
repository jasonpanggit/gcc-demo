#!/bin/bash

# ============================================================================
# Azure REST API Workbook Deployment
# ============================================================================
# Direct REST API approach using Azure CLI for authentication
# ============================================================================

set -e

# Check if required parameters are provided
if [ $# -ne 5 ]; then
    echo "Usage: $0 <WorkbookPath> <ResourceGroupName> <WorkbookName> <SubscriptionId> <Location>"
    echo ""
    echo "Example:"
    echo "  $0 ./software-inventory-eol-report.json rg-gcc-demo Software-EOL-Report a87a8e64-a52a-4aa8-a760-5e8919d23cd1 'Australia East'"
    exit 1
fi

WORKBOOK_PATH="$1"
RESOURCE_GROUP="$2"
WORKBOOK_NAME="$3"
SUBSCRIPTION_ID="$4"
LOCATION="$5"

echo "🍎 Azure REST API Workbook Deployment"
echo "====================================="
echo "📊 Workbook: $WORKBOOK_NAME"
echo "📁 Template: $WORKBOOK_PATH"
echo "🏷️  Resource Group: $RESOURCE_GROUP"
echo "🌏 Location: $LOCATION"
echo ""

# Verify Azure CLI authentication
echo "🔐 Verifying Azure CLI authentication..."
if ! az account show --query "id" -o tsv >/dev/null 2>&1; then
    echo "❌ Not authenticated to Azure CLI"
    echo "💡 Please run: az login"
    exit 1
fi

CURRENT_SUB=$(az account show --query "id" -o tsv)
if [ "$CURRENT_SUB" != "$SUBSCRIPTION_ID" ]; then
    echo "⚠️  Current subscription ($CURRENT_SUB) doesn't match target ($SUBSCRIPTION_ID)"
    echo "🔄 Setting subscription context..."
    az account set --subscription "$SUBSCRIPTION_ID"
fi

echo "✅ Authenticated to subscription: $SUBSCRIPTION_ID"
echo "✅ Account: $(az account show --query "user.name" -o tsv)"

# Verify workbook template exists
if [ ! -f "$WORKBOOK_PATH" ]; then
    echo "❌ Workbook template not found: $WORKBOOK_PATH"
    exit 1
fi

echo "✅ Workbook template found: $WORKBOOK_PATH"

# Verify resource group exists
echo "📊 Verifying resource group..."
if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
    echo "❌ Resource group not found: $RESOURCE_GROUP"
    exit 1
fi

echo "✅ Resource group found: $RESOURCE_GROUP"

# Get access token
echo "🔑 Getting access token..."
ACCESS_TOKEN=$(az account get-access-token --query "accessToken" -o tsv)
if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Failed to get access token"
    exit 1
fi

echo "✅ Access token obtained"

# Generate unique workbook ID
WORKBOOK_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Create workbook using REST API
echo "🚀 Deploying workbook using Azure REST API..."

# Read workbook content
WORKBOOK_CONTENT=$(cat "$WORKBOOK_PATH")

# Create temporary payload file
PAYLOAD_FILE=$(mktemp)
cat > "$PAYLOAD_FILE" << EOF
{
    "kind": "shared",
    "properties": {
        "displayName": "$WORKBOOK_NAME",
        "serializedData": $(echo "$WORKBOOK_CONTENT" | jq -c . | jq -R .),
        "version": "1.0",
        "sourceId": "azure monitor",
        "category": "workbook"
    },
    "location": "$LOCATION"
}
EOF

# Make REST API call
WORKBOOK_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Insights/workbooks/$WORKBOOK_ID?api-version=2022-04-01"

echo "🔄 Creating workbook with ID: $WORKBOOK_ID"
echo "🌐 API URL: $WORKBOOK_URL"

if curl -s \
    -X PUT \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "@$PAYLOAD_FILE" \
    "$WORKBOOK_URL" \
    -o /tmp/workbook_response.json; then
    
    # Check response
    if jq -e '.error' /tmp/workbook_response.json >/dev/null 2>&1; then
        echo "❌ Workbook deployment failed:"
        jq '.error' /tmp/workbook_response.json
        rm -f "$PAYLOAD_FILE" /tmp/workbook_response.json
        exit 1
    else
        echo "✅ Workbook deployed successfully!"
        echo "📊 Workbook Name: $WORKBOOK_NAME"
        echo "🆔 Workbook ID: $WORKBOOK_ID"
        echo "🌐 Access via: https://portal.azure.com/#view/Microsoft_Azure_MonitoringMetrics/AzureMonitoringBrowseBlade/~/workbooks"
        
        # Show response details
        if [ -f /tmp/workbook_response.json ]; then
            echo "📋 Response: $(jq -r '.properties.displayName // "Success"' /tmp/workbook_response.json)"
        fi
    fi
else
    echo "❌ REST API call failed"
    rm -f "$PAYLOAD_FILE" /tmp/workbook_response.json
    exit 1
fi

# Cleanup
rm -f "$PAYLOAD_FILE" /tmp/workbook_response.json

echo ""
echo "🎉 Deployment Complete!"
echo "💡 Pro Tips:"
echo "   • Open Azure Monitor Workbooks in the Azure portal"
echo "   • Configure the Log Analytics workspace parameter"
echo "   • Set appropriate time ranges for EOL analysis"
echo "   • Review critical and high-risk software first"
