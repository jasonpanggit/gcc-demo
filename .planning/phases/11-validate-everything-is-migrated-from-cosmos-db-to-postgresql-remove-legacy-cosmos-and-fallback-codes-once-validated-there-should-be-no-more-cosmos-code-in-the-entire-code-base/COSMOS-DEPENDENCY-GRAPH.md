# Cosmos Dependency Graph

**Generated:** 2026-03-18
**Source files:** `utils/cosmos_cache.py` (374 lines), `utils/cve_cosmos_repository.py` (442 lines)
**Total consumer files:** 24 (excluding the 2 core files themselves)

---

## cosmos_cache.py Consumers

### Direct `base_cosmos` Import & Usage

| # | File | Import Line | Usage Pattern | Specific Calls | Action |
|---|------|-------------|---------------|----------------|--------|
| 1 | `utils/eol_cache.py` | `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos._initialize_async()`, `base_cosmos.get_container(self.container_id)`, `base_cosmos.initialized` | Refactor to EOLPostgresRepository |
| 2 | `utils/eol_inventory.py` | `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos._initialize_async()`, `base_cosmos.get_container(...)` | Refactor to EOLPostgresRepository |
| 3 | `utils/resource_inventory_cache.py` | `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos.initialized`, `base_cosmos._ensure_initialized()`, `base_cosmos.get_container(...)` | Refactor to InventoryPostgresRepository |
| 4 | `utils/inventory_cache.py` | `from .cosmos_cache import BaseCosmosClient` + `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | Constructor takes `BaseCosmosClient`, uses `cosmos_client.get_container(...)` throughout; module-level `inventory_cache = InventoryRawCache(base_cosmos)` | Refactor to InventoryCachePostgresRepository |
| 5 | `utils/alert_manager.py` | `from utils.cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos.initialized`, `base_cosmos.get_container(...)`, `base_cosmos._initialize_async()` | Refactor to AlertPostgresRepository + NotificationPostgresRepository |
| 6 | `utils/agent_context_store.py` | `from utils.cosmos_cache import base_cosmos` (try/except dual import) | Cache reader + writer + Singleton user | `base_cosmos._ensure_initialized()`, `base_cosmos.initialized`, `base_cosmos.get_container(...)` | Refactor to SREPostgresRepository or in-memory dict |
| 7 | `utils/sre_incident_memory.py` | `from utils.cosmos_cache import base_cosmos` (try/except dual import) | Cache reader + writer + Singleton user | `base_cosmos._ensure_initialized()`, `base_cosmos.initialized`, `base_cosmos.get_container(...)` | Refactor to SREPostgresRepository |
| 8 | `utils/patch_assessment_repository.py` | `from utils.cosmos_cache import base_cosmos` (try/except dual import) | Cache reader + writer + Singleton user | `base_cosmos.initialized`, `base_cosmos._initialize_async()`, `base_cosmos.get_container(...)` | Refactor to PatchAssessmentPostgresRepository |
| 9 | `utils/os_extraction_rules.py` | `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos.get_container(...)`, `base_cosmos._initialize_async()` | Refactor to PostgreSQL table (already exists) |
| 10 | `utils/cve_inventory_sync.py` | `from .cosmos_cache import base_cosmos` | Cache writer + Singleton user | `base_cosmos.get_container(...)` | Refactor to PostgresCVEScanRepository |
| 11 | `utils/vendor_url_inventory.py` | `from .cosmos_cache import base_cosmos` | Cache reader + writer + Singleton user | `base_cosmos._initialize_async()`, `base_cosmos.get_container(...)` | Refactor to PostgreSQL table (already exists) |
| 12 | `mcp_servers/sre_mcp_server.py` | `from utils.cosmos_cache import base_cosmos` (3 locations) | Cache reader + writer + Singleton user | `base_cosmos._ensure_initialized()`, `base_cosmos.initialized`, `base_cosmos.get_container(...)` for audit_trail, custom_runbooks, slo_definitions containers | Refactor to SREPostgresRepository |
| 13 | `api/eol.py` | `from utils.cosmos_cache import base_cosmos` | Singleton user (guard check) | `base_cosmos.initialized` check before eol_cache operations | Remove guard check |
| 14 | `api/sre_audit.py` | `from utils.cosmos_cache import cosmos_cache` (BUG: wrong import name) | Cache reader + Singleton user | `cosmos_cache._ensure_initialized()`, `cosmos_cache.initialized`, `cosmos_cache.get_container(...)` for audit_trail | Refactor to SREPostgresRepository |
| 15 | `api/debug.py` | `from utils.cosmos_cache import base_cosmos` (2 locations) | Cache reader + writer + Singleton user (test/validation endpoints) | `base_cosmos.initialized`, `base_cosmos._initialize_async()`, `base_cosmos.get_container(...)`, `base_cosmos.last_error`, `base_cosmos.cosmos_client`, `base_cosmos.database`, `base_cosmos.get_cache_info()` | Remove Cosmos test/validation endpoints entirely |
| 16 | `main.py` | `from utils.cosmos_cache import base_cosmos` (15 locations) | Cache reader + writer + Singleton user + Config reference | `base_cosmos.cosmos_client`, `base_cosmos.initialized`, `base_cosmos._initialize_async()`, `base_cosmos.get_container(...)`, `base_cosmos.last_error`, `base_cosmos.get_cache_info()` for CVE/KB/scan/patch init + 6 Cosmos API endpoints + startup init + cache validation | Major refactor: remove Cosmos API endpoints, remove startup init, refactor service singletons to use PG repos |
| 17 | `utils/endpoint_decorators.py` | None (no import) | Comment/docstring only | `base_cosmos.is_available()` appears in docstring usage example only | Update docstring |

### `get_cosmos_client()` Consumers

| # | File | Import Line | Usage Pattern | Specific Calls | Action |
|---|------|-------------|---------------|----------------|--------|
| 18 | `utils/cve_alert_rule_manager.py` | `from utils.cosmos_cache import get_cosmos_client` | Cache reader + writer | `get_cosmos_client().get_container_client(database="eol_db", container="cve_alert_rules")` for rule CRUD | Refactor to AlertPostgresRepository |
| 19 | `utils/cve_alert_history_manager.py` | `from utils.cosmos_cache import get_cosmos_client` | Cache reader + writer | `get_cosmos_client().get_container_client(database="eol_db", container="cve_alert_history")` for history CRUD | Refactor to AlertPostgresRepository |

### Test File Consumers

| # | File | Import Line | Usage Pattern | Specific Calls | Action |
|---|------|-------------|---------------|----------------|--------|
| 20 | `tests/cache/test_cosmos_cache.py` | `from utils.cosmos_cache import BaseCosmosClient` + `from utils import cosmos_cache` | Direct test target | Tests BaseCosmosClient initialization, module attributes, COSMOS_IMPORTS_OK | DELETE entire file |
| 21 | `tests/cache/test_eol_cache.py` | `patch('utils.eol_cache.base_cosmos')` | Mock usage | Patches `base_cosmos.initialized` and `base_cosmos._initialize_async` in eol_cache tests | UPDATE mocks to remove cosmos patches |
| 22 | `tests/cache/test_resource_inventory_cache.py` | `patch('utils.resource_inventory_cache.base_cosmos')` | Mock usage | Patches `base_cosmos.initialized`, `base_cosmos._ensure_initialized`, `base_cosmos.get_container` | UPDATE mocks to remove cosmos patches |

---

## cve_cosmos_repository.py Consumers

| # | File | Import Line | Usage Pattern | Specific Calls | Action |
|---|------|-------------|---------------|----------------|--------|
| 23 | `main.py` | `from utils.cve_cosmos_repository import CVECosmosRepository` | Cache writer + Singleton user | `CVECosmosRepository(cosmos_client=..., database_name=..., container_name=...)` in `get_cve_service()` | Replace with CVEPostgresRepository (already exists in `repositories/cve_repository.py`) |
| 24 | `utils/cve_service.py` | `from utils.cve_cosmos_repository import CVECosmosRepository` (try/except dual import) | Type hint + Singleton user | `CVECosmosRepository` used as constructor type hint for `repository` parameter; `CVECosmosRepository()` in `get_cve_service()` | Replace type hint with Protocol/ABC; update `get_cve_service()` to use CVEPostgresRepository |

### Test File Consumer

| # | File | Import Line | Usage Pattern | Specific Calls | Action |
|---|------|-------------|---------------|----------------|--------|
| 25 | `tests/test_cve_cosmos_repository.py` | `from utils.cve_cosmos_repository import CVECosmosRepository, CVE_DATA_INDEXING_POLICY` | Direct test target | Tests CVECosmosRepository upsert, query, count operations | DELETE entire file |

---

## Summary

| Usage Pattern | File Count | Files |
|---------------|------------|-------|
| Dead import | 0 | (none found - all imports are actively used) |
| Cache reader | 2 | `cve_alert_rule_manager.py`, `cve_alert_history_manager.py` (read + write combined) |
| Cache writer | 0 | (all writers also read - categorized as reader + writer) |
| Cache reader + writer | 14 | `eol_cache.py`, `eol_inventory.py`, `resource_inventory_cache.py`, `inventory_cache.py`, `alert_manager.py`, `agent_context_store.py`, `sre_incident_memory.py`, `patch_assessment_repository.py`, `os_extraction_rules.py`, `cve_inventory_sync.py`, `vendor_url_inventory.py`, `sre_mcp_server.py`, `sre_audit.py`, `debug.py` |
| Singleton user | 16 | Most cache reader+writer files also use singleton (`base_cosmos.initialized`, `_ensure_initialized()`, `_initialize_async()`) |
| Config reference | 1 | `main.py` (accesses `config.azure.cosmos_database`, `config.cve_data.cosmos_container_name`, etc.) |
| Comment/docstring only | 1 | `endpoint_decorators.py` |
| Type hint only | 1 | `cve_service.py` (uses `CVECosmosRepository` as constructor parameter type) |
| Direct test target | 2 | `test_cosmos_cache.py`, `test_cve_cosmos_repository.py` |
| Mock/patch usage | 2 | `test_eol_cache.py`, `test_resource_inventory_cache.py` |
| BUG (wrong import name) | 1 | `sre_audit.py` (imports `cosmos_cache` instead of `base_cosmos`) |

---

## Removal Order

Files listed from lowest to highest risk (leaves first, roots last):

### Tier 1: Test Files (Zero Runtime Risk)
1. `tests/cache/test_cosmos_cache.py` - DELETE (direct test of BaseCosmosClient)
2. `tests/test_cve_cosmos_repository.py` - DELETE (direct test of CVECosmosRepository)
3. `tests/cache/test_eol_cache.py` - UPDATE (remove `base_cosmos` mock patches)
4. `tests/cache/test_resource_inventory_cache.py` - UPDATE (remove `base_cosmos` mock patches)

### Tier 2: Comment/Docstring Only (Zero Behavioral Risk)
5. `utils/endpoint_decorators.py` - UPDATE docstring (remove Cosmos DB example)

### Tier 3: Guard-Check-Only Consumers (Low Risk)
6. `api/eol.py` - REMOVE `base_cosmos.initialized` guard check (1 location)

### Tier 4: API Endpoint Consumers (Medium Risk - Deletable Endpoints)
7. `api/debug.py` - REMOVE Cosmos test/validation endpoints (2 endpoint functions)
8. `api/sre_audit.py` - REFACTOR to SREPostgresRepository (3 endpoints, also fix BUG)

### Tier 5: Utility Consumer Refactors (Medium-High Risk)
9. `utils/cve_alert_rule_manager.py` - REFACTOR to AlertPostgresRepository
10. `utils/cve_alert_history_manager.py` - REFACTOR to AlertPostgresRepository
11. `utils/vendor_url_inventory.py` - REFACTOR to PostgreSQL table
12. `utils/os_extraction_rules.py` - REFACTOR to PostgreSQL table
13. `utils/cve_inventory_sync.py` - REFACTOR to PostgresCVEScanRepository
14. `utils/agent_context_store.py` - REFACTOR to SREPostgresRepository or in-memory
15. `utils/sre_incident_memory.py` - REFACTOR to SREPostgresRepository
16. `utils/patch_assessment_repository.py` - REFACTOR to PatchAssessmentPostgresRepository
17. `utils/eol_cache.py` - REFACTOR to EOLPostgresRepository
18. `utils/eol_inventory.py` - REFACTOR to EOLPostgresRepository
19. `utils/resource_inventory_cache.py` - REFACTOR to InventoryPostgresRepository
20. `utils/alert_manager.py` - REFACTOR to AlertPostgresRepository + NotificationPostgresRepository
21. `utils/inventory_cache.py` - REFACTOR constructor to remove BaseCosmosClient dependency

### Tier 6: MCP Server Refactor (High Risk)
22. `mcp_servers/sre_mcp_server.py` - REFACTOR 3 container access points to SREPostgresRepository

### Tier 7: Service Layer Refactor (High Risk)
23. `utils/cve_service.py` - REFACTOR type hint and singleton initialization to CVEPostgresRepository

### Tier 8: Application Entry Point (Highest Risk)
24. `main.py` - REFACTOR: remove 6 Cosmos API endpoints, remove Cosmos startup init, refactor 5+ service singletons to use PG repos

### Tier 9: Core File Deletion (Final Step)
25. `utils/cosmos_cache.py` - DELETE (only after all 24 consumers refactored)
26. `utils/cve_cosmos_repository.py` - DELETE (only after main.py + cve_service.py refactored)

---

*Dependency graph built: 2026-03-18*
*Phase: 11-validate-everything-is-migrated-from-cosmos-db-to-postgresql-remove-legacy-cosmos-and-fallback-codes-once-validated-there-should-be-no-more-cosmos-code-in-the-entire-code-base*
