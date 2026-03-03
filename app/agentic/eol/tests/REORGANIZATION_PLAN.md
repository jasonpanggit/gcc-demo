# Tests Folder Reorganization Plan

## Current Issues
1. Too many files in root directory (56 test files)
2. No clear organization by category
3. Multiple duplicate/temporary debug files in ui/
4. Too many summary/report MD files (10+ in ui/)
5. Unclear which tests are still relevant

## Proposed Structure

```
tests/
├── README.md                          # Main testing guide
├── conftest.py                        # Root fixtures
├── pytest.ini                         # Pytest configuration
│
├── agents/                            # Agent-specific tests
│   ├── __init__.py
│   ├── test_monitor_agent.py
│   ├── test_patch_sub_agent.py
│   ├── test_sre_sub_agent.py
│   ├── test_microsoft_agent.py
│   ├── test_ubuntu_agent.py
│   └── test_redhat_agent.py
│
├── orchestrators/                     # Orchestrator tests
│   ├── __init__.py
│   ├── test_base_orchestrator.py
│   ├── test_eol_orchestrator.py
│   ├── test_inventory_orchestrator.py
│   ├── test_sre_orchestrator.py
│   ├── test_orchestrator_tool_access.py
│   ├── test_orchestrator_error_handling.py
│   └── test_orchestrator_integration.py
│
├── mcp_servers/                       # MCP server tests
│   ├── __init__.py
│   ├── test_mcp_azure_cli_server.py
│   ├── test_mcp_compute_server.py
│   ├── test_mcp_inventory_server.py
│   ├── test_mcp_monitor_server.py
│   ├── test_mcp_network_server.py
│   ├── test_mcp_os_eol_server.py
│   ├── test_mcp_patch_server.py
│   ├── test_mcp_sre_server.py
│   └── test_mcp_storage_server.py
│
├── tools/                             # Tool registry and routing tests
│   ├── __init__.py
│   ├── test_tool_registry.py
│   ├── test_tool_embedder.py
│   ├── test_tool_retriever.py
│   ├── test_tool_manifest_index.py
│   ├── test_tool_result_cache.py
│   ├── test_unified_domain_registry.py
│   └── test_sre_tool_registry.py
│
├── cache/                             # Cache-related tests
│   ├── __init__.py
│   ├── test_cosmos_cache.py
│   ├── test_eol_cache.py
│   └── test_resource_inventory_cache.py
│
├── network/                           # Network and connectivity tests
│   ├── __init__.py
│   ├── test_connectivity_matrix.py
│   ├── test_nsg_rule_evaluator.py
│   └── test_route_path_analyzer.py
│
├── reliability/                       # Error handling, resilience tests
│   ├── __init__.py
│   ├── test_circuit_breaker.py
│   ├── test_error_boundary.py
│   ├── test_error_aggregation.py
│   ├── test_error_scenarios_e2e.py
│   └── test_correlation_id.py
│
├── services/                          # Service layer tests
│   ├── __init__.py
│   └── test_resource_inventory_service.py
│
├── routing/                           # Routing and pipeline tests
│   ├── __init__.py
│   ├── test_router.py
│   ├── test_pipeline_routing.py
│   ├── test_phase6_pipeline.py
│   └── test_phase7_default.py
│
├── remote/                            # Remote execution tests
│   ├── __init__.py
│   ├── test_remote_sre.py
│   ├── test_remote_tool_selection.py
│   └── test_cli_executor_safety.py
│
├── integration/                       # Integration tests (keep as is)
│   ├── __init__.py
│   ├── test_network_audit_orchestration.py
│   └── test_integration_workflows.py
│
├── unit/                              # Unit tests (keep as is)
│   ├── __init__.py
│   └── test_network_security_posture.py
│
├── ui/                                # UI tests (clean up)
│   ├── README.md                      # UI testing guide
│   ├── conftest.py                    # UI fixtures
│   ├── ui-issues.md                   # Issue tracking
│   ├── FINAL-TEST-RESULTS.md          # Keep: Final results
│   ├── UI-TESTING-SUMMARY.md          # Keep: Executive summary
│   ├── THEME-TEST-FIX-REPORT.md       # Keep: Theme fix details
│   │
│   ├── pages/                         # Page-specific tests
│   │   ├── test_dashboard.py
│   │   ├── test_analytics.py
│   │   ├── test_azure_mcp.py
│   │   ├── test_sre_assistant.py
│   │   ├── test_inventory_ai.py
│   │   ├── test_eol_search_ai.py
│   │   ├── test_eol_inventory.py
│   │   ├── test_azure_resources.py
│   │   ├── test_os_software_law.py
│   │   ├── test_patch_management.py
│   │   ├── test_alerts.py
│   │   ├── test_cache.py
│   │   ├── test_agents.py
│   │   ├── test_eol_search_history.py
│   │   ├── test_os_eol_tracker.py
│   │   └── test_system_health.py
│   │
│   ├── features/                      # Cross-page features
│   │   ├── test_navigation.py
│   │   └── test_theme_visibility.py
│   │
│   └── utils/                         # UI test utilities
│       └── debug_helpers.py           # Consolidated debug tools
│
└── config/                            # Test configuration tests
    ├── __init__.py
    ├── test_config.py
    ├── test_conftest_factories.py
    ├── test_structured_logging.py
    ├── test_sre_gateway.py
    └── test_sre_incident_memory.py
```

