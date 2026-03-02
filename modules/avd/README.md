# AVD Module

Creates Azure Virtual Desktop resources for the demo stack.

## Resources created

- AVD workspace, host pool, app group, and association
- Host pool registration token info
- Session host/private endpoint subnets and route table association
- FSLogix storage account + share + private endpoint + private DNS
- Session host VMs and AVD/AAD extensions
- Diagnostic settings for AVD components

## Source of truth

- Inputs: `modules/avd/variables.tf`
- Outputs: `modules/avd/outputs.tf`
- Implementation: `modules/avd/main.tf`
