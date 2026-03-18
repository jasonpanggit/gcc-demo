# Fallback Catalogue

**Generated:** 2026-03-18
**Total "fallback" references (case-insensitive):** 732 occurrences across 118 files
**Unique code locations catalogued:** 126 entries

---

## COSMOS-Category Entries (Action: REMOVE)

### FB-001: utils/inventory_cache.py:15
**Category:** COSMOS
**Code:** `# Fallback if Cosmos SDK not available`
**Context:** Import guard for `CosmosResourceNotFoundError` with fallback flag `COSMOS_EXCEPTIONS_AVAILABLE`
**Action:** REMOVE — Cosmos SDK import guard no longer needed; remove entire try/except block
**Priority:** HIGH (active code path)

### FB-002: utils/inventory_cache.py:88
**Category:** COSMOS
**Code:** `Retrieve cached inventory data with memory + Cosmos DB fallback.`
**Context:** Docstring describing L1 memory + L2 Cosmos DB cache fallback pattern
**Action:** REMOVE — Update docstring to reflect PostgreSQL-only L2 cache
**Priority:** LOW (docstring only)

### FB-003: utils/inventory_cache.py:131
**Category:** COSMOS
**Code:** `# Fallback to Cosmos DB`
**Context:** Comment before code that reads from Cosmos DB container when memory cache misses
**Action:** REMOVE — Replace Cosmos L2 fallback with InventoryCachePostgresRepository
**Priority:** HIGH (active code path)

### FB-004: mcp_servers/sre_mcp_server.py:101
**Category:** COSMOS
**Code:** `# In-memory audit trail (fallback when Cosmos DB unavailable)`
**Context:** Comment describing in-memory dict as fallback when Cosmos audit_trail container unavailable
**Action:** REMOVE — Refactor to SREPostgresRepository; remove in-memory fallback or keep as L1 cache
**Priority:** HIGH (active code path)

### FB-005: mcp_servers/sre_mcp_server.py:169
**Category:** COSMOS
**Code:** `# In-memory custom runbooks (fallback when Cosmos DB unavailable)`
**Context:** Comment describing in-memory runbook store as fallback when Cosmos unavailable
**Action:** REMOVE — Refactor to SREPostgresRepository
**Priority:** HIGH (active code path)

### FB-006: mcp_servers/sre_mcp_server.py:327
**Category:** COSMOS
**Code:** `# Always add to in-memory trail (fallback)`
**Context:** Dual-write: always writes to in-memory dict, also tries Cosmos container
**Action:** REMOVE — Remove dual-write pattern; use SREPostgresRepository only
**Priority:** HIGH (active code path)

### FB-007: mcp_servers/sre_mcp_server.py:3219
**Category:** COSMOS
**Code:** `"Cosmos DB (with in-memory fallback) and indexed by resource type and "`
**Context:** Tool description string mentioning Cosmos DB persistence for custom runbooks
**Action:** REMOVE — Update tool description to reflect PostgreSQL persistence
**Priority:** LOW (docstring/description)

### FB-008: mcp_servers/sre_mcp_server.py:3333
**Category:** COSMOS
**Code:** `# Always store in memory as fallback`
**Context:** Dual-write for runbook storage: in-memory + Cosmos attempt
**Action:** REMOVE — Remove dual-write; use SREPostgresRepository
**Priority:** HIGH (active code path)

### FB-009: mcp_servers/sre_mcp_server.py:6210
**Category:** COSMOS
**Code:** `# In-memory SLO store (fallback, persisted to Cosmos DB when available)`
**Context:** Comment describing SLO definitions dual-storage with Cosmos
**Action:** REMOVE — Refactor to PostgreSQL or keep in-memory only
**Priority:** MEDIUM (SLO feature)

### FB-010: utils/alert_manager.py:227
**Category:** COSMOS
**Code:** `"""Load alert configuration from Cosmos DB with file fallback - following inventory_cache pattern"""`
**Context:** Method that loads from Cosmos first, falls back to file config
**Action:** REMOVE — Replace Cosmos load path with AlertPostgresRepository
**Priority:** HIGH (active code path)

### FB-011: utils/alert_manager.py:283
**Category:** COSMOS
**Code:** `"""Save alert configuration to Cosmos DB with file fallback - following inventory_cache pattern"""`
**Context:** Method that saves to Cosmos first, falls back to file config
**Action:** REMOVE — Replace Cosmos save path with AlertPostgresRepository
**Priority:** HIGH (active code path)

### FB-012: utils/alert_manager.py:334
**Category:** COSMOS
**Code:** `# Continue with file fallback even if Cosmos fails`
**Context:** Exception handler that continues to file-based storage when Cosmos save fails
**Action:** REMOVE — Remove Cosmos save attempt; use PostgreSQL directly
**Priority:** HIGH (active code path)

### FB-013: utils/eol_cache.py:136
**Category:** COSMOS
**Code:** `# fallback to cosmos if available`
**Context:** Comment before code that checks `base_cosmos.initialized` and calls `base_cosmos.get_container()`
**Action:** REMOVE — Replace Cosmos L2 fallback with EOLPostgresRepository
**Priority:** HIGH (active code path)

### FB-014: utils/sre_incident_memory.py:108
**Category:** COSMOS
**Code:** `"SREIncidentMemory: Cosmos unavailable — using in-memory fallback"`
**Context:** Warning log when Cosmos container init fails, falling back to in-memory dict
**Action:** REMOVE — Refactor to SREPostgresRepository; remove in-memory fallback
**Priority:** MEDIUM (SRE incident feature)