## Files to Delete

### UI Folder Cleanup - DELETE
1. `ui/COMPLETE-TEST-SUMMARY.md` - Superseded by FINAL-TEST-RESULTS.md
2. `ui/COMPLETION-SUMMARY.md` - Duplicate
3. `ui/COMPREHENSIVE-TEST-SUMMARY.md` - Duplicate
4. `ui/FINAL-REPORT.md` - Duplicate
5. `ui/FINAL-TEST-REPORT.md` - Duplicate
6. `ui/STATUS.md` - Temporary
7. `ui/SUMMARY.md` - Duplicate
8. `ui/TEST-RESULTS.md` - Superseded
9. `ui/TEST-VERIFICATION-RESULTS.md` - Superseded
10. `ui/THEME-TEST-RESULTS.md` - Consolidated into THEME-TEST-FIX-REPORT.md
11. `ui/THEME-VISIBILITY-TESTS.md` - Implementation details, not needed
12. `ui/QUICK-REFERENCE.md` - Redundant with UI-TESTING-SUMMARY.md
13. `ui/debug_toggle.py` - Temporary debug script
14. `ui/find_toggle.py` - Temporary debug script

### UI Folder - KEEP (4 files)
1. `ui/README.md` - Entry point for UI testing
2. `ui/ui-issues.md` - Issue tracking (ESSENTIAL)
3. `ui/FINAL-TEST-RESULTS.md` - Complete results (ESSENTIAL)
4. `ui/UI-TESTING-SUMMARY.md` - Executive summary (ESSENTIAL)
5. `ui/THEME-TEST-FIX-REPORT.md` - Important fix documentation

## Migration Commands

```bash
# Create new directory structure
mkdir -p agents orchestrators mcp_servers tools cache network
mkdir -p reliability services routing remote config ui/pages ui/features ui/utils

# Move agent tests
mv test_*_agent.py agents/

# Move orchestrator tests
mv test_*_orchestrator*.py orchestrators/
mv test_base_orchestrator.py orchestrators/

# Move MCP server tests
mv test_mcp_*.py mcp_servers/

# Move tool-related tests
mv test_tool_*.py test_unified_domain_registry.py test_sre_tool_registry.py tools/

# Move cache tests
mv test_*_cache.py cache/

# Move network tests
mv test_connectivity_matrix.py test_nsg_rule_evaluator.py test_route_path_analyzer.py network/

# Move reliability tests
mv test_circuit_breaker.py test_error_*.py test_correlation_id.py reliability/

# Move service tests
mv test_resource_inventory_service.py services/

# Move routing tests
mv test_router.py test_*_pipeline.py test_pipeline_routing.py routing/

# Move remote tests
mv test_remote_*.py test_cli_executor_safety.py remote/

# Move config tests
mv test_config.py test_conftest_factories.py test_structured_logging.py config/
mv test_sre_gateway.py test_sre_incident_memory.py config/

# Move UI page tests
mv ui/test_dashboard.py ui/test_analytics.py ui/test_azure_mcp.py ui/pages/
mv ui/test_sre_assistant.py ui/test_inventory_ai.py ui/test_eol_search_ai.py ui/pages/
mv ui/test_eol_inventory.py ui/test_azure_resources.py ui/test_os_software_law.py ui/pages/
mv ui/test_patch_management.py ui/test_alerts.py ui/test_cache.py ui/pages/
mv ui/test_agents.py ui/test_eol_search_history.py ui/test_os_eol_tracker.py ui/pages/
mv ui/test_system_health.py ui/pages/

# Move UI feature tests
mv ui/test_navigation.py ui/test_theme_visibility.py ui/features/

# Delete duplicate/temporary files
rm ui/COMPLETE-TEST-SUMMARY.md ui/COMPLETION-SUMMARY.md ui/COMPREHENSIVE-TEST-SUMMARY.md
rm ui/FINAL-REPORT.md ui/FINAL-TEST-REPORT.md ui/STATUS.md ui/SUMMARY.md
rm ui/TEST-RESULTS.md ui/TEST-VERIFICATION-RESULTS.md
rm ui/THEME-TEST-RESULTS.md ui/THEME-VISIBILITY-TESTS.md ui/QUICK-REFERENCE.md
rm ui/debug_toggle.py ui/find_toggle.py

# Create __init__.py files
touch agents/__init__.py orchestrators/__init__.py mcp_servers/__init__.py
touch tools/__init__.py cache/__init__.py network/__init__.py
touch reliability/__init__.py services/__init__.py routing/__init__.py
touch remote/__init__.py config/__init__.py
```

## Benefits

1. **Clear Organization**: Easy to find tests by category
2. **Reduced Clutter**: Root directory has only key files
3. **Better Maintenance**: Grouped related tests together
4. **Cleaner UI Folder**: Only essential docs remain
5. **Easier Navigation**: Logical folder names
6. **Better Test Discovery**: pytest can easily find all tests

## After Reorganization

Root directory will have:
- `conftest.py`
- `pytest.ini`
- `README.md`
- 13 category folders
- Clean and organized!

UI folder will have:
- 5 essential MD files (down from 18!)
- 2 folders: pages/ and features/
- No debug scripts
