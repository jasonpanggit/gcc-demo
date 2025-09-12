# ============================================================================
# Windows Server 2025 Azure Arc Setup (Streamlined for Azure Custom Script Extension)
# Version bump: force redeploy to update remote blob content
# ----------------------------------------------------------------------------
# Purpose:
#   Deterministically install and connect the Azure Connected Machine (Arc) agent
#   when executed by the Azure Custom Script Extension (CSE).
#
# Characteristics:
#   - Assumes execution as LocalSystem (CSE context). No elevation logic needed.
#   - Provides idempotent firewall / environment prep (safe re-run).
#   - Explicit success (exit 0) / failure (exit 1) signaling for CSE status.
#   - Minimal sleeps; no infinite loops; network calls have timeouts.
#
# Exit Codes:
#   0  = Success (agent installed + connected)
#   1  = Failure (any handled error / exception)
#
# Logged Artifacts:
#   Transcript: C:\arc-setup.log
#   CSE captures stdout/stderr; key markers: AZURE_VM_EXTENSION_SUCCESS / FAILURE
#
# Parameters:
#   -ServicePrincipalId / -ServicePrincipalSecret : Creds for SPN used to onboard
#   -SubscriptionId / -ResourceGroup / -TenantId  : Target Azure scope
#   -Location                                     : Azure region for Arc resource
#   -ArcPrivateLinkScopeId                        : AMPLS / Arc PLS resource ID
#   -ProxyUrl (optional)                          : Outbound proxy (http/https)
# ============================================================================
param(
    [Parameter(Mandatory = $true)]  [string]$ServicePrincipalId,
    [Parameter(Mandatory = $true)]  [string]$ServicePrincipalSecret,
    [Parameter(Mandatory = $true)]  [string]$SubscriptionId,
    [Parameter(Mandatory = $true)]  [string]$ResourceGroup,
    [Parameter(Mandatory = $true)]  [string]$TenantId,
    [Parameter(Mandatory = $true)]  [string]$Location,
    [Parameter(Mandatory = $false)] [string]$ProxyUrl,
    [Parameter(Mandatory = $true)]  [string]$ArcPrivateLinkScopeId
)

# ----------------------------------------------------------------------------
# Global Settings
# ----------------------------------------------------------------------------
$LogPath               = "C:\arc-setup.log"
$ErrorActionPreference = "Stop"   # Make all errors terminating for uniform handling

Write-Host "=== Azure Arc Setup (Windows Server 2025) ==="
Write-Host "Timestamp: $(Get-Date)"
Write-Host "Subscription: $SubscriptionId | RG: $ResourceGroup | Location: $Location | Tenant: $TenantId"
Write-Host "Arc PLS: $ArcPrivateLinkScopeId"
# Proxy indicator (avoid PowerShell 7 ternary for Windows PowerShell 5.1 compatibility)
if ($ProxyUrl -and $ProxyUrl.Trim()) {
    Write-Host "Proxy: $ProxyUrl"
} else {
    Write-Host "Proxy: (none)"
}

# Attempt transcript logging (non-fatal if it fails in restricted contexts)
try { 
    Start-Transcript -Path $LogPath -Append -ErrorAction Stop 
} catch { 
    Write-Warning "Transcript start failed: $($_.Exception.Message)" 
}