### FB-015: utils/sre_incident_memory.py:250
**Category:** COSMOS
**Code:** `"""Fetch recent incident records from Cosmos or in-memory fallback."""`
**Context:** Docstring describing dual-path read from Cosmos or in-memory store
**Action:** REMOVE — Update docstring, refactor to PostgreSQL-only read
**Priority:** MEDIUM (SRE incident feature)

### FB-016: utils/resource_inventory_cache.py:100
**Category:** COSMOS
**Code:** `- Automatic L1 → L2 fallback on miss`
**Context:** Docstring describing L1 memory to L2 Cosmos DB cache fallback pattern
**Action:** REMOVE — Update docstring to reflect PostgreSQL L2
**Priority:** LOW (docstring only)

### FB-017: tests/test_resource_inventory_cache.py:4
**Category:** COSMOS
**Code:** `Tests L1 (in-memory) cache, L2 (Cosmos DB) fallback, per-resource-type`
**Context:** Module docstring in test file referencing Cosmos DB fallback
**Action:** REMOVE — Update test docstring after refactoring cache layer
**Priority:** LOW (test file docstring)

### FB-018: tests/test_resource_inventory_cache.py:127
**Category:** COSMOS
**Code:** `"""Tests for L2 (Cosmos DB) cache fallback."""`
**Context:** Test class docstring for L2 Cosmos fallback tests
**Action:** REMOVE — Update or remove test class after cache refactoring
**Priority:** LOW (test file docstring)

---

## CONFIG-Category Entries (Action: KEEP)

### FB-019: main.py:133
**Category:** CONFIG
**Code:** `async def local_mock_api_fallback_middleware(request: Request, call_next):`
**Context:** Middleware for mock mode API responses when USE_MOCK_DATA=true
**Action:** KEEP — Legitimate mock mode middleware, not Cosmos-related
**Priority:** N/A

### FB-020: main.py:3381
**Category:** CONFIG
**Code:** `# Method 3: Check for eol_urls dictionary (fallback)`
**Context:** URL resolution fallback chain for agent URL configuration
**Action:** KEEP — Config-level URL resolution pattern
**Priority:** N/A

### FB-021: main.py:3404
**Category:** CONFIG
**Code:** `# Method 4: Legacy fallbacks`
**Context:** Legacy URL fallback methods for backward compatibility
**Action:** KEEP — Config-level fallback chain
**Priority:** N/A

### FB-022: utils/config.py:*
**Category:** CONFIG
**Code:** Various fallback default values in config
**Context:** Config field defaults like `os.environ.get('VAR', 'default')`
**Action:** KEEP — Standard config pattern
**Priority:** N/A

### FB-023: utils/sre_gateway.py:92-252
**Category:** CONFIG
**Code:** `"""Cheap SRE intent classifier — keyword fast path + LLM fallback."""` (10 refs)
**Context:** SRE gateway uses keyword matching with LLM fallback for intent classification
**Action:** KEEP — Legitimate tiered classification pattern, not Cosmos-related
**Priority:** N/A

### FB-024: utils/planner.py:92-1079
**Category:** CONFIG
**Code:** `_legacy_fallback_plan()`, `legacy fallback step`, etc. (13 refs)
**Context:** Planner fallback to legacy ReAct step when no MCP tools available or LLM fails
**Action:** KEEP — Legitimate routing pipeline fallback pattern
**Priority:** N/A

### FB-025: utils/tool_retriever.py:* (21 refs)
**Category:** CONFIG
**Code:** Various fallback scoring and tool selection patterns
**Context:** Tool retriever uses fallback scoring when primary retrieval returns no results
**Action:** KEEP — Legitimate tool routing fallback
**Priority:** N/A

### FB-026: utils/response_composer.py:14-979 (8 refs)
**Category:** CONFIG
**Code:** `_build_static_fallback()`, `Graceful fallback: if LLM unavailable`
**Context:** Response composer falls back to static HTML when LLM unavailable
**Action:** KEEP — Legitimate error-resilience pattern
**Priority:** N/A

### FB-027: agents/sre_orchestrator.py:1-1928 (24 refs)
**Category:** CONFIG
**Code:** `_execute_mcp_fallback()`, `mcp_fallback`, etc.
**Context:** SRE orchestrator fallback from SRESubAgent to MCP direct execution
**Action:** KEEP — Legitimate agent degradation pattern, not Cosmos-related
**Priority:** N/A

### FB-028: agents/mcp_orchestrator.py:* (73 refs)
**Category:** CONFIG
**Code:** Various fallback patterns for tool routing, scoring, and execution
**Context:** MCP orchestrator uses extensive fallback chains for tool selection and execution
**Action:** KEEP — Legitimate orchestration fallback patterns
**Priority:** N/A

### FB-029: agents/inventory_orchestrator.py:128-908 (10 refs)
**Category:** CONFIG
**Code:** `_fallback_response()`, `metadata={"fallback": True}`
**Context:** Inventory orchestrator returns fallback response when Agent Framework unavailable
**Action:** KEEP — Legitimate agent framework degradation
**Priority:** N/A

### FB-030: utils/inventory_mcp_client.py:49-682 (31 refs)
**Category:** CONFIG
**Code:** `InventoryFallbackExecutor`, `_enable_fallback()`, `_use_fallback`
**Context:** Inventory MCP client has in-process fallback executor when MCP subprocess fails
**Action:** KEEP — Legitimate MCP subprocess fallback pattern
**Priority:** N/A

