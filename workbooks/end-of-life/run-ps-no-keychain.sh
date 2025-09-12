#!/bin/bash

# ============================================================================
# macOS Keychain-Free Azure PowerShell Launcher
# ============================================================================
# Runs PowerShell scripts with environment variables set to avoid keychain prompts
# ============================================================================

# Export environment variables to disable Azure keychain integration
export AZURE_CORE_COLLECT_TELEMETRY=false
export MSAL_CACHE_ENABLED=false
export AZURE_CORE_DISABLE_CONNECTION_SHARING=true
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

# Disable PowerShell telemetry
export POWERSHELL_TELEMETRY_OPTOUT=1

echo "🍎 macOS Keychain-Free PowerShell Azure Environment"
echo "=================================================="
echo "✅ Disabled Azure keychain integration"
echo "✅ Disabled telemetry collection"
echo "✅ Using device code authentication only"
echo ""

# Check if PowerShell is available
if ! command -v pwsh &> /dev/null; then
    echo "❌ PowerShell Core not found"
    echo "💡 Install with: brew install --cask powershell"
    exit 1
fi

# Check if script argument provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <PowerShell-Script> [arguments...]"
    echo ""
    echo "Examples:"
    echo "  $0 Deploy-SoftwareEOLWorkbook.ps1 -WorkbookPath ./software-inventory-eol-report.json -ResourceGroupName rg-gcc-demo -WorkbookName Software-EOL-Report -SubscriptionId a87a8e64-a52a-4aa8-a760-5e8919d23cd1 -Location 'Australia East'"
    echo "  $0 Get-SoftwareEOLReport.ps1 -WorkspaceName log-gcc-demo -ResourceGroupName rg-gcc-demo -SubscriptionId a87a8e64-a52a-4aa8-a760-5e8919d23cd1"
    exit 1
fi

# Get the script directory for relative paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POWERSHELL_SCRIPT="$1"
shift # Remove first argument, keep the rest as PowerShell arguments

# Check if PowerShell script exists
if [ ! -f "$SCRIPT_DIR/$POWERSHELL_SCRIPT" ]; then
    echo "❌ PowerShell script not found: $SCRIPT_DIR/$POWERSHELL_SCRIPT"
    exit 1
fi

echo "🚀 Launching PowerShell script: $POWERSHELL_SCRIPT"
echo "📂 Working directory: $SCRIPT_DIR"
echo "🔧 Arguments: $@"
echo ""

# Launch PowerShell with keychain-safe environment
cd "$SCRIPT_DIR"

# Build the PowerShell command with properly escaped arguments
PS_ARGS=""
i=1
for arg in "$@"; do
    if [[ "$arg" == -* ]]; then
        # This is a parameter name (starts with -), don't quote it
        PS_ARGS="$PS_ARGS $arg"
    else
        # This is a parameter value, quote it properly
        escaped_arg=$(printf "%s" "$arg" | sed "s/'/'''/g")
        PS_ARGS="$PS_ARGS '$escaped_arg'"
    fi
done

# Execute PowerShell command with properly escaped arguments
pwsh -NoProfile -Command "& './$POWERSHELL_SCRIPT'$PS_ARGS"

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ PowerShell script completed successfully"
else
    echo "❌ PowerShell script failed with exit code: $exit_code"
fi

exit $exit_code