try {
    # ------------------------------------------------------------------------
    # 1. Parameter Sanitization
    #    Remove stray single quotes (can appear due to Terraform templating)
    # ------------------------------------------------------------------------
    foreach ($n in 'ServicePrincipalId','ServicePrincipalSecret','SubscriptionId','ResourceGroup','TenantId','Location','ArcPrivateLinkScopeId','ProxyUrl') {
        $v = Get-Variable -Name $n -ValueOnly -ErrorAction SilentlyContinue
        if ($null -ne $v -and $v -is [string]) {
            Set-Variable -Name $n -Value ($v -replace "'", "")
        }
    }

    # ------------------------------------------------------------------------
    # 2. Environment Preparation
    #    - Mark test flag (if used for lab scenarios)
    #    - Optionally disable Azure Guest Agent (simulate non-Azure environment)
    #    - Block IMDS metadata endpoints (avoid Azure-VM identity ambiguity)
    #    - Allow outbound HTTPS for Arc agent
    # ------------------------------------------------------------------------
    $osVersion = (Get-CimInstance Win32_OperatingSystem).Caption
    Write-Host "OS: $osVersion"

    [System.Environment]::SetEnvironmentVariable("MSFT_ARC_TEST", 'true', [System.EnvironmentVariableTarget]::Machine)

    # IMPORTANT: The WindowsAzureGuestAgent is required for the Custom Script Extension to report its status.
    # While Arc evaluation docs suggest disabling it, doing so here will cause the extension to time out.
    # Blocking the IMDS endpoint is the more critical step for evaluation and is already handled.
    # $guest = Get-Service -Name WindowsAzureGuestAgent -ErrorAction SilentlyContinue
    # if ($guest) {
    #     Write-Host "Disabling WindowsAzureGuestAgent"
    #     Set-Service WindowsAzureGuestAgent -StartupType Disabled
    #     Stop-Service WindowsAzureGuestAgent -Force
    # }

    foreach ($addr in '169.254.169.254','169.254.169.253') {
        $ruleName = "BlockAzureIMDS-$addr"
        Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
        New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Enabled True -Profile Any -Direction Outbound -Action Block -RemoteAddress $addr -Protocol TCP -RemotePort 80 -ErrorAction SilentlyContinue | Out-Null
    }

    Remove-NetFirewallRule -Name AllowAzureArcAgentHTTPS -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name AllowAzureArcAgentHTTPS -DisplayName 'Allow Azure Arc Agent HTTPS' -Enabled True -Profile Any -Direction Outbound -Action Allow -Protocol TCP -RemotePort 443 -ErrorAction SilentlyContinue | Out-Null

    # ------------------------------------------------------------------------
    # 3. Export Variables Required by azcmagent connect
    # ------------------------------------------------------------------------
    $env:SUBSCRIPTION_ID = $SubscriptionId
    $env:RESOURCE_GROUP  = $ResourceGroup
    $env:TENANT_ID       = $TenantId
    $env:LOCATION        = $Location
    $env:AUTH_TYPE       = 'principal'
    $env:CORRELATION_ID  = '306d7da9-f090-4214-a588-b9db2886790e'  # Static correlation for traceability (optional)
    $env:CLOUD           = 'AzureCloud'

    # Enforce TLS 1.2 (3072) so downloads succeed in hardened environments
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072

    # ------------------------------------------------------------------------
    # 4. Download & Install Arc Agent (Proxy-aware, with fallback)
    # ------------------------------------------------------------------------
    $agentUrl    = 'https://gbl.his.arc.azure.com/azcmagent-windows'
    $agentScript = Join-Path $env:TEMP 'install_windows_azcmagent.ps1'
    Write-Host "Downloading agent installer... ($agentUrl)"

    $downloaded = $false
    if ($ProxyUrl -and ($ProxyUrl.Trim())) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $agentUrl -TimeoutSec 30 -OutFile $agentScript -Proxy $ProxyUrl
            $downloaded = $true
            Write-Host "Downloaded via proxy"
        } catch {
            Write-Warning "Proxy download failed: $($_.Exception.Message)"
        }
    }
    if (-not $downloaded) {
        Invoke-WebRequest -UseBasicParsing -Uri $agentUrl -TimeoutSec 30 -OutFile $agentScript
        Write-Host "Downloaded directly"
    }

    Write-Host "Installing Arc agent..."
    if ($ProxyUrl -and ($ProxyUrl.Trim())) { 
        & $agentScript -proxy $ProxyUrl 
    } else { 
        & $agentScript 
    }
    if ($LASTEXITCODE -ne 0) { throw "Arc agent installation failed with exit code $LASTEXITCODE" }

    # Allow brief initialization time (avoid premature connect errors)
    Start-Sleep -Seconds 10

    # ------------------------------------------------------------------------
    # 6. Connect Machine to Azure Arc (No Start-Process to avoid orphaning)
    # ------------------------------------------------------------------------
    $agentExe = 'C:\Program Files\AzureConnectedMachineAgent\azcmagent.exe'
    $connectArgs = @(
        'connect',
        '--service-principal-id', $ServicePrincipalId,
        '--service-principal-secret', $ServicePrincipalSecret,
        '--resource-group', $env:RESOURCE_GROUP,
        '--tenant-id', $env:TENANT_ID,
        '--location', $env:LOCATION,
        '--subscription-id', $env:SUBSCRIPTION_ID,
        '--cloud', $env:CLOUD,
        '--private-link-scope', $ArcPrivateLinkScopeId,
        '--correlation-id', $env:CORRELATION_ID
    )

    Write-Host "Connecting to Azure Arc (synchronous)..."
    & $agentExe @connectArgs
    $connectExitCode = $LASTEXITCODE
    Write-Host "Connect command exit code: $connectExitCode"

    # Exit code semantics (ref: Arc agent):
    # 0 = Connected successfully
    # 80 = Already connected (idempotent)
    # 81 = Already connected (scope / metadata difference but treated as connected)
    if ($connectExitCode -in 0,80,81) {
        if ($connectExitCode -eq 0) { Write-Host "Machine connected successfully (exit 0)" }
        elseif ($connectExitCode -eq 80) { Write-Host "Machine already connected (exit 80) - treating as success" }
        elseif ($connectExitCode -eq 81) { Write-Host "Machine already connected (exit 81) - treating as success" }
    } else {
        # Show diagnostics before failing
        Write-Warning "Arc connect failed (exit $connectExitCode). Collecting diagnostics..."
        try { & $agentExe show } catch { Write-Warning "Show command failed: $($_.Exception.Message)" }
        throw "Arc connect failed with exit code $connectExitCode"
    }

    # ------------------------------------------------------------------------
    # 7. Success Path
    # ------------------------------------------------------------------------
    Write-Host "Arc connection succeeded (exit code $connectExitCode)."
    Write-Output 'AZURE_VM_EXTENSION_SUCCESS: Arc setup completed with exit code 0'
    exit 0
    
}
catch {
    # ------------------------------------------------------------------------
    # Unified Failure Path (any exception or explicit throw)
    # ------------------------------------------------------------------------
    Write-Error $_.Exception.Message
    Write-Output "AZURE_VM_EXTENSION_FAILURE: $($_.Exception.Message)"
    exit 1
}
finally {
    # ------------------------------------------------------------------------
    # Cleanup: Stop transcript if active and flush output streams
    # ------------------------------------------------------------------------
    try { Stop-Transcript -ErrorAction SilentlyContinue } catch { }
    [Console]::Out.Flush(); [Console]::Error.Flush()
}