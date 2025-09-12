#Requires -Version 5.1
<#
.SYNOPSIS
    Deploy Software EOL Workbook to Azure Monitor

.DESCRIPTION
    This script deploys the Software Inventory End-of-Life workbook to Azure Monitor Workbooks.

.PARAMETER WorkbookPath
    Path to the workbook JSON file

.PARAMETER ResourceGroupName
    Resource group where the workbook will be created

.PARAMETER WorkbookName
    Name for the workbook in Azure

.PARAMETER SubscriptionId
    Azure subscription ID

.PARAMETER Location
    Azure region for the workbook (default: Australia East)

.EXAMPLE
    .\Deploy-SoftwareEOLWorkbook.ps1 -WorkbookPath ".\workbooks\software-inventory-eol-report.json" -ResourceGroupName "rg-gcc-demo" -WorkbookName "Software-EOL-Report" -SubscriptionId "12345678-1234-1234-1234-123456789012"

.NOTES
    Author: IT Team
    Version: 1.0
    Updated: August 2025
    Requires: Az PowerShell module, Azure authentication
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,
    
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory = $true)]
    [string]$WorkbookName,
    
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,
    
    [Parameter(Mandatory = $false)]
    [string]$Location = "Australia East"
)

# Import required modules
try {
    Import-Module Az.Accounts -ErrorAction Stop
    Import-Module Az.Resources -ErrorAction Stop
}
catch {
    Write-Error "Required Azure PowerShell modules not found. Please install: Install-Module Az"
    exit 1
}

# Disable Azure PowerShell keychain integration on macOS to prevent password prompts
if ($IsMacOS) {
    Write-Host "🍎 Detected macOS - Disabling keychain integration to prevent password prompts" -ForegroundColor Yellow
    
    # Set environment variables to disable keychain integration
    [System.Environment]::SetEnvironmentVariable("AZURE_CORE_COLLECT_TELEMETRY", "false")
    [System.Environment]::SetEnvironmentVariable("MSAL_CACHE_ENABLED", "false")
    [System.Environment]::SetEnvironmentVariable("AZURE_CORE_DISABLE_CONNECTION_SHARING", "true")
    [System.Environment]::SetEnvironmentVariable("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")
    
    # Try to disable context autosave, but ignore keychain errors
    try {
        Disable-AzContextAutosave -Scope Process -ErrorAction SilentlyContinue
        Write-Host "✅ Disabled Azure context autosave" -ForegroundColor Green
    }
    catch {
        Write-Host "⚠️  Note: Keychain autosave disable failed (expected on macOS) - continuing with environment variables" -ForegroundColor Yellow
    }
}

Write-Host "📊 Azure Monitor Workbook Deployment" -ForegroundColor Cyan
Write-Host "=" * 40

# Authenticate to Azure
try {
    Write-Host "🔐 Connecting to Azure PowerShell..." -ForegroundColor Yellow
    
    # First try to use existing context if available
    $currentContext = Get-AzContext -ErrorAction SilentlyContinue
    if ($currentContext -and $currentContext.Subscription.Id -eq $SubscriptionId) {
        Write-Host "✅ Using existing Azure context" -ForegroundColor Green
        Write-Host "✅ Account: $($currentContext.Account.Id)" -ForegroundColor Green
        Write-Host "✅ Subscription: $($currentContext.Subscription.Id)" -ForegroundColor Green
    }
    else {
        # Clear any existing context, with keychain-safe error handling
        try {
            Clear-AzContext -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Host "⚠️  Note: Context clear encountered keychain access - continuing" -ForegroundColor Yellow
        }
        
        # Try to disable autosave again, but handle keychain errors gracefully
        try {
            Disable-AzContextAutosave -Scope Process -ErrorAction SilentlyContinue
        } catch {
            Write-Host "⚠️  Note: Autosave disable encountered keychain access - using environment variables" -ForegroundColor Yellow
        }
        
        Write-Host "⚠️  Please authenticate using the device code shown below" -ForegroundColor Yellow
        Write-Host "⚠️  Use an account that has access to subscription: $SubscriptionId" -ForegroundColor Yellow
        Write-Host "⚠️  This will NOT prompt for keychain password" -ForegroundColor Green
        
        # Use device code authentication with additional parameters to avoid keychain
        try {
            $connectResult = Connect-AzAccount -UseDeviceAuthentication -Force -SkipContextPopulation -ErrorAction Stop
            if (-not $connectResult) {
                throw "Failed to connect to Azure"
            }
        }
        catch {
            Write-Host "❌ PowerShell Azure authentication failed: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "💡 Suggestion: This may be due to keychain issues on macOS" -ForegroundColor Yellow
            Write-Host "💡 Alternative: Use Azure CLI authentication instead" -ForegroundColor Yellow
            throw "Failed to authenticate to Azure: $($_.Exception.Message)"
        }
        
        # List available subscriptions for user reference
        try {
            $subscriptions = Get-AzSubscription -ErrorAction SilentlyContinue
            if ($subscriptions) {
                Write-Host "📋 Available subscriptions:" -ForegroundColor Cyan
                foreach ($sub in $subscriptions) {
                    $marker = if ($sub.Id -eq $SubscriptionId) { "✅" } else { "  " }
                    Write-Host "$marker $($sub.Name) ($($sub.Id))" -ForegroundColor White
                }
            }
        }
        catch {
            Write-Host "⚠️  Could not list subscriptions (credential issue)" -ForegroundColor Yellow
        }
    }
    
    # Try to set the context to the target subscription
    try {
        $currentContext = Set-AzContext -SubscriptionId $SubscriptionId -ErrorAction Stop
        Write-Host "✅ Successfully set context to target subscription" -ForegroundColor Green
    }
    catch {
        Write-Warning "Failed to access subscription $SubscriptionId"
        Write-Host "❌ Please ensure your account has access to the target subscription" -ForegroundColor Red
        Write-Host "💡 Available options:" -ForegroundColor Yellow
        Write-Host "   1. Use a different account with subscription access" -ForegroundColor White
        Write-Host "   2. Update the script with a subscription ID you have access to" -ForegroundColor White
        Write-Host "   3. Request access to subscription: $SubscriptionId" -ForegroundColor White
        throw "Subscription access denied: $($_.Exception.Message)"
    }
    
    Write-Host "✅ Connected to Azure subscription: $($currentContext.Subscription.Id)" -ForegroundColor Green
    Write-Host "✅ Account: $($currentContext.Account.Id)" -ForegroundColor Green
}
catch {
    Write-Error "Failed to authenticate to Azure: $($_.Exception.Message)"
    exit 1
}