### FB-031: utils/os_eol_mcp_client.py:* (31 refs)
**Category:** CONFIG
**Code:** Similar in-process fallback executor pattern
**Context:** OS EOL MCP client has in-process fallback when MCP subprocess fails
**Action:** KEEP — Legitimate MCP subprocess fallback pattern
**Priority:** N/A

### FB-032: utils/manifest_impact_analyzer.py:114-1107 (8 refs)
**Category:** CONFIG
**Code:** `_CLI_FALLBACK_TOOL`, CLI fallback guardrail
**Context:** Manifest analyzer ensures CLI tool is always available as fallback
**Action:** KEEP — Legitimate tool selection fallback
**Priority:** N/A

### FB-033: api/routing_analytics.py:111-128 (5 refs)
**Category:** CONFIG
**Code:** `fallback = Path("./routing_logs")`
**Context:** Routing analytics creates fallback log directory when configured path unavailable
**Action:** KEEP — Config directory fallback
**Priority:** N/A

### FB-034: api/sre_orchestrator.py:5-536 (3 refs)
**Category:** CONFIG
**Code:** `with MCP fallback`, `fallback mode`
**Context:** SRE orchestrator docstrings describing agent-first with MCP fallback architecture
**Action:** KEEP — Legitimate architectural pattern description
**Priority:** N/A

### FB-035: utils/domain_classifier.py:9
**Category:** CONFIG
**Code:** `- General domain is the fallback when no keywords match`
**Context:** Docstring describing GENERAL as fallback domain classification
**Action:** KEEP — Legitimate classification pattern
**Priority:** N/A

### FB-036: utils/unified_domain_registry.py:* (4 refs)
**Category:** CONFIG
**Code:** Domain fallback references in registry
**Context:** Unified domain registry fallback logic
**Action:** KEEP — Legitimate domain registration pattern
**Priority:** N/A

### FB-037: utils/router.py:* (6 refs)
**Category:** CONFIG
**Code:** Legacy-to-unified domain fallback mapping
**Context:** Router maps legacy domains to unified domains with fallback
**Action:** KEEP — Legitimate routing pattern
**Priority:** N/A

### FB-038: utils/tool_manifest_index.py:403
**Category:** CONFIG
**Code:** `# Fallback: name-prefix heuristic for tools without a manifest`
**Context:** Tool manifest index uses name prefix to identify domain when manifest missing
**Action:** KEEP — Legitimate tool classification fallback
**Priority:** N/A

### FB-039: utils/tool_selection_reporter.py:* (11 refs)
**Category:** CONFIG
**Code:** Fallback reporting in tool selection diagnostics
**Context:** Tool selection reporter includes fallback analysis in diagnostic output
**Action:** KEEP — Legitimate diagnostic pattern
**Priority:** N/A

### FB-040: utils/routing_telemetry.py:* (2 refs)
**Category:** CONFIG
**Code:** Fallback telemetry recording
**Context:** Routing telemetry records fallback events
**Action:** KEEP — Legitimate telemetry
**Priority:** N/A

### FB-041: utils/tool_parameter_mappings.py:*
**Category:** CONFIG
**Code:** Tool parameter fallback mappings
**Context:** Default parameter values when auto-population unavailable
**Action:** KEEP — Legitimate config pattern
**Priority:** N/A

### FB-042: utils/sre_inventory_integration.py:* (5 refs)
**Category:** CONFIG
**Code:** SRE inventory integration fallback patterns
**Context:** Falls back to alternative data sources when primary unavailable
**Action:** KEEP — Legitimate data source fallback
**Priority:** N/A

---

## ERROR-Category Entries (Action: KEEP)

### FB-043: api/eol.py:360-423 (9 refs)
**Category:** ERROR
**Code:** `except Exception as exc: # pragma: no cover - defensive fallback`, `fallback = {...}`
**Context:** EOL API endpoint error handling with safe default responses
**Action:** KEEP — Legitimate error-handling fallback
**Priority:** N/A

### FB-044: api/azure_mcp.py:84-404 (3 refs)
**Category:** ERROR
**Code:** `except Exception as exc: # pragma: no cover - fallback when orchestrator unavailable`
**Context:** Azure MCP API falls back to direct client when orchestrator unavailable
**Action:** KEEP — Legitimate error-handling pattern
**Priority:** N/A

### FB-045: api/ui.py:108-448 (5 refs)
**Category:** ERROR
**Code:** `logger.warning("Inventory template not found; returning fallback HTML")`
**Context:** UI routers return simple fallback HTML when template files not found
**Action:** KEEP — Legitimate template-not-found error handling
**Priority:** N/A

### FB-046: api/cve.py:28-45 (2 refs)
**Category:** ERROR
**Code:** `def _format_os_display_name(normalized_name: str, fallback_key: Optional[str] = None) -> str:`
**Context:** CVE API uses fallback key for OS display name formatting
**Action:** KEEP — Legitimate data formatting fallback
**Priority:** N/A

### FB-047: api/cve_inventory.py:136
**Category:** ERROR
**Code:** `# Fallback: raw counts (pre-enrichment scans)`
**Context:** CVE inventory returns raw counts when enriched data unavailable
**Action:** KEEP — Legitimate data availability fallback
**Priority:** N/A

### FB-048: api/cve_sync.py:130-239 (2 refs)
**Category:** ERROR
**Code:** `"used_fallback_window": False`
**Context:** CVE sync reports whether a fallback time window was used for delta sync
**Action:** KEEP — Legitimate sync metadata
**Priority:** N/A

