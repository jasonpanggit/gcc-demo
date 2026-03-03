# Tool Selection Test Report

**Generated:** 2026-03-02 11:57 UTC
**Target:** http://localhost:8000
**Total:** 67  |  ✅ Pass: 0  |  ❌ Fail: 0  |  ⚠️ Error: 67

## ❌ Failures / Errors

| Test | Query | Check | Expected | Plan Tools | Domains | Fast? |
|------|-------|-------|----------|------------|---------|-------|
list_subscriptions | `list my subscriptions` | plan_contains | `subscription_list` | — | — | no |
show_subscriptions | `show all my Azure subscriptions` | plan_contains | `subscription_list` | — | — | no |
list_resource_groups | `list my resource groups` | plan_any_prefix | `group_list|resource_group` | — | — | no |
show_storage_accounts | `show my storage accounts` | plan_contains | `storage_account_list` | — | — | no |
domain_azure_management | `list my subscriptions` | domain_contains | `azure_management` | — | — | no |
list_vnets | `list my virtual networks` | plan_contains | `virtual_network_list` | — | — | no |
show_vnets | `show all VNets` | plan_contains | `virtual_network_list` | — | — | no |
vnets_not_test_conn | `list my virtual networks` | plan_not_contains | `test_network_connectivity` | — | — | no |
vnets_not_check_dns | `show my virtual networks` | plan_not_contains | `check_dns_resolution` | — | — | no |
vnet_domain | `list my virtual networks` | domain_contains | `network|azure_management` | — | — | no |
list_nsgs | `list my network security groups` | plan_contains | `nsg_list` | — | — | no |
nsgs_not_assess_posture | `list my network security groups` | plan_not_contains | `assess_network_security_posture` | — | — | no |
list_private_endpoints | `list my private endpoints` | plan_contains | `private_endpoint_list` | — | — | no |
show_private_endpoints | `show all private endpoints in my subscription` | plan_contains | `private_endpoint_list` | — | — | no |
inspect_nsg_rules | `show rules for my NSG nsg-prod` | plan_contains | `inspect_nsg_rules` | — | — | no |
nsg_rules_not_nsg_list | `show rules for my NSG nsg-prod` | plan_not_contains | `nsg_list` | — | — | no |
effective_routes | `show effective routes for my NIC` | plan_any_prefix | `get_effective_routes|effective_routes` | — | — | no |
appgw_health | `check Application Gateway health` | plan_contains | `inspect_appgw_waf` | — | — | no |
waf_policy | `show WAF policy for my App Gateway` | plan_contains | `inspect_appgw_waf` | — | — | no |
vpn_gateway | `check VPN gateway status` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
expressroute | `show ExpressRoute circuit state` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
test_connectivity | `test network connectivity from my VM to the database` | plan_any_prefix | `test_network|connectivity|azure_cli` | — | — | no |
check_dns | `check DNS resolution for api.example.com` | plan_any_prefix | `dns|check_dns|azure_cli` | — | — | no |
network_inventory | `inventory my network resources` | plan_contains | `inventory_network_resources` | — | — | no |
hub_spoke_validate | `validate my hub-spoke topology` | plan_contains | `validate_hub_spoke_topology` | — | — | no |
hub_spoke_health | `is my hub-spoke topology healthy` | plan_any_prefix | `validate_hub_spoke|hub_spoke|hub` | — | — | no |
connectivity_matrix | `generate connectivity matrix for my subnets` | plan_any_prefix | `generate_connectivity|connectivity_matrix|connectivity` | — | — | no |
route_path_analysis | `analyze route path from my subnet to www.microsoft.com` | plan_any_prefix | `analyze_route|route_path|route` | — | — | no |
nsg_flow_simulate | `simulate NSG flow from my VM to port 443` | plan_any_prefix | `simulate_nsg|nsg_flow|simulate` | — | — | no |
private_coverage | `analyze private endpoint coverage for zero-trust` | plan_any_prefix | `analyze_private|private_connect|private_endpoint` | — | — | no |
dns_path | `trace DNS resolution path from vnet-prod for api.example.com` | plan_any_prefix | `analyze_dns|dns_resolution_path|dns` | — | — | no |
security_posture | `assess my network security posture` | plan_contains | `assess_network_security_posture` | — | — | no |
posture_not_nsg_list | `assess my network security posture` | plan_not_contains | `nsg_list` | — | — | no |
posture_not_fast_path | `assess my network security posture` | fast_path_false | `` | — | — | no |
list_vnets_and_subnets | `list my virtual networks and subnets` | plan_contains | `virtual_network_list` | — | — | no |
vnets_subnets_not_describe | `list my virtual networks and subnets` | plan_not_contains | `describe_capabilities` | — | — | no |
show_vnets_subnets | `show my VNets and their subnets` | plan_contains | `virtual_network_list` | — | — | no |
inspect_vnet_peering | `show VNet peering status` | plan_contains | `inspect_vnet` | — | — | no |
inspect_vnet_address_space | `show VNet address space and subnets` | plan_contains | `inspect_vnet` | — | — | no |
inspect_vnet_not_list | `show VNet peering status` | plan_not_contains | `virtual_network_list` | — | — | no |
simulate_not_nsg_list | `will traffic from my VM be allowed on port 443` | plan_not_contains | `nsg_list` | — | — | no |
dns_path_not_check_dns | `trace DNS resolution path from vnet-prod for api.example.com` | plan_not_contains | `check_dns_resolution` | — | — | no |
private_cov_not_list_ep | `which PaaS services are not using private endpoints` | plan_not_contains | `private_endpoint_list` | — | — | no |
connectivity_matrix_no_fp | `generate connectivity matrix for my subnets` | fast_path_false | `` | — | — | no |
simulate_nsg_no_fp | `simulate NSG flow from my VM to port 443` | fast_path_false | `` | — | — | no |
route_path_no_fp | `analyze route path from my subnet to www.microsoft.com` | fast_path_false | `` | — | — | no |
private_cov_no_fp | `analyze private endpoint coverage for zero-trust` | fast_path_false | `` | — | — | no |
dns_path_no_fp | `trace DNS resolution path from vnet-prod for api.example.com` | fast_path_false | `` | — | — | no |
network_inventory_unused | `find unused network resources` | plan_contains | `inventory_network_resources` | — | — | no |
network_inventory_cost | `network resource inventory for cost optimization` | plan_contains | `inventory_network_resources` | — | — | no |
hub_spoke_alt | `check hub-spoke architecture health` | plan_any_prefix | `validate_hub_spoke|hub_spoke` | — | — | no |
expressroute_circuit | `check ExpressRoute circuit health` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
appgw_alt | `inspect my Application Gateway WAF` | plan_contains | `inspect_appgw_waf` | — | — | no |
security_posture_cis | `run CIS Azure network compliance check` | plan_contains | `assess_network_security_posture` | — | — | no |
security_posture_nist | `check network compliance against NIST` | plan_contains | `assess_network_security_posture` | — | — | no |
list_vms | `list my virtual machines` | plan_contains | `virtual_machine_list` | — | — | no |
show_vms | `show all VMs in my subscription` | plan_contains | `virtual_machine_list` | — | — | no |
os_inventory | `what OS are my VMs running` | plan_any_prefix | `os|inventory|eol|law` | — | — | no |
eol_lookup | `show end of life software on my servers` | plan_any_prefix | `eol|end_of_life|os_eol|law_get_software` | — | — | no |
eol_domain | `which of my VMs have end-of-life operating systems` | domain_contains | `arc_inventory` | — | — | no |
container_health_domain | `check health of my container apps` | domain_contains | `sre_health|sre_incident|observability` | — | — | no |
container_error_domain | `why is my container app returning 503 errors` | domain_contains | `sre_health|sre_incident|observability` | — | — | no |
fast_path_simple | `list my subscriptions` | fast_path_true | `` | — | — | no |
not_fast_path_complex | `list my VMs then restart any that are stopped and show me the results` | fast_path_false | `` | — | — | no |
cli_in_retrieved_vnets | `list my virtual networks` | plan_any_prefix | `virtual_network_list|azure_cli` | — | — | no |
action_tools_filtered_vnets | `list my virtual networks` | plan_no_prefix | `test_|check_|create_|delete_|restart_` | — | — | no |
action_tools_filtered_subs | `list my subscriptions` | plan_no_prefix | `test_|check_|create_|delete_|restart_` | — | — | no |

