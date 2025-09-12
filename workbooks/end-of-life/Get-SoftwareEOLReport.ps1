#Requires -Version 5.1
<#
.SYNOPSIS
    Software End-of-Life Checker for Azure Arc Inventory

.DESCRIPTION
    This script extracts software inventory from Azure Arc-connected machines via Log Analytics
    and checks their End-of-Life status using the endoflife.date API.

.PARAMETER WorkspaceName
    Name of the Log Analytics workspace

.PARAMETER ResourceGroupName
    Resource group containing the Log Analytics workspace

.PARAMETER SubscriptionId
    Azure subscription ID

.PARAMETER DaysBack
    Number of days to look back for software inventory data (default: 7)

.PARAMETER OutputPath
    Path to save the EOL report (optional)

.PARAMETER ExportFormat
    Export format: CSV, JSON, or HTML (default: CSV)

.EXAMPLE
    .\Get-SoftwareEOLReport.ps1 -WorkspaceName "log-gcc-demo" -ResourceGroupName "rg-gcc-demo" -SubscriptionId "12345678-1234-1234-1234-123456789012"

.EXAMPLE
    .\Get-SoftwareEOLReport.ps1 -WorkspaceName "log-gcc-demo" -ResourceGroupName "rg-gcc-demo" -SubscriptionId "12345678-1234-1234-1234-123456789012" -OutputPath "C:\Reports\EOL-Report.csv" -ExportFormat "CSV"

.NOTES
    Author: IT Team
    Version: 1.0
    Updated: August 2025
    Requires: Az PowerShell module, Azure authentication
    API: Uses https://endoflife.date/docs/api/v1/
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceName,
    
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,
    
    [Parameter(Mandatory = $false)]
    [int]$DaysBack = 7,
    
    [Parameter(Mandatory = $false)]
    [string]$OutputPath,
    
    [Parameter(Mandatory = $false)]
    [ValidateSet("CSV", "JSON", "HTML")]
    [string]$ExportFormat = "CSV"
)

# Import required modules
try {
    Import-Module Az.Accounts -ErrorAction Stop
    Import-Module Az.OperationalInsights -ErrorAction Stop
}
catch {
    Write-Error "Required Azure PowerShell modules not found. Please install: Install-Module Az"
    exit 1
}

# Disable Azure PowerShell keychain integration on macOS to prevent password prompts
if ($IsMacOS) {
    Write-Host "🍎 Detected macOS - Using Azure CLI instead of PowerShell to avoid keychain prompts" -ForegroundColor Yellow
    [System.Environment]::SetEnvironmentVariable("AZURE_CORE_COLLECT_TELEMETRY", "false")
    [System.Environment]::SetEnvironmentVariable("MSAL_CACHE_ENABLED", "false")
}

# Software product mapping for EOL API
$productMapping = @{
    "Windows Server" = "windows-server"
    "Microsoft SQL Server" = "sql-server"
    "Internet Information Services" = "iis"
    ".NET Framework" = "dotnet"
    "Java" = "java"
    "Node.js" = "nodejs"
    "Python" = "python"
    "PHP" = "php"
    "Apache HTTP Server" = "apache"
    "nginx" = "nginx"
    "MySQL" = "mysql"
    "PostgreSQL" = "postgresql"
    "MongoDB" = "mongodb"
    "Redis" = "redis"
    "Elasticsearch" = "elasticsearch"
    "Docker" = "docker"
    "Kubernetes" = "kubernetes"
    "VMware vSphere ESXi" = "vmware-esxi"
    "Microsoft Office" = "office"
    "Microsoft Exchange Server" = "exchange"
    "Microsoft SharePoint" = "sharepoint"
    "Google Chrome" = "chrome"
    "Mozilla Firefox" = "firefox"
    "Microsoft Edge" = "edge"
    "Adobe Acrobat" = "acrobat"
    "Adobe Flash Player" = "flash"
}

