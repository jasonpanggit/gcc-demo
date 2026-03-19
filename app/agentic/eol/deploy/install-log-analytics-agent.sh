#!/bin/bash
# Install Log Analytics agent on Azure VMs for OS inventory collection
# This enables CVE scanning by providing normalized OS name and version data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPSETTINGS_FILE="$SCRIPT_DIR/appsettings.json"

# Check if appsettings.json exists
if [ ! -f "$APPSETTINGS_FILE" ]; then
    echo "❌ Error: appsettings.json not found at $APPSETTINGS_FILE"
    echo "Run ./generate-appsettings.sh first to create it"
    exit 1
fi

# Extract Log Analytics workspace ID from appsettings
WORKSPACE_ID=$(jq -r '.AzureServices.LogAnalytics.WorkspaceId // empty' "$APPSETTINGS_FILE")

if [ -z "$WORKSPACE_ID" ]; then
    echo "❌ Error: Could not extract Log Analytics workspace ID from appsettings.json"
    echo "Expected structure: .AzureServices.LogAnalytics.WorkspaceId"
    exit 1
fi

echo "=" | head -c 80
echo ""
echo "Log Analytics Agent Installation"
echo "=" | head -c 80
echo ""
echo ""
echo "📋 Workspace ID: $WORKSPACE_ID"
echo ""

# VMs that need the agent (don't have OS inventory data)
VMS_TO_INSTALL=(
    "jumphost:aml-rg"
    "arcgis-vm:arcgis-demo-rg"
    "image-vm:arcgis-demo-rg"
    "ManufacturingVM:contosoresourcegroup"
    "testvm1:contosoresourcegroup"
    "testvm2:contosoresourcegroup"
)

echo "🎯 Target VMs (6 total):"
for vm_rg in "${VMS_TO_INSTALL[@]}"; do
    VM_NAME="${vm_rg%%:*}"
    RG="${vm_rg##*:}"
    echo "   • $VM_NAME (Resource Group: $RG)"
done
echo ""

# Get workspace key (needs to be retrieved at runtime)
echo "🔑 Retrieving Log Analytics workspace key..."
WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
    --workspace-name "$(jq -r '.AzureServices.LogAnalytics.WorkspaceName // empty' "$APPSETTINGS_FILE")" \
    --resource-group "$(jq -r '.AzureServices.LogAnalytics.ResourceGroup // empty' "$APPSETTINGS_FILE")" \
    --query primarySharedKey \
    --output tsv)

if [ -z "$WORKSPACE_KEY" ]; then
    echo "❌ Failed to retrieve workspace key"
    exit 1
fi

echo "✅ Workspace key retrieved"
echo ""

# Install extension on each VM
for vm_rg in "${VMS_TO_INSTALL[@]}"; do
    VM_NAME="${vm_rg%%:*}"
    RG="${vm_rg##*:}"

    echo "🔧 Installing MicrosoftMonitoringAgent on $VM_NAME..."

    az vm extension set \
        --resource-group "$RG" \
        --vm-name "$VM_NAME" \
        --name MicrosoftMonitoringAgent \
        --publisher Microsoft.EnterpriseCloud.Monitoring \
        --protected-settings "{\"workspaceKey\":\"$WORKSPACE_KEY\"}" \
        --settings "{\"workspaceId\":\"$WORKSPACE_ID\"}" \
        --output table

    if [ $? -eq 0 ]; then
        echo "✅ Agent installed on $VM_NAME"
    else
        echo "⚠️  Failed to install agent on $VM_NAME (may already be installed)"
    fi
    echo ""
done

echo "=" | head -c 80
echo ""
echo "✅ Log Analytics Agent Installation Complete"
echo ""
echo "⏱️  Next Steps:"
echo "   1. Wait 5-10 minutes for agents to start reporting"
echo "   2. Verify OS inventory: curl .../api/os"
echo "   3. Run CVE scan: POST .../api/cve-scan/scan"
echo "   4. Check results: GET .../api/cve/inventory/overview"
echo ""
echo "=" | head -c 80
echo ""
