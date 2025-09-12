# Squid Proxy Configuration Script

This directory contains a shell script to bootstrap a Squid HTTP/HTTPS forward proxy for lab scenarios (e.g., controlling outbound traffic from on-prem / edge VMs toward Azure services when testing Private Link or restricted egress).

## File

### `squid-config.sh`
Installs and configures Squid with a minimal, permissive ACL suitable for isolated lab environments. Adjust before any production usage.

## Features
- Installs squid package (apt or yum detection can be added as needed)
- Backs up existing squid.conf (if present)
- Writes a simplified configuration allowing outbound traffic
- Restarts Squid service

## Example Manual Usage
```bash
chmod +x squid-config.sh
sudo ./squid-config.sh

# Validate service
systemctl status squid --no-pager

# Test from a client VM
curl -v -x http://<proxy-ip>:3128 https://www.microsoft.com/
```

## Terraform Integration
Not automatically invoked; wire it via a Custom Script Extension or cloud-init if you enable a proxy VM. Store any custom configuration (auth, ACLs) securely.

## Key Configuration Paths
| Item | Path |
|------|------|
| Main Config | /etc/squid/squid.conf |
| Access Logs | /var/log/squid/access.log |
| Cache Logs | /var/log/squid/cache.log |

## Hardening (Before Production)
| Area | Action |
|------|--------|
| ACLs | Restrict src networks & block unwanted destinations |
| TLS | Enable SSL Bump only if required; manage certs securely |
| Auth | Add Basic/NTLM/Negotiate authentication if multi-tenant |
| Logging | Forward logs to centralized SIEM / Log Analytics |
| Updates | Keep OS & squid package patched regularly |

## Troubleshooting
```bash
# Tail access log
tail -f /var/log/squid/access.log

# Check listening port
ss -ltnp | grep squid

# Verify process
ps -ef | grep squid
```

---
This script provides a quick-start baseline for controlled outbound routing tests. Extend with caching, ACL refinements, or authentication as needed.
