# Storage Module

Creates script storage used by VM custom script extension flows.

## Resources created (feature-flag dependent)

- Storage account for script hosting
- `scripts` container
- Arc script blob (`arc/windows-server-2025-arc-setup.ps1`)
- VPN script blob (`vpn/windows-server-2016-vpn-setup.ps1`)
- SAS token data source for script access

## Source of truth

- Inputs: `modules/storage/variables.tf`
- Outputs: `modules/storage/outputs.tf`
- Implementation: `modules/storage/main.tf`
