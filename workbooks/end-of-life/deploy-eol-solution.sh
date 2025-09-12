#!/bin/bash

# ==========================================================# Deploy workbook using Azure CLI (REST API approach)
echo "📊 Deploying Azure Monitor workbook..."
if [ -f "$WORKBOOK_SCRIPT" ]; then
    if "$WORKBOOK_SCRIPT" "$WORKBOOK_FILE" "$RESOURCE_GROUP" "$WORKBOOK_NAME" "$SUBSCRIPTION_ID" "$LOCATION"; then
        echo "✅ Workbook deployment completed"
    else
        echo "⚠️  Workbook deployment encountered issues, but continuing..."
        echo "💡 You can manually deploy the workbook later using:"
        echo "    $WORKBOOK_SCRIPT $WORKBOOK_FILE $RESOURCE_GROUP $WORKBOOK_NAME $SUBSCRIPTION_ID '$LOCATION'"
    fi
else
    echo "⚠️  Workbook deployment script not found: $WORKBOOK_SCRIPT"
    echo "💡 Using alternative REST API deployment..."
    if [ -f "./deploy-workbook-rest.sh" ]; then
        ./deploy-workbook-rest.sh "$WORKBOOK_FILE" "$RESOURCE_GROUP" "$WORKBOOK_NAME" "$SUBSCRIPTION_ID" "$LOCATION"
    else
        echo "❌ No workbook deployment script available"
    fi
fi
# Software End-of-Life Solution Deployment Script
# ============================================================================
# Automated deployment script for the Software EOL Analysis solution.
# Deploys Azure Monitor Workbook and demonstrates PowerShell automation.
# 
# Author: IT Team
# Version: 1.0
# Updated: August 2025
#
# Prerequisites:
# - Azure CLI installed and authenticated
# - PowerShell Core installed
# - Azure Arc agents with software inventory enabled
# - Valid Azure subscription and resource group
# ============================================================================

# Configuration
SUBSCRIPTION_ID="a87a8e64-a52a-4aa8-a760-5e8919d23cd1"
RESOURCE_GROUP="rg-gcc-demo"
WORKSPACE_NAME="log-gcc-demo"
WORKBOOK_NAME="Software-EOL-Report"
LOCATION="Australia East"

echo "🚀 Software EOL Solution Deployment"
echo "=================================="

# Step 1: Authenticate to Azure
echo "🔐 Authenticating to Azure..."

# Check if already logged in
if az account show --query "id" -o tsv 2>/dev/null | grep -q "$SUBSCRIPTION_ID"; then
    echo "✅ Already authenticated to target subscription"
else
    echo "🔑 Please authenticate to Azure..."
    az login
    
    # List available subscriptions
    echo "📋 Available subscriptions:"
    az account list --query "[].{Name:name, SubscriptionId:id, IsDefault:isDefault}" -o table
    
    # Try to set the subscription
    if az account set --subscription "$SUBSCRIPTION_ID" 2>/dev/null; then
        echo "✅ Successfully set subscription: $SUBSCRIPTION_ID"
    else
        echo "❌ Cannot access subscription: $SUBSCRIPTION_ID"
        echo "💡 Please ensure your account has access to this subscription"
        echo "💡 Or update SUBSCRIPTION_ID in this script to match an available subscription"
        exit 1
    fi
fi

# Verify subscription access
CURRENT_SUB=$(az account show --query "id" -o tsv 2>/dev/null)
if [ "$CURRENT_SUB" != "$SUBSCRIPTION_ID" ]; then
    echo "❌ Subscription mismatch. Current: $CURRENT_SUB, Expected: $SUBSCRIPTION_ID"
    exit 1
fi

echo "✅ Azure CLI authenticated to subscription: $SUBSCRIPTION_ID"

# Step 2: Verify Log Analytics workspace exists
echo "📊 Verifying Log Analytics workspace..."
if az monitor log-analytics workspace show --resource-group "$RESOURCE_GROUP" --workspace-name "$WORKSPACE_NAME" > /dev/null 2>&1; then
    echo "✅ Log Analytics workspace found: $WORKSPACE_NAME"
else
    echo "❌ Log Analytics workspace not found: $WORKSPACE_NAME"
    echo "Please create the workspace first or update the configuration"
    exit 1
fi

# Step 3: Deploy the workbook using Azure CLI (keychain-free)
echo "📈 Deploying Azure Monitor Workbook..."
echo "⚠️  Note: Using Azure CLI instead of PowerShell to avoid keychain issues"

# Get the script directory to use absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKBOOK_JSON="$SCRIPT_DIR/software-inventory-eol-report.json"
CLI_WORKBOOK_SCRIPT="$SCRIPT_DIR/deploy-workbook-rest.sh"

"$CLI_WORKBOOK_SCRIPT" "$WORKBOOK_JSON" "$RESOURCE_GROUP" "$WORKBOOK_NAME" "$SUBSCRIPTION_ID" "$LOCATION"

if [ $? -eq 0 ]; then
    echo "✅ Workbook deployed successfully!"
else
    echo "❌ Workbook deployment failed"
    exit 1
fi

# Step 4: Generate initial EOL report
echo "📋 Generating initial EOL report..."
echo "⚠️  Note: Using keychain-free PowerShell launcher to avoid password prompts"
echo "📊 Enhanced report includes Arc-enabled server OS and version information"
mkdir -p reports

EOL_REPORT_SCRIPT="Get-SoftwareEOLReport.ps1"
REPORTS_DIR="$SCRIPT_DIR/reports"
KEYCHAIN_FREE_LAUNCHER="$SCRIPT_DIR/run-ps-no-keychain.sh"

"$KEYCHAIN_FREE_LAUNCHER" "$EOL_REPORT_SCRIPT" -WorkspaceName "$WORKSPACE_NAME" -ResourceGroupName "$RESOURCE_GROUP" -SubscriptionId "$SUBSCRIPTION_ID" -DaysBack 30 -OutputPath "$REPORTS_DIR/initial-eol-report.csv" -ExportFormat "CSV"

# Step 5: Display next steps
echo ""
echo "🎉 Deployment Complete!"
echo "======================"
echo ""
echo "📊 Access your workbook:"
echo "   https://portal.azure.com/#view/Microsoft_Azure_MonitoringMetrics/AzureMonitoringBrowseBlade/~/workbooks"
echo ""
echo "📁 Initial report generated:"
echo "   ./reports/initial-eol-report.csv"
echo ""
echo "🔄 Next Steps:"
echo "   1. Open the workbook in Azure Monitor"
echo "   2. Configure workspace and time range parameters"
echo "   3. Review critical and high-risk software"
echo "   4. Set up scheduled reporting using the PowerShell script"
echo "   5. Create alerts for EOL software detection"
echo ""
echo "💡 Pro Tips:"
echo "   • Enable software inventory on all Arc agents"
echo "   • Schedule weekly EOL reports"
echo "   • Focus on Critical and High priority items first"
echo "   • Use the API links in the workbook for detailed EOL information"

# Optional: Create a scheduled task example (commented out)
# echo "⏰ Example: Create scheduled task for weekly reports"
# echo "   crontab -e"
# echo "   # Add this line for weekly reports every Monday at 9 AM:"
# echo "   0 9 * * 1 cd /path/to/solution && pwsh -Command './Get-SoftwareEOLReport.ps1 -WorkspaceName '$WORKSPACE_NAME' -ResourceGroupName '$RESOURCE_GROUP' -SubscriptionId '$SUBSCRIPTION_ID' -OutputPath \"./reports/weekly-eol-report-\$(date +%Y%m%d).csv\"'"
