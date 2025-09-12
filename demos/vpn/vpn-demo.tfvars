# ==============================================================================
# VPN DEMONSTRATION CONFIGURATION
# ==============================================================================
# Complete Site-to-Site VPN connectivity between Azure Hub VNet and 
# simulated on-premises environment using Windows Server 2016
#
# DEPLOYMENT: terraform apply -var-file="credentials.tfvars" -var-file="demos/vpn/vpn-demo.tfvars"
# ESTIMATED COST: ~$1,250/month | DEPLOYMENT TIME: ~45-60 minutes
# ==============================================================================

# Basic Configuration
location     = "Australia East"
environment  = "demo"
project_name = "gcc"

# ==============================================================================
# CORE INFRASTRUCTURE
# ==============================================================================
deploy_hub_vnet     = true
deploy_hub_firewall = true
deploy_bastion      = true
deploy_vpn_gateway  = true

# VPN Gateway Configuration
vpn_gateway_sku        = "VpnGw1"
enable_vpn_gateway_bgp = true
vpn_gateway_bgp_asn    = 65516

# ==============================================================================
# ON-PREMISES SIMULATION
# ==============================================================================
deploy_onprem_vnet                = true
deploy_onprem_windows_server_2016 = true
onprem_windows_vpn_setup          = true

# BGP Configuration
enable_local_network_gateway_bgp = true
local_network_gateway_bgp_asn    = 65050

# VPN Security
onprem_vpn_shared_key = "VpnDemoSharedKey2025!"

# ==============================================================================
# SUPPORTING SERVICES
# ==============================================================================
deploy_script_storage     = true # Required for VPN automation
deploy_hub_onprem_peering = true # Hub-OnPrem connectivity