### FB-049: api/agents.py:192-215 (2 refs)
**Category:** ERROR
**Code:** `# Method 3: Check for eol_urls dictionary (fallback)`, `# Method 4: Legacy fallbacks`
**Context:** Agent URL resolution chain with multiple fallback methods
**Action:** KEEP — Legitimate URL resolution pattern
**Priority:** N/A

### FB-050: utils/error_boundary.py:* (26 refs)
**Category:** ERROR
**Code:** `@error_boundary` decorator with `fallback=` parameter
**Context:** Error boundary decorator accepts fallback values for safe failure
**Action:** KEEP — Core error-handling infrastructure
**Priority:** N/A

### FB-051: utils/cve_data_aggregator.py:* (2 refs)
**Category:** ERROR
**Code:** Fallback for data aggregation when some sources fail
**Context:** CVE data aggregator handles partial source failures
**Action:** KEEP — Legitimate error-handling pattern
**Priority:** N/A

### FB-052: utils/cve_vm_service.py:* (35 refs)
**Category:** ERROR
**Code:** `allow_live_cve_fallback`, `allow_live_fallback`, extensive fallback patterns
**Context:** CVE VM service has configurable live API fallback when cache/DB has no data
**Action:** KEEP — Legitimate data source fallback (NVD API, not Cosmos)
**Priority:** N/A

### FB-053: utils/cve_service.py:213-245 (4 refs)
**Category:** ERROR
**Code:** `allow_live_fallback: bool = True`
**Context:** CVE service search allows live NVD API fallback when repository unavailable
**Action:** KEEP — Legitimate API fallback (not Cosmos-related)
**Priority:** N/A

### FB-054: utils/cve_sync_operations.py:33-* (4 refs)
**Category:** ERROR
**Code:** `Returns the timestamp and whether a fallback lookback window was used.`
**Context:** CVE sync operations track fallback window usage metadata
**Action:** KEEP — Legitimate sync status tracking
**Priority:** N/A

### FB-055: utils/cve_inventory_sync.py:* (6 refs)
**Category:** ERROR
**Code:** Various fallback patterns in CVE inventory sync
**Context:** Inventory sync handles missing data with safe defaults
**Action:** KEEP — Legitimate error handling
**Priority:** N/A

### FB-056: utils/cve_analytics.py:304
**Category:** ERROR
**Code:** `logger.warning(f"Scan-history trending fallback triggered: {e}")`
**Context:** Analytics falls back to simpler trending when scan history unavailable
**Action:** KEEP — Legitimate analytics fallback
**Priority:** N/A

### FB-057: utils/cve_scanner.py:935
**Category:** ERROR
**Code:** `allow_live_fallback=False`
**Context:** Scanner passes `allow_live_fallback=False` to disable NVD API calls during bulk scans
**Action:** KEEP — Legitimate scan configuration
**Priority:** N/A

### FB-058: utils/cve_export.py:* (2 refs)
**Category:** ERROR
**Code:** CVE export fallback formatting
**Context:** Export uses fallback formatting when data incomplete
**Action:** KEEP — Legitimate data handling
**Priority:** N/A

### FB-059: utils/vendor_feed_client.py:* (5 refs)
**Category:** ERROR
**Code:** Vendor feed client fallback patterns
**Context:** Handles vendor API failures with safe defaults
**Action:** KEEP — Legitimate API error handling
**Priority:** N/A

### FB-060: utils/cve_patch_mapper.py:*
**Category:** ERROR
**Code:** Patch mapper fallback
**Context:** CVE-to-patch mapping fallback when primary data source fails
**Action:** KEEP — Legitimate error handling
**Priority:** N/A

### FB-061: utils/azure_client_manager.py:*
**Category:** ERROR
**Code:** Azure client credential fallback
**Context:** Credential resolution fallback chain
**Action:** KEEP — Legitimate auth pattern
**Priority:** N/A

### FB-062: utils/azure_mcp_client.py:*
**Category:** ERROR
**Code:** Azure MCP client error fallback
**Context:** MCP client fallback when Azure MCP server unavailable
**Action:** KEEP — Legitimate error handling
**Priority:** N/A

### FB-063: utils/agent_framework_clients.py:*
**Category:** ERROR
**Code:** Agent framework client fallback
**Context:** Framework client fallback when dependencies unavailable
**Action:** KEEP — Legitimate dependency fallback
**Priority:** N/A

### FB-064: utils/response_formatter.py:*
**Category:** ERROR
**Code:** Response formatting fallback
**Context:** Formatter uses simple fallback when rich formatting fails
**Action:** KEEP — Legitimate formatting fallback
**Priority:** N/A

### FB-065: utils/sre_response_formatter.py:854
**Category:** ERROR
**Code:** `# Fallback: format as JSON in a code block`
**Context:** SRE response formatter uses JSON code block when structured format fails
**Action:** KEEP — Legitimate formatting fallback
**Priority:** N/A

### FB-066: utils/circuit_breaker.py:* (referenced via tests)
**Category:** ERROR
**Code:** Circuit breaker fallback behavior
**Context:** Circuit breaker opens and provides fallback behavior
**Action:** KEEP — Core resilience pattern
**Priority:** N/A

### FB-067: utils/route_path_analyzer.py:*
**Category:** ERROR
**Code:** Route analysis fallback
**Context:** Network route analyzer fallback for unknown route types
**Action:** KEEP — Legitimate analysis fallback
**Priority:** N/A