## All Results

| Status | Test | Query | Check | Expected | Plan Tools | Domains | Fast? |
|--------|------|-------|-------|----------|------------|---------|-------|
| ⚠️ | list_subscriptions | `list my subscriptions` | plan_contains | `subscription_list` | — | — | no |
| ⚠️ | show_subscriptions | `show all my Azure subscriptions` | plan_contains | `subscription_list` | — | — | no |
| ⚠️ | list_resource_groups | `list my resource groups` | plan_any_prefix | `group_list|resource_group` | — | — | no |
| ⚠️ | show_storage_accounts | `show my storage accounts` | plan_contains | `storage_account_list` | — | — | no |
| ⚠️ | domain_azure_management | `list my subscriptions` | domain_contains | `azure_management` | — | — | no |
| ⚠️ | list_vnets | `list my virtual networks` | plan_contains | `virtual_network_list` | — | — | no |
| ⚠️ | show_vnets | `show all VNets` | plan_contains | `virtual_network_list` | — | — | no |
| ⚠️ | vnets_not_test_conn | `list my virtual networks` | plan_not_contains | `test_network_connectivity` | — | — | no |
| ⚠️ | vnets_not_check_dns | `show my virtual networks` | plan_not_contains | `check_dns_resolution` | — | — | no |
| ⚠️ | vnet_domain | `list my virtual networks` | domain_contains | `network|azure_management` | — | — | no |
| ⚠️ | list_nsgs | `list my network security groups` | plan_contains | `nsg_list` | — | — | no |
| ⚠️ | nsgs_not_assess_posture | `list my network security groups` | plan_not_contains | `assess_network_security_posture` | — | — | no |
| ⚠️ | list_private_endpoints | `list my private endpoints` | plan_contains | `private_endpoint_list` | — | — | no |
| ⚠️ | show_private_endpoints | `show all private endpoints in my subscription` | plan_contains | `private_endpoint_list` | — | — | no |
| ⚠️ | inspect_nsg_rules | `show rules for my NSG nsg-prod` | plan_contains | `inspect_nsg_rules` | — | — | no |
| ⚠️ | nsg_rules_not_nsg_list | `show rules for my NSG nsg-prod` | plan_not_contains | `nsg_list` | — | — | no |
| ⚠️ | effective_routes | `show effective routes for my NIC` | plan_any_prefix | `get_effective_routes|effective_routes` | — | — | no |
| ⚠️ | appgw_health | `check Application Gateway health` | plan_contains | `inspect_appgw_waf` | — | — | no |
| ⚠️ | waf_policy | `show WAF policy for my App Gateway` | plan_contains | `inspect_appgw_waf` | — | — | no |
| ⚠️ | vpn_gateway | `check VPN gateway status` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
| ⚠️ | expressroute | `show ExpressRoute circuit state` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
| ⚠️ | test_connectivity | `test network connectivity from my VM to the database` | plan_any_prefix | `test_network|connectivity|azure_cli` | — | — | no |
| ⚠️ | check_dns | `check DNS resolution for api.example.com` | plan_any_prefix | `dns|check_dns|azure_cli` | — | — | no |
| ⚠️ | network_inventory | `inventory my network resources` | plan_contains | `inventory_network_resources` | — | — | no |
| ⚠️ | hub_spoke_validate | `validate my hub-spoke topology` | plan_contains | `validate_hub_spoke_topology` | — | — | no |
| ⚠️ | hub_spoke_health | `is my hub-spoke topology healthy` | plan_any_prefix | `validate_hub_spoke|hub_spoke|hub` | — | — | no |
| ⚠️ | connectivity_matrix | `generate connectivity matrix for my subnets` | plan_any_prefix | `generate_connectivity|connectivity_matrix|connectivity` | — | — | no |
| ⚠️ | route_path_analysis | `analyze route path from my subnet to www.microsoft.com` | plan_any_prefix | `analyze_route|route_path|route` | — | — | no |
| ⚠️ | nsg_flow_simulate | `simulate NSG flow from my VM to port 443` | plan_any_prefix | `simulate_nsg|nsg_flow|simulate` | — | — | no |
| ⚠️ | private_coverage | `analyze private endpoint coverage for zero-trust` | plan_any_prefix | `analyze_private|private_connect|private_endpoint` | — | — | no |
| ⚠️ | dns_path | `trace DNS resolution path from vnet-prod for api.example.com` | plan_any_prefix | `analyze_dns|dns_resolution_path|dns` | — | — | no |
| ⚠️ | security_posture | `assess my network security posture` | plan_contains | `assess_network_security_posture` | — | — | no |
| ⚠️ | posture_not_nsg_list | `assess my network security posture` | plan_not_contains | `nsg_list` | — | — | no |
| ⚠️ | posture_not_fast_path | `assess my network security posture` | fast_path_false | `` | — | — | no |
| ⚠️ | list_vnets_and_subnets | `list my virtual networks and subnets` | plan_contains | `virtual_network_list` | — | — | no |
| ⚠️ | vnets_subnets_not_describe | `list my virtual networks and subnets` | plan_not_contains | `describe_capabilities` | — | — | no |
| ⚠️ | show_vnets_subnets | `show my VNets and their subnets` | plan_contains | `virtual_network_list` | — | — | no |
| ⚠️ | inspect_vnet_peering | `show VNet peering status` | plan_contains | `inspect_vnet` | — | — | no |
| ⚠️ | inspect_vnet_address_space | `show VNet address space and subnets` | plan_contains | `inspect_vnet` | — | — | no |
| ⚠️ | inspect_vnet_not_list | `show VNet peering status` | plan_not_contains | `virtual_network_list` | — | — | no |
| ⚠️ | simulate_not_nsg_list | `will traffic from my VM be allowed on port 443` | plan_not_contains | `nsg_list` | — | — | no |
| ⚠️ | dns_path_not_check_dns | `trace DNS resolution path from vnet-prod for api.example.com` | plan_not_contains | `check_dns_resolution` | — | — | no |
| ⚠️ | private_cov_not_list_ep | `which PaaS services are not using private endpoints` | plan_not_contains | `private_endpoint_list` | — | — | no |
| ⚠️ | connectivity_matrix_no_fp | `generate connectivity matrix for my subnets` | fast_path_false | `` | — | — | no |
| ⚠️ | simulate_nsg_no_fp | `simulate NSG flow from my VM to port 443` | fast_path_false | `` | — | — | no |
| ⚠️ | route_path_no_fp | `analyze route path from my subnet to www.microsoft.com` | fast_path_false | `` | — | — | no |
| ⚠️ | private_cov_no_fp | `analyze private endpoint coverage for zero-trust` | fast_path_false | `` | — | — | no |
| ⚠️ | dns_path_no_fp | `trace DNS resolution path from vnet-prod for api.example.com` | fast_path_false | `` | — | — | no |
| ⚠️ | network_inventory_unused | `find unused network resources` | plan_contains | `inventory_network_resources` | — | — | no |
| ⚠️ | network_inventory_cost | `network resource inventory for cost optimization` | plan_contains | `inventory_network_resources` | — | — | no |
| ⚠️ | hub_spoke_alt | `check hub-spoke architecture health` | plan_any_prefix | `validate_hub_spoke|hub_spoke` | — | — | no |
| ⚠️ | expressroute_circuit | `check ExpressRoute circuit health` | plan_contains | `inspect_vpn_expressroute` | — | — | no |
| ⚠️ | appgw_alt | `inspect my Application Gateway WAF` | plan_contains | `inspect_appgw_waf` | — | — | no |
| ⚠️ | security_posture_cis | `run CIS Azure network compliance check` | plan_contains | `assess_network_security_posture` | — | — | no |
| ⚠️ | security_posture_nist | `check network compliance against NIST` | plan_contains | `assess_network_security_posture` | — | — | no |
| ⚠️ | list_vms | `list my virtual machines` | plan_contains | `virtual_machine_list` | — | — | no |
| ⚠️ | show_vms | `show all VMs in my subscription` | plan_contains | `virtual_machine_list` | — | — | no |
| ⚠️ | os_inventory | `what OS are my VMs running` | plan_any_prefix | `os|inventory|eol|law` | — | — | no |
| ⚠️ | eol_lookup | `show end of life software on my servers` | plan_any_prefix | `eol|end_of_life|os_eol|law_get_software` | — | — | no |
| ⚠️ | eol_domain | `which of my VMs have end-of-life operating systems` | domain_contains | `arc_inventory` | — | — | no |
| ⚠️ | container_health_domain | `check health of my container apps` | domain_contains | `sre_health|sre_incident|observability` | — | — | no |
| ⚠️ | container_error_domain | `why is my container app returning 503 errors` | domain_contains | `sre_health|sre_incident|observability` | — | — | no |
| ⚠️ | fast_path_simple | `list my subscriptions` | fast_path_true | `` | — | — | no |
| ⚠️ | not_fast_path_complex | `list my VMs then restart any that are stopped and show me the results` | fast_path_false | `` | — | — | no |
| ⚠️ | cli_in_retrieved_vnets | `list my virtual networks` | plan_any_prefix | `virtual_network_list|azure_cli` | — | — | no |
| ⚠️ | action_tools_filtered_vnets | `list my virtual networks` | plan_no_prefix | `test_|check_|create_|delete_|restart_` | — | — | no |
| ⚠️ | action_tools_filtered_subs | `list my subscriptions` | plan_no_prefix | `test_|check_|create_|delete_|restart_` | — | — | no |