# Function to normalize software names for API lookup
function Get-ProductKey {
    param([string]$SoftwareName)
    
    $normalizedName = $SoftwareName.ToLower()
    
    # Direct mapping first
    foreach ($key in $productMapping.Keys) {
        if ($normalizedName -like "*$($key.ToLower())*") {
            return $productMapping[$key]
        }
    }
    
    # Pattern-based mapping
    switch -Regex ($normalizedName) {
        "windows.*server" { return "windows-server" }
        "sql.*server" { return "sql-server" }
        "internet.*information" { return "iis" }
        "\.net.*framework" { return "dotnet" }
        "java.*runtime|java.*development" { return "java" }
        "node\.?js" { return "nodejs" }
        "python" { return "python" }
        "php" { return "php" }
        "apache.*http" { return "apache" }
        "nginx" { return "nginx" }
        "mysql" { return "mysql" }
        "postgresql|postgres" { return "postgresql" }
        "mongodb|mongo" { return "mongodb" }
        "redis" { return "redis" }
        "elasticsearch|elastic" { return "elasticsearch" }
        "docker" { return "docker" }
        "kubernetes|k8s" { return "kubernetes" }
        "vmware.*esxi" { return "vmware-esxi" }
        "microsoft.*office" { return "office" }
        "microsoft.*exchange" { return "exchange" }
        "microsoft.*sharepoint" { return "sharepoint" }
        "google.*chrome" { return "chrome" }
        "mozilla.*firefox" { return "firefox" }
        "microsoft.*edge" { return "edge" }
        "adobe.*acrobat" { return "acrobat" }
        "adobe.*flash" { return "flash" }
        default { return $null }
    }
}

# Function to check EOL status via API
function Get-EOLStatus {
    param(
        [string]$ProductKey,
        [string]$Version
    )
    
    try {
        $apiUrl = "https://endoflife.date/api/$ProductKey.json"
        Write-Verbose "Checking EOL for $ProductKey at $apiUrl"
        
        $response = Invoke-RestMethod -Uri $apiUrl -Method Get -TimeoutSec 10
        
        # Find matching cycle/version
        $matchedCycle = $response | Where-Object { 
            $_.cycle -eq $Version -or 
            $_.latest -like "*$Version*" -or
            $_.cycle -like "*$Version*"
        } | Select-Object -First 1
        
        if (-not $matchedCycle) {
            # Try to find closest match
            $matchedCycle = $response | Sort-Object { 
                if ($_.cycle -match '\d+') { [int]($_.cycle -replace '\D', '') } else { 0 }
            } -Descending | Select-Object -First 1
        }
        
        if ($matchedCycle) {
            $eolDate = if ($matchedCycle.eol -and $matchedCycle.eol -ne $false) { 
                try { [datetime]$matchedCycle.eol } catch { $null }
            } else { $null }
            
            $supportDate = if ($matchedCycle.support -and $matchedCycle.support -ne $false) { 
                try { [datetime]$matchedCycle.support } catch { $null }
            } else { $null }
            
            $status = if ($eolDate -and $eolDate -lt (Get-Date)) { 
                "End of Life" 
            } elseif ($supportDate -and $supportDate -lt (Get-Date)) { 
                "End of Support" 
            } else { 
                "Supported" 
            }
            
            $daysUntilEOL = if ($eolDate) { 
                [math]::Round(($eolDate - (Get-Date)).TotalDays) 
            } else { 
                $null 
            }
            
            return [PSCustomObject]@{
                Product = $ProductKey
                Cycle = $matchedCycle.cycle
                EOLDate = $eolDate
                SupportDate = $supportDate
                LatestVersion = $matchedCycle.latest
                LTS = $matchedCycle.lts
                Status = $status
                DaysUntilEOL = $daysUntilEOL
                RiskLevel = switch ($status) {
                    "End of Life" { "Critical" }
                    "End of Support" { "High" }
                    default { 
                        if ($daysUntilEOL -lt 90) { "High" }
                        elseif ($daysUntilEOL -lt 365) { "Medium" }
                        else { "Low" }
                    }
                }
                APIResponse = $true
            }
        }
    }
    catch {
        Write-Warning "Failed to get EOL data for $ProductKey : $($_.Exception.Message)"
        return [PSCustomObject]@{
            Product = $ProductKey
            Status = "API Error"
            APIResponse = $false
            Error = $_.Exception.Message
        }
    }
    
    return $null
}

# Main execution
Write-Host "🔍 Azure Arc Software EOL Report Generator" -ForegroundColor Cyan
Write-Host "=" * 50

