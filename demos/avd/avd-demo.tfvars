# ============================================================================
# AVD DEMO CONFIGURATION
# ============================================================================
# This configuration file demonstrates Azure Virtual Desktop deployment
# in the Non-Gen VNet with enterprise features including:
# - AAD-joined session hosts
# - FSLogix profile containers with private endpoints
# - Outbound traffic routing through Non-Gen firewall
# - Comprehensive monitoring integration
# ============================================================================

# ==============================================================================
# GENERAL CONFIGURATION
# ==============================================================================
location     = "Australia East"
environment  = "demo"
project_name = "avd-demo"

# ==============================================================================
# CORE INFRASTRUCTURE - Required for AVD
# ==============================================================================
# Hub VNet - Foundation network
deploy_hub_vnet = true

# Non-Gen VNet - Where AVD will be deployed
deploy_nongen_vnet = true

# VNet Peering - Connect Hub and Non-Gen
deploy_hub_nongen_peering = true

# ==============================================================================
# FIREWALL CONFIGURATION - Required for secure AVD outbound traffic
# ==============================================================================
# Non-Gen Firewall for AVD traffic filtering
deploy_nongen_firewall = true

# ==============================================================================
# MONITORING - Required for AVD insights and diagnostics
# ==============================================================================
deploy_azure_monitor_private_link_scope = true
log_analytics_workspace_sku             = "PerGB2018"
log_analytics_workspace_retention_days  = 30

# ==============================================================================
# AZURE VIRTUAL DESKTOP CONFIGURATION
# ==============================================================================
# Enable AVD deployment in Non-Gen VNet
deploy_nongen_avd = true

# ==============================================================================
# AVD HOST POOL CONFIGURATION
# ==============================================================================
avd_host_pool_type                = "Pooled"       # Pooled for shared access, Personal for dedicated
avd_host_pool_load_balancer_type  = "BreadthFirst" # BreadthFirst, DepthFirst, or Persistent
avd_host_pool_maximum_sessions    = 10             # Max concurrent sessions per host
avd_host_pool_start_vm_on_connect = true           # Auto-start VMs when users connect (cost optimization)

# ==============================================================================
# AVD SESSION HOST CONFIGURATION
# ==============================================================================
avd_session_host_count          = 2                 # Number of session hosts (start small for demo)
avd_session_host_vm_size        = "Standard_D2s_v3" # VM size (2 vCPUs, 8GB RAM) - good for demo
avd_session_host_admin_username = "avdadmin"        # Local admin username
avd_session_host_admin_password = "P@55w0rd1234"    # Local admin password (change in production!)

# Windows 11 Multi-Session with Office (recommended for AVD)
avd_session_host_image_publisher = "MicrosoftWindowsDesktop"
avd_session_host_image_offer     = "Windows-11"
avd_session_host_image_sku       = "win11-22h2-avd" # Windows 11 Enterprise multi-session

# ==============================================================================
# AVD ENTERPRISE FEATURES
# ==============================================================================
# Azure AD Join - Modern authentication and management
avd_aad_join_enabled = true # Enable Azure AD join for session hosts

# FSLogix Profile Containers - Persistent user profiles
avd_fslogix_enabled                     = true       # Enable FSLogix profile containers
avd_fslogix_storage_account_tier        = "Standard" # Premium for better performance (Standard for cost savings)
avd_fslogix_storage_account_replication = "LRS"      # LRS sufficient for demo (consider ZRS for production)
avd_fslogix_file_share_quota_gb         = 1024       # 1TB quota for user profiles

# Private Endpoints - Secure connectivity to storage
avd_private_endpoints_enabled = true # Enable private endpoints for FSLogix storage

# ==============================================================================
# OPTIONAL SERVICES (Disabled for focused AVD demo)
# ==============================================================================
deploy_bastion = false

# ==============================================================================
# DEPLOYMENT SCENARIOS
# ==============================================================================

# SCENARIO 1: Minimal AVD Demo (Current Configuration)
# - Hub VNet + Non-Gen VNet with peering
# - Non-Gen Firewall for secure outbound access
# - 2 session hosts with AAD join and FSLogix
# - Private endpoints for secure storage access
# - Log Analytics for monitoring

# SCENARIO 2: Production-Ready AVD (Uncomment below)
# avd_session_host_count = 5
# avd_session_host_vm_size = "Standard_D4s_v3"
# avd_fslogix_storage_account_replication = "ZRS"
# deploy_hub_firewall = true
# deploy_bastion = true

# SCENARIO 3: Cost-Optimized AVD (Alternative configuration)
# avd_session_host_count = 1
# avd_session_host_vm_size = "Standard_B2s"
# avd_fslogix_storage_account_tier = "Standard"
# avd_host_pool_start_vm_on_connect = true
# avd_private_endpoints_enabled = false

# ==============================================================================
# DEPLOYMENT NOTES
# ==============================================================================
# 1. Ensure you have sufficient Azure quota for the session host VMs
# 2. Update the admin password before deploying to production
# 3. Configure user assignments to the AVD application group after deployment
# 4. Consider Azure AD conditional access policies for additional security
# 5. Monitor costs and adjust VM sizes and count based on actual usage
# 6. Review firewall rules to ensure proper AVD service connectivity
# ==============================================================================
