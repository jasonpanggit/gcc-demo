# Azure Arc Onboarding Script (Windows Server 2025)

This directory contains the PowerShell script used to onboard a Windows Server 2025 virtual machine to Azure Arc using a Service Principal, optionally via Private Link and an outbound proxy. The script is designed for deterministic execution under the Azure Custom Script Extension (CSE) as part of the Landing Zone deployment.

## File

### `windows-server-2025-arc-setup.ps1`
Installs and connects the Azure Connected Machine agent (azcmagent) with explicit success/failure signaling and guarded timeouts.

## Key Features
- Deterministic (bounded waits, no infinite loops)
- Cleans up stale azcmagent processes before connect
- Sanitizes Terraform-injected parameters (removes stray quotes)
- Optional proxy-aware download & connect
- Blocks Azure IMDS endpoints to emulate non-Azure environment
- Enforces TLS 1.2 for secure downloads
- Adds targeted firewall rules (allow HTTPS 443, block IMDS 169.254.169.x)
- Explicit exit codes (0 = success, 1 = failure) with CSE log markers

## Parameters
| Name | Required | Description |
|------|----------|-------------|
| `ServicePrincipalId` | Yes | App registration (client) ID used for Arc onboarding |
| `ServicePrincipalSecret` | Yes | Client secret for the Service Principal |
| `SubscriptionId` | Yes | Azure Subscription ID where Arc resource will reside |
| `ResourceGroup` | Yes | Target Resource Group for the Arc machine resource |
| `TenantId` | Yes | Azure AD tenant (directory) ID |
| `Location` | Yes | Azure region (e.g. eastus) for the Arc resource metadata |
| `ArcPrivateLinkScopeId` | Yes | Resource ID of the Arc-enabled Private Link Scope (AMPLS) |
| `ProxyUrl` | No | Optional HTTP/HTTPS proxy (e.g. http://proxy:8080) |

## Usage (Manual Invocation Example)
```powershell
# Run locally (must be elevated) if testing outside CSE
.\windows-server-2025-arc-setup.ps1 \
  -ServicePrincipalId "<appId>" \
  -ServicePrincipalSecret "<secret>" \
  -SubscriptionId "<subId>" \
  -ResourceGroup "rg-arc-demo" \
  -TenantId "<tenantId>" \
  -Location "eastus" \
  -ArcPrivateLinkScopeId "/subscriptions/<subId>/resourceGroups/rg-arc-demo/providers/Microsoft.HybridCompute/privateLinkScopes/pls-arc" \
  -ProxyUrl "http://proxy:8080"
```

## Terraform Integration
Provisioned automatically when:
```hcl
deploy_onprem_windows_server_2025 = true
onprem_windows_arc_setup          = true
```
The Custom Script Extension passes parameters from variables / outputs (SPN credentials, PLS scope ID, etc.).

## Logs & Diagnostics
- Transcript: `C:\arc-setup.log`
- Success Marker: `AZURE_VM_EXTENSION_SUCCESS`
- Failure Marker: `AZURE_VM_EXTENSION_FAILURE`

Check status:
```powershell
Get-Service AzureConnectedMachineAgent
& "C:\Program Files\AzureConnectedMachineAgent\azcmagent.exe" show
```

## Troubleshooting
| Symptom | Action |
|---------|--------|
| Timeout waiting for agent | Verify outbound 443 and that install script downloaded. Re-run script manually. |
| Connect exit code != 0 | Confirm SPN credentials & RBAC (Hybrid Connected Machines Onboarding role). |
| Proxy auth errors | Ensure proxy allows anonymous / or pre configure system proxy creds. |
| Arc resource not visible | Check correct subscription / RG; run `azcmagent show` for status. |

## Security Notes
- Use a least-privilege Service Principal (only needed roles for Arc onboarding).
- Rotate the SPN secret and store securely (Key Vault) if used beyond ephemeral labs.
- Private Link Scope ID restricts control plane traffic to private endpoints when configured.

---
For production, consider: Defender for Cloud integration, policy assignments, guest configuration baselines, and central logging.