# Authenticate to Azure using Azure CLI (avoiding PowerShell keychain issues on macOS)
try {
    Write-Host "🔐 Verifying Azure CLI authentication..." -ForegroundColor Yellow
    
    # Check if Azure CLI is authenticated
    $cliAccount = az account show --query "user.name" -o tsv 2>$null
    if (-not $cliAccount) {
        Write-Host "❌ Azure CLI not authenticated. Please run 'az login' first." -ForegroundColor Red
        exit 1
    }
    
    # Set the subscription
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set subscription: $SubscriptionId"
    }
    
    Write-Host "✅ Connected to Azure via CLI" -ForegroundColor Green
    Write-Host "✅ Account: $cliAccount" -ForegroundColor Green
    Write-Host "✅ Subscription: $SubscriptionId" -ForegroundColor Green
}
catch {
    Write-Error "Failed to authenticate to Azure: $($_.Exception.Message)"
    exit 1
}

# KQL query to get software inventory and OS details from Azure Arc agents
$kqlQuery = @"
// Get software inventory with machine information
let SoftwareInventory = ConfigurationData
    | where TimeGenerated > ago(30d)
    | where ConfigDataType == "Software"
    | extend SoftwareName = tostring(SoftwareName)
    | extend SoftwareVersion = tostring(CurrentVersion)
    | extend SoftwareVendor = tostring(Publisher)
    | extend SoftwareType = coalesce(tostring(SoftwareType), "Unknown")
    | extend SoftwareArchitecture = coalesce(tostring(Architecture), "Unknown")
    | extend SoftwareDescription = coalesce(tostring(SoftwareDescription), "Unknown")
    | where isnotempty(SoftwareName)
    | summarize 
        Versions = make_list(SoftwareVersion),
        MachineCount = dcount(Computer),
        Machines = make_list(Computer),
        SoftwareType = any(SoftwareType),
        SoftwareArchitecture = any(SoftwareArchitecture),
        SoftwareDescription = any(SoftwareDescription),
        LatestSeen = max(TimeGenerated)
        by SoftwareName, SoftwareVendor;

SoftwareInventory
| project 
    SoftwareName,
    SoftwareVendor,
    SoftwareType,
    SoftwareArchitecture,
    SoftwareDescription,
    Versions = tostring(Versions),
    MachineCount,
    Machines = tostring(Machines),
    LatestSeen
| order by MachineCount desc
"@

Write-Host "📊 Querying Log Analytics workspace: $WorkspaceName" -ForegroundColor Yellow

try {
    # Get workspace information using Azure CLI
    Write-Host "🔍 Getting workspace information..." -ForegroundColor Cyan
    $workspaceInfo = az monitor log-analytics workspace show --resource-group $ResourceGroupName --workspace-name $WorkspaceName --query "{customerId:customerId}" -o json | ConvertFrom-Json -AsHashTable
    
    if (-not $workspaceInfo.customerId) {
        throw "Workspace not found or access denied"
    }
    
    Write-Host "✅ Found workspace with ID: $($workspaceInfo.customerId)" -ForegroundColor Green
    
    # Execute KQL query using Azure CLI
    Write-Host "🔍 Executing KQL query..." -ForegroundColor Cyan
    $queryFile = [System.IO.Path]::GetTempFileName()
    $kqlQuery | Out-File -FilePath $queryFile -Encoding UTF8
    
    $queryResult = az monitor log-analytics query --workspace $workspaceInfo.customerId --analytics-query $kqlQuery --output json
    
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to execute query"
    }
    
    $results = $queryResult | ConvertFrom-Json -AsHashTable
    
    if (-not $results -or $results.Count -eq 0) {
        Write-Warning "No software inventory data found in the last $DaysBack days"
        exit 0
    }
    
    Write-Host "✅ Found $($results.Count) software products" -ForegroundColor Green
}
catch {
    Write-Error "Failed to query Log Analytics: $($_.Exception.Message)"
    exit 1
}

# Process software inventory and check EOL status
$eolReport = @()
$processedCount = 0
$totalCount = $results.Count

Write-Host "🔍 Checking EOL status for software products..." -ForegroundColor Yellow

