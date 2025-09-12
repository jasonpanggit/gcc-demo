# Windows Server 2016 Site-to-Site VPN Setup Script
param(
    [Parameter(Mandatory = $true)]
    [string]$AzureVpnGatewayPublicIP,
    
    [Parameter(Mandatory = $true)]
    [string]$SharedKey,
    
    [Parameter(Mandatory = $false)]
    [string]$AzureNetworkCIDR = "172.16.0.0/16",
    
    [Parameter(Mandatory = $false)]
    [string]$ConnectionName = "Azure-S2S-VPN"
)

$ErrorActionPreference = "Stop"
$LogPath = "C:\vpn-setup.log"

$AzureVpnGatewayPublicIP = $AzureVpnGatewayPublicIP -replace "'", ""
$SharedKey = $SharedKey -replace "'", ""
$AzureNetworkCIDR = $AzureNetworkCIDR -replace "'", ""
$ConnectionName = $ConnectionName -replace "'", ""

Write-Host "Windows Server 2016 VPN Setup - $(Get-Date)"
Write-Host "Target: $AzureVpnGatewayPublicIP | Network: $AzureNetworkCIDR"

# Check admin privileges
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator privileges required"
}

# Start transcript logging
Start-Transcript -Path $LogPath -Append

try {
    # Install required Windows features
    Write-Host "Installing RRAS features..."
    $features = @("RemoteAccess", "Routing", "DirectAccess-VPN")
    foreach ($feature in $features) {
        if ((Get-WindowsFeature -Name $feature).InstallState -ne "Installed") {
            Install-WindowsFeature -Name $feature -IncludeManagementTools | Out-Null
        }
    }

    # Configure RRAS
    Write-Host "Configuring RRAS..."
    Import-Module RemoteAccess -Force
    try {
        Install-RemoteAccess -VpnType VpnS2S
    } catch {
        if ($_.Exception.Message -notlike "*already installed*") { throw }
    }

    # Ensure service is running
    Start-Service -Name "RemoteAccess" -ErrorAction SilentlyContinue

    # Create VPN connection
    Write-Host "Creating VPN connection..."
    
    # More thorough cleanup of existing interfaces
    Write-Host "Cleaning up any existing VPN interfaces..."
    try {
        Get-VpnS2SInterface | Where-Object { $_.Name -eq $ConnectionName } | ForEach-Object {
            Write-Host "Disconnecting existing interface: $($_.Name)"
            Disconnect-VpnS2SInterface -Name $_.Name -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 10
            Write-Host "Removing existing interface: $($_.Name)"
            Remove-VpnS2SInterface -Name $_.Name -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Host "[INFO] No existing interfaces to clean up"
    }

    # Test if destination IP is reachable before creating VPN interface
    Write-Host "Testing connectivity to destination: $AzureVpnGatewayPublicIP"
    if (Test-Connection -ComputerName $AzureVpnGatewayPublicIP -Count 2 -Quiet) {
        Write-Host "[OK] Destination is reachable"
    } else {
        Write-Host "[WARN] Destination may not be immediately reachable, continuing..."
    }

    Write-Host "Adding new VPN interface: $ConnectionName"
    Add-VpnS2SInterface -Name $ConnectionName `
                       -Protocol IKEv2 `
                       -Destination $AzureVpnGatewayPublicIP `
                       -AuthenticationMethod PSKOnly `
                       -SharedSecret $SharedKey `
                       -Persistent

    # Configure IPv6 to suppress warnings
    Write-Host "Configuring IPv6 settings..."
    try {
        Set-VpnIPAddressAssignment -IPv6Prefix "FE80::/64" -ErrorAction SilentlyContinue
    } catch {
        Write-Host "[INFO] IPv6 configuration warning can be ignored"
    }

    # Configure firewall rules
    Write-Host "Configuring firewall..."
    $firewallRules = @(
        @{Name="VPN-IKE"; Port=500; Protocol="UDP"},
        @{Name="VPN-IKEv2"; Port=4500; Protocol="UDP"},
        @{Name="VPN-ESP"; Port=50; Protocol="Any"}
    )

    foreach ($rule in $firewallRules) {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Protocol $rule.Protocol -LocalPort $rule.Port -Action Allow -Profile Any -ErrorAction SilentlyContinue
    }
    
    # Connect VPN and add routing
    Write-Host "Connecting VPN..."
    try {
        Connect-VpnS2SInterface -Name $ConnectionName
        Write-Host "[OK] VPN connection command executed"
    } catch {
        Write-Host "[WARN] VPN connection failed: $($_.Exception.Message)"
        Write-Host "This may be normal during initial setup - checking status..."
    }

    # Wait for connection and add route
    Start-Sleep -Seconds 10

    # Try multiple methods to find the VPN adapter
    $vpnAdapter = $null

    # Method 1: Look for RAS adapter
    $vpnAdapter = Get-NetAdapter | Where-Object { $_.InterfaceDescription -like "*RAS*" -or $_.Name -like "*VPN*" -or $_.Name -like "*$ConnectionName*" }

    # Method 2: If not found, try to get the VPN interface directly
    if (-not $vpnAdapter) {
        try {
            $vpnInterface = Get-VpnS2SInterface -Name $ConnectionName -ErrorAction SilentlyContinue
            if ($vpnInterface -and $vpnInterface.ConnectionState -eq "Connected") {
                # Use route command instead of PowerShell cmdlets for S2S VPN
                $gateway = ($vpnInterface.Destination)
                Write-Host "Adding route via route command for S2S VPN..."
                cmd /c "route add $AzureNetworkCIDR $gateway -p"
                Write-Host "Route added for $AzureNetworkCIDR via $gateway"
            } else {
                Write-Host "[INFO] VPN interface exists but not connected yet, adding persistent route..."
                # Add route that will work when connection establishes
                cmd /c "route add $AzureNetworkCIDR 0.0.0.0 metric 1 -p"
            }
        } catch {
            Write-Warning "Could not configure routes automatically: $($_.Exception.Message)"
        }
    } else {
        # Original method if adapter is found
        try {
            Remove-NetRoute -DestinationPrefix $AzureNetworkCIDR -Confirm:$false -ErrorAction SilentlyContinue
            New-NetRoute -DestinationPrefix $AzureNetworkCIDR -InterfaceIndex $vpnAdapter.InterfaceIndex -PolicyStore PersistentStore
            Write-Host "Route added for $AzureNetworkCIDR via adapter $($vpnAdapter.Name)"
        } catch {
            Write-Warning "Route configuration may require manual setup"
        }
    }

    # Final status check
    $vpnStatus = Get-VpnS2SInterface -Name $ConnectionName
    Write-Host "VPN Setup Complete!"
    Write-Host "Connection: $($vpnStatus.Name) - Status: $($vpnStatus.ConnectionState)"
    Write-Host "Gateway: $($vpnStatus.Destination)"

    # Basic connectivity test
    $testIP = ($AzureNetworkCIDR.Split('/')[0] -replace '\d+$', '4')
    Write-Host "Testing connectivity to $testIP..."
    if (Test-Connection -ComputerName $testIP -Count 2 -Quiet) {
        Write-Host "[OK] Connectivity test successful"
    } else {
        Write-Host "[WARN] Connectivity test failed - VPN may still be establishing"
    }

    Write-Host "Log saved to: $LogPath"
    exit 0

} catch {
    Write-Error "VPN Setup Failed: $($_.Exception.Message)"
    exit 1
} finally {
    Stop-Transcript -ErrorAction SilentlyContinue
}