# Validate workbook file exists
if (-not (Test-Path $WorkbookPath)) {
    Write-Error "Workbook file not found: $WorkbookPath"
    exit 1
}

# Read workbook template
try {
    $workbookContent = Get-Content -Path $WorkbookPath -Raw | ConvertFrom-Json
    Write-Host "✅ Workbook template loaded successfully" -ForegroundColor Green
}
catch {
    Write-Error "Failed to read workbook template: $($_.Exception.Message)"
    exit 1
}

# Generate unique workbook ID
$workbookId = [System.Guid]::NewGuid().ToString()

# Create ARM template for workbook deployment
$armTemplate = @{
    '$schema' = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    parameters = @{
        workbookDisplayName = @{
            type = "string"
            defaultValue = $WorkbookName
            metadata = @{
                description = "The friendly name for the workbook that is used in the Gallery or Saved List."
            }
        }
        workbookType = @{
            type = "string"
            defaultValue = "workbook"
            metadata = @{
                description = "The gallery that the workbook will been shown under."
            }
        }
        workbookSourceId = @{
            type = "string"
            defaultValue = "azure monitor"
            metadata = @{
                description = "The id associated with the workbook."
            }
        }
        workbookId = @{
            type = "string"
            defaultValue = $workbookId
            metadata = @{
                description = "The unique guid for this workbook instance."
            }
        }
    }
    resources = @(
        @{
            name = $workbookId
            type = "microsoft.insights/workbooks"
            location = $Location
            apiVersion = "2021-03-08"
            properties = @{
                displayName = "[parameters('workbookDisplayName')]"
                serializedData = ($workbookContent | ConvertTo-Json -Depth 100 -Compress)
                version = "1.0"
                sourceId = "[parameters('workbookSourceId')]"
                category = "[parameters('workbookType')]"
            }
            metadata = @{
                description = "Software Inventory End-of-Life Analysis Workbook"
            }
        }
    )
}

# Save ARM template to temporary file
$tempPath = [System.IO.Path]::GetTempFileName() + ".json"
$armTemplate | ConvertTo-Json -Depth 100 | Out-File -FilePath $tempPath -Encoding UTF8

try {
    Write-Host "🚀 Deploying workbook to resource group: $ResourceGroupName" -ForegroundColor Yellow
    
    # Deploy the workbook
    $deployment = New-AzResourceGroupDeployment -ResourceGroupName $ResourceGroupName -TemplateFile $tempPath -Verbose
    
    if ($deployment.ProvisioningState -eq "Succeeded") {
        Write-Host "✅ Workbook deployed successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "📋 Workbook Details:" -ForegroundColor Cyan
        Write-Host "   Name: $WorkbookName"
        Write-Host "   Resource Group: $ResourceGroupName"
        Write-Host "   Location: $Location"
        Write-Host "   Workbook ID: $workbookId"
        Write-Host ""
        Write-Host "🌐 Access your workbook at:" -ForegroundColor Yellow
        Write-Host "   https://portal.azure.com/#view/Microsoft_Azure_MonitoringMetrics/AzureMonitoringBrowseBlade/~/workbooks"
        Write-Host ""
        Write-Host "📝 Next Steps:" -ForegroundColor Cyan
        Write-Host "   1. Navigate to Azure Monitor > Workbooks"
        Write-Host "   2. Find your workbook: $WorkbookName"
        Write-Host "   3. Configure the Log Analytics workspace parameter"
        Write-Host "   4. Review software inventory and EOL status"
    }
    else {
        Write-Error "Deployment failed with state: $($deployment.ProvisioningState)"
        if ($deployment.Error) {
            Write-Error "Error details: $($deployment.Error.Message)"
        }
    }
}
catch {
    Write-Error "Failed to deploy workbook: $($_.Exception.Message)"
}
finally {
    # Clean up temporary file
    if (Test-Path $tempPath) {
        Remove-Item $tempPath -Force
    }
}

Write-Host ""
Write-Host "💡 Pro Tips:" -ForegroundColor Green
Write-Host "   • Enable software inventory on Azure Arc agents"
Write-Host "   • Schedule regular EOL checks using the PowerShell script"
Write-Host "   • Set up alerts for critical EOL software"
Write-Host "   • Review the workbook weekly for new risks"