foreach ($software in $results) {
    $processedCount++
    $progressPercent = [math]::Round(($processedCount / $totalCount) * 100)
    Write-Progress -Activity "Checking EOL Status" -Status "$processedCount of $totalCount" -PercentComplete $progressPercent
    
    $productKey = Get-ProductKey -SoftwareName $software.SoftwareName
    
    if ($productKey) {
        $versions = if ($software.Versions) { $software.Versions | ConvertFrom-Json -AsHashTable } else { @() }
        $primaryVersion = $versions | Select-Object -First 1
        
        # Parse OS details
        $osDetails = @()
        if ($software.OSDetails) {
            try {
                $osData = $software.OSDetails | ConvertFrom-Json -AsHashTable
                foreach ($os in $osData) {
                    if ($os.OSName) {
                        $osDetails += "$($os.Computer): $($os.OSName) $($os.OSVersion) ($($os.OSType))"
                    }
                }
            }
            catch {
                $osDetails = @("OS data parsing error")
            }
        }
        
        $eolStatus = Get-EOLStatus -ProductKey $productKey -Version $primaryVersion
        
        if ($eolStatus) {
            $reportItem = [PSCustomObject]@{
                SoftwareName = $software.SoftwareName
                SoftwareVendor = $software.SoftwareVendor
                SoftwareType = if ($software.SoftwareType) { $software.SoftwareType } else { "Unknown" }
                SoftwareArchitecture = if ($software.SoftwareArchitecture) { $software.SoftwareArchitecture } else { "Unknown" }
                SoftwareDescription = if ($software.SoftwareDescription) { $software.SoftwareDescription } else { "Unknown" }
                ProductKey = $productKey
                InstalledVersions = ($versions -join "; ")
                MachineCount = $software.MachineCount
                Machines = if ($software.Machines) { (($software.Machines | ConvertFrom-Json -AsHashTable) -join "; ") } else { "" }
                OSDetails = ($osDetails -join "; ")
                EOLStatus = $eolStatus.Status
                EOLDate = $eolStatus.EOLDate
                SupportDate = $eolStatus.SupportDate
                LatestVersion = $eolStatus.LatestVersion
                DaysUntilEOL = $eolStatus.DaysUntilEOL
                RiskLevel = $eolStatus.RiskLevel
                LTS = $eolStatus.LTS
                LatestSeen = $software.LatestSeen
                APIResponse = $eolStatus.APIResponse
            }
            $eolReport += $reportItem
        }
    }
    else {
        # Parse OS details for unmapped software
        $osDetails = @()
        if ($software.OSDetails) {
            try {
                $osData = $software.OSDetails | ConvertFrom-Json -AsHashTable
                foreach ($os in $osData) {
                    if ($os.OSName) {
                        $osDetails += "$($os.Computer): $($os.OSName) $($os.OSVersion) ($($os.OSType))"
                    }
                }
            }
            catch {
                $osDetails = @("OS data parsing error")
            }
        }
        
        # Add unmapped software for reference
        $reportItem = [PSCustomObject]@{
            SoftwareName = $software.SoftwareName
            SoftwareVendor = $software.SoftwareVendor
            SoftwareType = if ($software.SoftwareType) { $software.SoftwareType } else { "Unknown" }
            SoftwareArchitecture = if ($software.SoftwareArchitecture) { $software.SoftwareArchitecture } else { "Unknown" }
            SoftwareDescription = if ($software.SoftwareDescription) { $software.SoftwareDescription } else { "Unknown" }
            ProductKey = "Not Mapped"
            InstalledVersions = if ($software.Versions) { (($software.Versions | ConvertFrom-Json -AsHashTable) -join "; ") } else { "" }
            MachineCount = $software.MachineCount
            Machines = if ($software.Machines) { (($software.Machines | ConvertFrom-Json -AsHashTable) -join "; ") } else { "" }
            OSDetails = ($osDetails -join "; ")
            EOLStatus = "Unknown"
            RiskLevel = "Unknown"
            LatestSeen = $software.LatestSeen
            APIResponse = $false
        }
        $eolReport += $reportItem
    }
}

Write-Progress -Completed -Activity "Checking EOL Status"

# Generate summary statistics
$criticalCount = ($eolReport | Where-Object { $_.RiskLevel -eq "Critical" }).Count
$highRiskCount = ($eolReport | Where-Object { $_.RiskLevel -eq "High" }).Count
$eolCount = ($eolReport | Where-Object { $_.EOLStatus -eq "End of Life" }).Count
$supportedCount = ($eolReport | Where-Object { $_.EOLStatus -eq "Supported" }).Count