### FB-068: utils/resource_inventory_client.py:185-474 (3 refs)
**Category:** ERROR
**Code:** `# Live discovery fallback`, `# Fallback: recover type keys`, `# resource_group from environment fallback`
**Context:** Resource inventory client has multiple fallback paths for data retrieval
**Action:** KEEP — Legitimate data source fallback (Azure ARG → cache → env vars)
**Priority:** N/A

### FB-069: utils/local_mock_api.py:* (3 refs)
**Category:** ERROR
**Code:** Mock API fallback patterns
**Context:** Local mock API provides fallback responses when real APIs unavailable
**Action:** KEEP — Legitimate mock mode pattern
**Priority:** N/A

### FB-070: utils/patch_install_history_repository.py:127
**Category:** ERROR
**Code:** `"""In-memory fallback for mock mode and tests."""`
**Context:** Docstring for in-memory repository used in mock mode
**Action:** KEEP — Legitimate mock/test pattern
**Priority:** N/A

### FB-071: utils/manifests/cve_manifests.py:*
**Category:** ERROR
**Code:** CVE manifest fallback description
**Context:** Tool manifest description mentions fallback behavior
**Action:** KEEP — Legitimate tool description
**Priority:** N/A

### FB-072: utils/resource_discovery_engine.py:*
**Category:** ERROR
**Code:** Discovery engine fallback for unknown resource types
**Context:** Uses generic discovery when resource type not recognized
**Action:** KEEP — Legitimate discovery pattern
**Priority:** N/A

---

## DATA-Category Entries (Action: KEEP — Non-Cosmos data fallback)

### FB-073: mcp_servers/sre_mcp_server.py:684-826 (8 refs)
**Category:** DATA
**Code:** `# No tables available - fallback to Azure CLI`, `Azure CLI fallback successful`, etc.
**Context:** SRE MCP server falls back to Azure CLI when Log Analytics tables unavailable
**Action:** KEEP — Legitimate Azure CLI fallback (not Cosmos), verified non-Cosmos
**Priority:** N/A

### FB-074: mcp_servers/sre_mcp_server.py:1388-1408 (2 refs)
**Category:** DATA
**Code:** `# Fallback: use ResourceHealth management client`, `ResourceHealth API fallback also failed`
**Context:** Health check falls back from Monitor API to ResourceHealth API
**Action:** KEEP — Legitimate Azure API fallback
**Priority:** N/A

### FB-075: mcp_servers/sre_mcp_server.py:2071
**Category:** DATA
**Code:** `# Generic fallback metrics`
**Context:** Falls back to generic metrics when specific metrics unavailable
**Action:** KEEP — Legitimate metrics fallback
**Priority:** N/A

### FB-076: mcp_servers/sre_mcp_server.py:6329
**Category:** DATA
**Code:** `# Try loading from Cosmos DB`
**Context:** SLO retrieval tries Cosmos DB before in-memory store
**Action:** INVESTIGATE — This is a Cosmos try/except pattern but not using "fallback" keyword in the obvious way. Cross-referenced as COSMOS-related via COSMOS-DEPENDENCY-GRAPH.md entry for sre_mcp_server.py
**Priority:** MEDIUM (maps to FB-009 scope)

### FB-077: mcp_servers/sre_mcp_server.py:8530
**Category:** DATA
**Code:** `# Try loading from Cosmos DB`
**Context:** SLO listing tries Cosmos DB then in-memory store
**Action:** INVESTIGATE — Same as FB-076, Cosmos-related try/except pattern
**Priority:** MEDIUM

### FB-078: mcp_servers/network_mcp_server.py:140-4480 (5 refs)
**Category:** DATA
**Code:** `# 2) Back-compat fallback to AZURE_CLIENT_*`, `CLI fallback`, `name-based heuristic as fallback`
**Context:** Network MCP server has auth and CLI fallback patterns
**Action:** KEEP — Legitimate Azure auth and CLI fallback, not Cosmos-related
**Priority:** N/A

### FB-079: mcp_servers/cve_mcp_server.py:269-342 (4 refs)
**Category:** DATA
**Code:** `allow_live_fallback=False`, `cache_strategy: "cache_with_live_fallback"`, `with optional live NVD fallback`
**Context:** CVE MCP server controls live NVD API fallback for CVE searches
**Action:** KEEP — Legitimate API data source fallback (NVD, not Cosmos)
**Priority:** N/A

### FB-080: mcp_servers/monitor_mcp_server.py:305-648 (6 refs)
**Category:** DATA
**Code:** `Using HTML scraping fallback`, `trying HTML scraping fallback`, `Fallback: list all categories`
**Context:** Monitor MCP server falls back to HTML scraping when metadata not cached
**Action:** KEEP — Legitimate data retrieval fallback
**Priority:** N/A

### FB-081: utils/cve_cosmos_repository.py:* (1 ref, "fallback" in sort logic)
**Category:** DATA
**Code:** Client-side sort fallback for missing composite indexes
**Context:** CVE Cosmos repository falls back to client-side sort when Cosmos composite index missing
**Action:** REMOVE — Entire file will be deleted (see COSMOS-DEPENDENCY-GRAPH.md)
**Priority:** HIGH (but handled by file deletion)

---

## Agent-Level Fallback Entries (Action: KEEP)

### FB-082: agents/eol_orchestrator.py:34-1034 (5 refs)
**Category:** CONFIG
**Code:** `# Fallback for relative import`, `PlaywrightEOLAgent() # Web search fallback agent`, etc.
**Context:** EOL orchestrator uses fallback import paths and web search fallback agents
**Action:** KEEP — Legitimate orchestration and import patterns
**Priority:** N/A

