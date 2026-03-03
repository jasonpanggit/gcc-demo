#!/bin/bash
set -e

echo "Starting tests folder reorganization..."

# Create new directory structure
echo "Creating new directories..."
mkdir -p agents orchestrators mcp_servers tools cache network
mkdir -p reliability services routing remote config ui/pages ui/features

# Move agent tests
echo "Moving agent tests..."
mv test_monitor_agent.py test_patch_sub_agent.py test_sre_sub_agent.py agents/ 2>/dev/null || true
mv test_microsoft_agent.py test_ubuntu_agent.py test_redhat_agent.py agents/ 2>/dev/null || true

# Move orchestrator tests
echo "Moving orchestrator tests..."
mv test_base_orchestrator.py test_eol_orchestrator.py test_inventory_orchestrator.py orchestrators/ 2>/dev/null || true
mv test_sre_orchestrator.py test_orchestrator_tool_access.py orchestrators/ 2>/dev/null || true
mv test_orchestrator_error_handling.py test_orchestrator_integration.py orchestrators/ 2>/dev/null || true

# Move MCP server tests
echo "Moving MCP server tests..."
mv test_mcp_*.py mcp_servers/ 2>/dev/null || true

# Move tool-related tests
echo "Moving tool tests..."
mv test_tool_*.py tools/ 2>/dev/null || true
mv test_unified_domain_registry.py test_sre_tool_registry.py tools/ 2>/dev/null || true

# Move cache tests
echo "Moving cache tests..."
mv test_cosmos_cache.py test_eol_cache.py test_resource_inventory_cache.py cache/ 2>/dev/null || true

# Move network tests
echo "Moving network tests..."
mv test_connectivity_matrix.py test_nsg_rule_evaluator.py test_route_path_analyzer.py network/ 2>/dev/null || true

# Move reliability tests
echo "Moving reliability tests..."
mv test_circuit_breaker.py test_error_boundary.py test_error_aggregation.py reliability/ 2>/dev/null || true
mv test_error_scenarios_e2e.py test_correlation_id.py reliability/ 2>/dev/null || true

# Move service tests
echo "Moving service tests..."
mv test_resource_inventory_service.py services/ 2>/dev/null || true

# Move routing tests
echo "Moving routing tests..."
mv test_router.py test_pipeline_routing.py routing/ 2>/dev/null || true
mv test_phase6_pipeline.py test_phase7_default.py routing/ 2>/dev/null || true

# Move remote tests
echo "Moving remote tests..."
mv test_remote_sre.py test_remote_tool_selection.py test_cli_executor_safety.py remote/ 2>/dev/null || true

# Move config tests
echo "Moving config tests..."
mv test_config.py test_conftest_factories.py test_structured_logging.py config/ 2>/dev/null || true
mv test_sre_gateway.py test_sre_incident_memory.py config/ 2>/dev/null || true

# Move UI page tests
echo "Moving UI page tests..."
cd ui
mv test_dashboard.py test_analytics.py test_azure_mcp.py pages/ 2>/dev/null || true
mv test_sre_assistant.py test_inventory_ai.py test_eol_search_ai.py pages/ 2>/dev/null || true
mv test_eol_inventory.py test_azure_resources.py test_os_software_law.py pages/ 2>/dev/null || true
mv test_patch_management.py test_alerts.py test_cache.py pages/ 2>/dev/null || true
mv test_agents.py test_eol_search_history.py test_os_eol_tracker.py pages/ 2>/dev/null || true
mv test_system_health.py pages/ 2>/dev/null || true

# Move UI feature tests
echo "Moving UI feature tests..."
mv test_navigation.py test_theme_visibility.py features/ 2>/dev/null || true

# Delete duplicate/temporary files
echo "Deleting duplicate/temporary files..."
rm -f COMPLETE-TEST-SUMMARY.md COMPLETION-SUMMARY.md COMPREHENSIVE-TEST-SUMMARY.md
rm -f FINAL-REPORT.md FINAL-TEST-REPORT.md STATUS.md SUMMARY.md
rm -f TEST-RESULTS.md TEST-VERIFICATION-RESULTS.md
rm -f THEME-TEST-RESULTS.md THEME-VISIBILITY-TESTS.md QUICK-REFERENCE.md
rm -f debug_toggle.py find_toggle.py

cd ..

# Create __init__.py files
echo "Creating __init__.py files..."
touch agents/__init__.py orchestrators/__init__.py mcp_servers/__init__.py
touch tools/__init__.py cache/__init__.py network/__init__.py
touch reliability/__init__.py services/__init__.py routing/__init__.py
touch remote/__init__.py config/__init__.py

echo "Reorganization complete!"
echo ""
echo "Summary:"
echo "- Created 13 category folders"
echo "- Moved tests into appropriate folders"
echo "- Cleaned up UI folder (removed 12 duplicate files)"
echo "- Created __init__.py files for all new folders"
