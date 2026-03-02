# Compute Module

Creates Linux and Windows VMs used by hybrid/demo scenarios.

## Resources created

- NICs and NSG associations for NVA, Squid, Win2016, Win2025
- Optional public IPs (scenario dependent)
- Linux VMs for NVA and Squid
- Windows VMs for on-prem simulation (2016 and 2025)

## Source of truth

- Inputs: `modules/compute/variables.tf`
- Outputs: `modules/compute/outputs.tf`
- Implementation: `modules/compute/main.tf`

Related scripts are under `scripts/arc`, `scripts/vpn`, `scripts/nva`, and `scripts/squid`.