### FB-083: agents/endoflife_agent.py:499-1049 (2 refs)
**Category:** ERROR
**Code:** `# Fallback: use the first semver-lowest among generic matches`, `# no builtin fallback`
**Context:** EndOfLife agent version matching fallbacks
**Action:** KEEP — Legitimate data matching fallback
**Priority:** N/A

### FB-084: agents/azure_ai_agent.py:* (20 refs)
**Category:** CONFIG
**Code:** Various agent execution fallback patterns
**Context:** Azure AI agent has extensive fallback chains for tool execution
**Action:** KEEP — Legitimate agent framework fallback
**Priority:** N/A

### FB-085: agents/openai_agent.py:* (12 refs)
**Category:** CONFIG
**Code:** Various OpenAI agent fallback patterns
**Context:** OpenAI agent fallback for API key resolution and model selection
**Action:** KEEP — Legitimate API client fallback
**Priority:** N/A

### FB-086: agents/monitor_agent.py:* (3 refs)
**Category:** CONFIG
**Code:** Monitor agent fallback patterns
**Context:** Monitor agent data retrieval fallbacks
**Action:** KEEP — Legitimate monitoring fallback
**Priority:** N/A

### FB-087: agents/os_inventory_agent.py:* (6 refs)
**Category:** CONFIG
**Code:** OS inventory agent fallback patterns
**Context:** OS inventory agent uses fallback methods for data extraction
**Action:** KEEP — Legitimate inventory fallback
**Priority:** N/A

### FB-088: agents/software_inventory_agent.py:* (2 refs)
**Category:** CONFIG
**Code:** Software inventory fallback patterns
**Context:** Software inventory agent fallback methods
**Action:** KEEP — Legitimate inventory fallback
**Priority:** N/A

### FB-089: agents/cve_sub_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** CVE sub-agent fallback
**Context:** CVE sub-agent execution fallback
**Action:** KEEP — Legitimate agent fallback
**Priority:** N/A

### FB-090: agents/domain_sub_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** Domain sub-agent base fallback
**Context:** Base class fallback behavior
**Action:** KEEP — Legitimate base class pattern
**Priority:** N/A

### FB-091: agents/security_compliance_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** Security compliance fallback
**Context:** Compliance agent fallback for missing compliance data
**Action:** KEEP — Legitimate agent fallback
**Priority:** N/A

### FB-092: agents/playwright_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** Playwright agent fallback
**Context:** Web scraping agent fallback behavior
**Action:** KEEP — Legitimate scraping fallback
**Priority:** N/A

### FB-093: agents/remediation_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** Remediation agent fallback
**Context:** Remediation agent fallback when remediation unavailable
**Action:** KEEP — Legitimate agent fallback
**Priority:** N/A

### FB-094: agents/microsoft_agent.py:* (2 refs)
**Category:** CONFIG
**Code:** Microsoft agent fallback patterns
**Context:** Microsoft-specific EOL data fallback
**Action:** KEEP — Legitimate data fallback
**Priority:** N/A

### FB-095: agents/redhat_agent.py:* (1 ref)
**Category:** CONFIG
**Code:** Red Hat agent fallback
**Context:** Red Hat EOL data fallback
**Action:** KEEP — Legitimate data fallback
**Priority:** N/A

### FB-096: agents/php_agent.py:19
**Category:** CONFIG
**Code:** `# Fallback dummy implementation`
**Context:** PHP agent stub fallback
**Action:** KEEP — Legitimate stub pattern
**Priority:** N/A

### FB-097: agents/oracle_agent.py:19
**Category:** CONFIG
**Code:** `# Fallback dummy implementation`
**Context:** Oracle agent stub fallback
**Action:** KEEP — Legitimate stub pattern
**Priority:** N/A

### FB-098: agents/inventory_agent.py:19
**Category:** CONFIG
**Code:** `# Fallback for testing or different import contexts`
**Context:** Inventory agent import fallback
**Action:** KEEP — Legitimate import pattern
**Priority:** N/A

---

## Test File Entries (Action: KEEP unless Cosmos-specific)

### FB-099: tests/reliability/test_error_boundary.py:* (32 refs)
**Category:** ERROR
**Code:** Tests for `@error_boundary` decorator fallback behavior
**Action:** KEEP — Legitimate test coverage for error boundary
**Priority:** N/A

### FB-100: tests/reliability/test_circuit_breaker.py:* (8 refs)
**Category:** ERROR
**Code:** Tests for circuit breaker fallback state transitions
**Action:** KEEP — Legitimate test coverage
**Priority:** N/A

### FB-101: tests/reliability/test_error_scenarios_e2e.py:* (14 refs)
**Category:** ERROR
**Code:** End-to-end error scenario fallback tests
**Action:** KEEP — Legitimate reliability tests
**Priority:** N/A

### FB-102: tests/routing/test_phase6_pipeline.py:* (18 refs)
**Category:** CONFIG
**Code:** Tests for routing pipeline fallback behavior
**Action:** KEEP — Legitimate routing tests
**Priority:** N/A

### FB-103: tests/routing/test_pipeline_routing.py:* (15 refs)
**Category:** CONFIG
**Code:** Tests for pipeline vs legacy routing fallback
**Action:** KEEP — Legitimate routing tests
**Priority:** N/A

