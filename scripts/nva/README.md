# NVA (Network Virtual Appliance) Bootstrap Script

This directory contains a shell script used to configure a simple Linux-based Network Virtual Appliance (NVA) for routing / forwarding scenarios in the Landing Zone topology.

## File

### `nva-config.sh`
Configures basic packet forwarding and (optionally) NAT / firewall kernel parameters appropriate for lab routing scenarios.

## Features
- Enables IPv4 forwarding
- (Optionally) Disables IPv6 if variable-driven (adjust script if required)
- Flushes and sets minimal iptables rules (safe lab baseline)
- Persists sysctl changes

## Typical Responsibilities of the NVA in This Lab
- Acts as a transit hop between on-prem simulated networks and hub/spoke VNets
- Provides a place to experiment with custom routing / inspection logic

## Example Manual Usage
```bash
# Run with sudo on the NVA VM
chmod +x nva-config.sh
sudo ./nva-config.sh
```

## Terraform Integration
Script can be delivered via a Custom Script Extension or cloud-init depending on the image & module configuration (not automatically wired unless variables are enabled in your deployment). Adjust root module to upload and attach if needed.

## Post-Configuration Validation
```bash
# Check forwarding
sysctl net.ipv4.ip_forward

# Show routes
ip route

# Ping across subnets
ping -c 3 10.0.0.4
```

## Hardening Considerations (Production)
| Area | Recommendation |
|------|---------------|
| Firewall | Replace basic iptables flush with explicit allowlist rules |
| Logging | Enable connection logging for troubleshooting (ulog / nftables) |
| Updates | Apply automatic security updates (unattended-upgrades) |
| Monitoring | Install Azure Monitor / AMA or other telemetry agents |

---
This script is intentionally minimal—extend with NAT, DPI, or firewall policies as required for advanced scenarios.