Write-Host ""
Write-Host "📈 EOL Report Summary" -ForegroundColor Cyan
Write-Host "=" * 30
Write-Host "🔴 Critical Risk: $criticalCount" -ForegroundColor Red
Write-Host "🟡 High Risk: $highRiskCount" -ForegroundColor Yellow
Write-Host "⚫ End of Life: $eolCount" -ForegroundColor DarkRed
Write-Host "✅ Supported: $supportedCount" -ForegroundColor Green
Write-Host "📊 Total Products: $($eolReport.Count)"

# Display top risks
$topRisks = $eolReport | Where-Object { $_.RiskLevel -in @("Critical", "High") } | Sort-Object RiskLevel, MachineCount -Descending | Select-Object -First 10

if ($topRisks) {
    Write-Host ""
    Write-Host "⚠️  Top Risk Products:" -ForegroundColor Red
    $topRisks | Format-Table SoftwareName, SoftwareType, RiskLevel, EOLStatus, MachineCount, DaysUntilEOL -AutoSize
}

# Export results
if ($OutputPath) {
    try {
        switch ($ExportFormat) {
            "CSV" {
                $eolReport | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8
                Write-Host "✅ Report exported to: $OutputPath" -ForegroundColor Green
            }
            "JSON" {
                $eolReport | ConvertTo-Json -Depth 3 | Out-File -FilePath $OutputPath -Encoding UTF8
                Write-Host "✅ Report exported to: $OutputPath" -ForegroundColor Green
            }
            "HTML" {
                $htmlReport = @"
<!DOCTYPE html>
<html>
<head>
    <title>Software EOL Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
        .summary { display: flex; gap: 20px; margin: 20px 0; }
        .card { background-color: #f8f9fa; padding: 15px; border-radius: 5px; flex: 1; text-align: center; }
        .critical { border-left: 5px solid #e74c3c; }
        .high { border-left: 5px solid #f39c12; }
        .medium { border-left: 5px solid #f1c40f; }
        .low { border-left: 5px solid #27ae60; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #34495e; color: white; }
        .eol { color: #e74c3c; font-weight: bold; }
        .supported { color: #27ae60; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Software End-of-Life Report</h1>
        <p>Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')</p>
        <p>Workspace: $WorkspaceName | Subscription: $SubscriptionId</p>
    </div>
    
    <div class="summary">
        <div class="card critical">
            <h3>$criticalCount</h3>
            <p>Critical Risk</p>
        </div>
        <div class="card high">
            <h3>$highRiskCount</h3>
            <p>High Risk</p>
        </div>
        <div class="card">
            <h3>$eolCount</h3>
            <p>End of Life</p>
        </div>
        <div class="card">
            <h3>$supportedCount</h3>
            <p>Supported</p>
        </div>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>Software Name</th>
                <th>Vendor</th>
                <th>Risk Level</th>
                <th>EOL Status</th>
                <th>Machines</th>
                <th>Days Until EOL</th>
                <th>Latest Version</th>
            </tr>
        </thead>
        <tbody>
"@
                foreach ($item in ($eolReport | Sort-Object RiskLevel, MachineCount -Descending)) {
                    $statusClass = if ($item.EOLStatus -eq "End of Life") { "eol" } else { "supported" }
                    $htmlReport += @"
            <tr class="$($item.RiskLevel.ToLower())">
                <td>$($item.SoftwareName)</td>
                <td>$($item.SoftwareVendor)</td>
                <td>$($item.RiskLevel)</td>
                <td class="$statusClass">$($item.EOLStatus)</td>
                <td>$($item.MachineCount)</td>
                <td>$($item.DaysUntilEOL)</td>
                <td>$($item.LatestVersion)</td>
            </tr>
"@
                }
                $htmlReport += @"
        </tbody>
    </table>
</body>
</html>
"@
                $htmlReport | Out-File -FilePath $OutputPath -Encoding UTF8
                Write-Host "✅ HTML report exported to: $OutputPath" -ForegroundColor Green
            }
        }
    }
    catch {
        Write-Error "Failed to export report: $($_.Exception.Message)"
    }
}
else {
    # Display results in console
    $eolReport | Sort-Object RiskLevel, MachineCount -Descending | Format-Table SoftwareName, RiskLevel, EOLStatus, MachineCount, DaysUntilEOL, LatestVersion -AutoSize
}

Write-Host ""
Write-Host "✅ EOL analysis complete!" -ForegroundColor Green
Write-Host "💡 Tip: Focus on Critical and High risk items first" -ForegroundColor Cyan