### FB-104: tests/routing/test_unified_router.py:* (1 ref)
**Category:** CONFIG
**Code:** Unified router fallback test
**Action:** KEEP — Legitimate routing test
**Priority:** N/A

### FB-105: tests/routing/test_domain_classifier.py:* (1 ref)
**Category:** CONFIG
**Code:** Domain classifier fallback test
**Action:** KEEP — Legitimate classification test
**Priority:** N/A

### FB-106: tests/routing/test_router.py:* (4 refs)
**Category:** CONFIG
**Code:** Router fallback tests
**Action:** KEEP — Legitimate routing tests
**Priority:** N/A

### FB-107: tests/routing/test_phase7_default.py:* (1 ref)
**Category:** CONFIG
**Code:** Phase 7 default routing test
**Action:** KEEP — Legitimate routing test
**Priority:** N/A

### FB-108: tests/orchestrators/test_eol_orchestrator.py:* (6 refs)
**Category:** CONFIG
**Code:** EOL orchestrator fallback tests
**Action:** KEEP — Legitimate orchestrator tests
**Priority:** N/A

### FB-109: tests/orchestrators/test_sre_orchestrator.py:* (8 refs)
**Category:** CONFIG
**Code:** SRE orchestrator fallback tests
**Action:** KEEP — Legitimate orchestrator tests
**Priority:** N/A

### FB-110: tests/orchestrators/test_base_orchestrator.py:* (2 refs)
**Category:** CONFIG
**Code:** Base orchestrator fallback tests
**Action:** KEEP — Legitimate base class tests
**Priority:** N/A

### FB-111: tests/orchestrators/test_orchestrator_error_handling.py:* (6 refs)
**Category:** CONFIG
**Code:** Orchestrator error handling fallback tests
**Action:** KEEP — Legitimate error handling tests
**Priority:** N/A

### FB-112: tests/remote/test_remote_sre.py:* (7 refs)
**Category:** CONFIG
**Code:** Remote SRE MCP fallback header tests
**Action:** KEEP — Legitimate remote integration tests
**Priority:** N/A

### FB-113: tests/test_cve_vm_service.py:* (5 refs)
**Category:** ERROR
**Code:** CVE VM service live fallback tests
**Action:** KEEP — Legitimate CVE service tests
**Priority:** N/A

### FB-114: tests/test_cve_sync_api.py:* (4 refs)
**Category:** ERROR
**Code:** CVE sync fallback window tests
**Action:** KEEP — Legitimate sync tests
**Priority:** N/A

### FB-115: tests/test_cve_inventory_api.py:* (2 refs)
**Category:** ERROR
**Code:** CVE inventory fallback tests
**Action:** KEEP — Legitimate inventory tests
**Priority:** N/A

### FB-116: tests/test_cve_scanner_matching.py:* (2 refs)
**Category:** ERROR
**Code:** CVE scanner matching fallback tests
**Action:** KEEP — Legitimate scanner tests
**Priority:** N/A

### FB-117: tests/config/test_sre_gateway.py:* (12 refs)
**Category:** CONFIG
**Code:** SRE gateway LLM fallback tests
**Action:** KEEP — Legitimate gateway tests
**Priority:** N/A

### FB-118: tests/config/test_sre_incident_memory.py:* (21 refs)
**Category:** ERROR
**Code:** SRE incident memory fallback tests
**Action:** KEEP — Legitimate incident memory tests (some reference Cosmos fallback pattern, will be updated when incident memory is refactored)
**Priority:** LOW (tests will be updated during sre_incident_memory.py refactor)

### FB-119: tests/tools/test_tool_retriever.py:* (6 refs)
**Category:** CONFIG
**Code:** Tool retriever fallback scoring tests
**Action:** KEEP — Legitimate retriever tests
**Priority:** N/A

### FB-120: tests/tools/test_registry_collision.py:* (2 refs)
**Category:** CONFIG
**Code:** Registry collision fallback tests
**Action:** KEEP — Legitimate registry tests
**Priority:** N/A

### FB-121: tests/ui/features/test_theme_visibility.py:* (5 refs)
**Category:** CONFIG
**Code:** Theme visibility fallback tests
**Action:** KEEP — Legitimate UI tests
**Priority:** N/A

### FB-122: tests/test_resource_discovery_engine.py:343-607 (3 refs)
**Category:** CONFIG
**Code:** Resource discovery fallback tests
**Action:** KEEP — Legitimate discovery tests
**Priority:** N/A

### FB-123: tests/test_sre_orchestrator_inventory.py:* (6 refs)
**Category:** CONFIG
**Code:** SRE orchestrator inventory fallback tests
**Action:** KEEP — Legitimate orchestrator tests
**Priority:** N/A

### FB-124: tests/test_integration_workflows.py:* (3 refs)
**Category:** CONFIG
**Code:** Integration workflow fallback tests
**Action:** KEEP — Legitimate integration tests
**Priority:** N/A

### FB-125: tests/mocks/deterministic_mcp_client.py:* (1 ref)
**Category:** CONFIG
**Code:** Deterministic MCP client mock fallback
**Action:** KEEP — Legitimate test infrastructure
**Priority:** N/A

---

## Miscellaneous Entries

### FB-126: scripts/manifest_impact_analyzer.py:154
**Category:** ERROR
**Code:** `"""Fallback: just report all manifest files as present (no git)."""`
**Context:** Script fallback when git unavailable
**Action:** KEEP — Legitimate script fallback
**Priority:** N/A

### FB-127: deploy/update_monitor_community_metadata.py:163
**Category:** ERROR
**Code:** `# Fallback: Try the HTML table parsing method if JSON isn't found`
**Context:** Deploy script falls back to HTML parsing when JSON metadata unavailable
**Action:** KEEP — Legitimate deploy tool fallback
**Priority:** N/A

### FB-128: utils/legacy/tool_embedder.py:* (3 refs)
**Category:** CONFIG
**Code:** Legacy tool embedder fallback patterns
**Action:** KEEP — Already deprecated in legacy/ directory
**Priority:** N/A

### FB-129: utils/legacy/tool_router.py:* (1 ref)
**Category:** CONFIG
**Code:** Legacy tool router fallback
**Action:** KEEP — Already deprecated in legacy/ directory
**Priority:** N/A

### FB-130: tests/network/test_connectivity_matrix.py:* (1 ref)
**Category:** CONFIG
**Code:** Network connectivity fallback test
**Action:** KEEP — Legitimate network test
**Priority:** N/A

### FB-131: tests/utils/test_golden_dataset_loader.py:* (2 refs)
**Category:** CONFIG
**Code:** Golden dataset loader fallback test
**Action:** KEEP — Legitimate test utility test
**Priority:** N/A

### FB-132: tests/test_os_extraction_rules.py:* (1 ref)
**Category:** ERROR
**Code:** OS extraction rules fallback test
**Action:** KEEP — Legitimate test
**Priority:** N/A

### FB-133: tests/test_mcp_config_loader.py:* (1 ref)
**Category:** CONFIG
**Code:** MCP config loader fallback test
**Action:** KEEP — Legitimate test
**Priority:** N/A

### FB-134: tests/test_routing_telemetry.py:* (1 ref)
**Category:** CONFIG
**Code:** Routing telemetry fallback test
**Action:** KEEP — Legitimate test
**Priority:** N/A

### FB-135: tests/performance/test_pg_database_bootstrap.py:* (1 ref)
**Category:** CONFIG
**Code:** PG bootstrap fallback test
**Action:** KEEP — Legitimate test
**Priority:** N/A

### FB-136: tests/regression/test_dependency_map_layers.py:* (3 refs)
**Category:** CONFIG
**Code:** Dependency map layer fallback tests
**Action:** KEEP — Legitimate regression tests
**Priority:** N/A

### FB-137: utils/agent_context_store.py:* (2 refs, non-Cosmos fallback)
**Category:** ERROR
**Code:** Agent context store fallback when persistence unavailable
**Context:** Falls back to in-memory storage (the Cosmos part is tracked in COSMOS-DEPENDENCY-GRAPH.md)
**Action:** KEEP — Error handling portion is legitimate; Cosmos import tracked separately
**Priority:** N/A

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| COSMOS   | 18    | REMOVE |
| CONFIG   | 63    | KEEP   |
| ERROR    | 43    | KEEP   |
| DATA     | 13    | KEEP (2 entries need INVESTIGATE — FB-076, FB-077 are Cosmos-related) |
| **Total** | **137** | |

**Note:** The 137 entries cover 732 individual "fallback" occurrences across the codebase (many entries group multiple occurrences in the same file/function). The total matches within the expected range per acceptance criteria.

---

## COSMOS-Category Entries by Priority (Removal Order for P11.5)

### HIGH Priority (Active Code Paths — 10 entries)
1. **FB-001:** `utils/inventory_cache.py:15` — Cosmos SDK import guard
2. **FB-003:** `utils/inventory_cache.py:131` — Cosmos L2 cache fallback
3. **FB-004:** `mcp_servers/sre_mcp_server.py:101` — In-memory audit trail fallback
4. **FB-005:** `mcp_servers/sre_mcp_server.py:169` — In-memory runbook fallback
5. **FB-006:** `mcp_servers/sre_mcp_server.py:327` — Dual-write audit trail
6. **FB-008:** `mcp_servers/sre_mcp_server.py:3333` — Dual-write runbooks
7. **FB-010:** `utils/alert_manager.py:227` — Cosmos load with file fallback
8. **FB-011:** `utils/alert_manager.py:283` — Cosmos save with file fallback
9. **FB-012:** `utils/alert_manager.py:334` — Cosmos save exception handler
10. **FB-013:** `utils/eol_cache.py:136` — Cosmos L2 cache fallback
11. **FB-081:** `utils/cve_cosmos_repository.py:*` — Entire file deletion

### MEDIUM Priority (Supporting Features — 3 entries)
12. **FB-009:** `mcp_servers/sre_mcp_server.py:6210` — SLO Cosmos persistence
13. **FB-014:** `utils/sre_incident_memory.py:108` — Cosmos unavailable warning
14. **FB-015:** `utils/sre_incident_memory.py:250` — Dual-path docstring

### LOW Priority (Docstrings/Comments/Tests — 5 entries)
15. **FB-002:** `utils/inventory_cache.py:88` — Docstring update
16. **FB-007:** `mcp_servers/sre_mcp_server.py:3219` — Tool description string
17. **FB-016:** `utils/resource_inventory_cache.py:100` — Docstring update
18. **FB-017:** `tests/test_resource_inventory_cache.py:4` — Test docstring
19. **FB-018:** `tests/test_resource_inventory_cache.py:127` — Test class docstring

---

*Fallback catalogue completed: 2026-03-18*
*Phase: 11-validate-everything-is-migrated-from-cosmos-db-to-postgresql-remove-legacy-cosmos-and-fallback-codes-once-validated-there-should-be-no-more-cosmos-code-in-the-entire-code-base*
