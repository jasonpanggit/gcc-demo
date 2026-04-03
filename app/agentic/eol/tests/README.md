# EOL App — Test Suite

Pytest-based test suite for the EOL Agentic platform. Runs entirely on mock data
— no Azure credentials required for the default local mode.

---

## Quick Start

```bash
# From the project root (uses venv automatically)
cd app/agentic/eol/tests
./run_tests.sh
```

Expected: all local tests collected and run in mock mode.

---

## Layout Conventions

- Keep domain-specific tests in the closest matching folder: `agents/`, `cache/`, `services/`, `utils/`, `orchestrators/`, `mcp_servers/`, `ui/`, and so on.
- Keep top-level files only for cross-cutting suites that span multiple domains, especially API contract regression tests and a small number of broad integration flows.
- If a test targets one concrete module or manager, it should not live at the top level.
- Disabled historical artifacts should be removed instead of left behind as `.skip` files.

Recent cleanup moved obvious strays into their domain folders, for example:

- `services/test_cve_alert_history_manager.py`
- `cache/test_resource_inventory_cache.py`
- `utils/test_nvd_client.py`
- `utils/test_vendor_feed_client.py`
- `utils/test_repository_state.py`

---

## Execution Modes

All modes are driven by `run_tests.sh`. Run `./run_tests.sh --help` for the full
reference.

### Target flags

| Flag | What it does |
|------|-------------|
| *(none)* | Local mode — ASGI transport, mock data, no Azure needed |
| `--remote` | Remote mode — tests against the Azure Container Apps deployment |
| `--url URL` | Custom URL — tests against any HTTP server |

### Category flags

| Flag | Equivalent pytest args | What it runs |
|------|------------------------|-------------|
| `--unit` | `-m unit` | Pure unit tests (orchestrators, utilities) |
| `--integration` | `-m integration` | API endpoint tests via ASGI client |
| `--mcp` | `-m mcp` | All MCP server tool tests |
| `--mcp-server NAME` | `-m mcp_<name>` | Single MCP server for the marker-backed suites (see names below) |

Marker-backed MCP server names: `sre`, `inventory`, `monitor`, `os_eol`, `azure_cli`, `azure`

Newer MCP-focused coverage such as CVE flows is currently run by targeting the test files directly, for example `./run_tests.sh tests/test_cve_mcp_server.py`.

### Coverage flags

| Flag | What it does |
|------|-------------|
| `--coverage` | HTML + terminal coverage for `mcp_servers`, `agents`, `utils` |
| `--coverage-module MOD` | Coverage for a single module (`mcp_servers`, `agents`, `utils`) |

### Output flags

| Flag | What it does |
|------|-------------|
| `--verbose` | `-vv` — show individual assertion diffs |
| `--debug` | `LOG_LEVEL=DEBUG` + `-s` to expose stdout (useful for mock agent print output) |
| `--parallel N` | Run with `N` pytest-xdist workers (requires `pip install pytest-xdist`) |

### Useful direct pytest patterns

```bash
# Run a single file
./run_tests.sh tests/test_sre_mcp_tools.py

# Run tests matching a name pattern
./run_tests.sh tests/ -k test_mcp

# Stop at first failure
./run_tests.sh tests/ -x

# Stop after 3 failures
./run_tests.sh tests/ --maxfail=3

# Run tests with a specific marker
./run_tests.sh tests/ -m api

# MCP server tests against Azure
./run_tests.sh --mcp --remote

# Coverage for SRE server only
./run_tests.sh --coverage --mcp-server sre
```

---

## Test File Index

| File | Category | What it tests |
|------|----------|---------------|
| `test_health_endpoints.py` | integration, api | `/health`, `/api/health`, `/api/status`, `/api/info` platform probes |
| `test_inventory_endpoints.py` | integration, api, inventory | Software and OS inventory CRUD endpoints |
| `test_eol_search_endpoints.py` | integration, api, eol | EOL risk analysis and version lookup endpoints |
| `test_cache_endpoints.py` | integration, api, cache | L1 cache CRUD and statistics endpoints |
| `test_cache_advanced_endpoints.py` | integration, api, cache | Bulk eviction, warm-up, and maintenance workflows |
| `test_alert_endpoints.py` | integration, api, alerts | Alert config, threshold management, SMTP validation |
| `test_agent_endpoints.py` | integration, api | Agent lifecycle, health, and configuration endpoints |
| `test_cosmos_endpoints.py` | integration, api | Cosmos DB cache write/read/invalidation endpoints |
| `test_communication_endpoints.py` | integration, api | Email notification history and channel endpoints |
| `test_ui_endpoints.py` | integration, ui | HTML routes: `/`, `/azure-mcp`, `/azure-ai-sre`, `/inventory-assistant`, CVE views |
| `test_cve_mcp_server.py` | unit | CVE MCP search, scan, patch lookup, and remediation trigger flows |
| `test_cve_patch_mapper.py` | unit | KB-to-CVE mapping and patch recommendation behavior |
| `test_cve_inventory_sync.py` | unit | Inventory-driven CVE sync and OS identity matching |
| `test_azure_mcp_endpoints.py` | integration, api, mcp_azure | Azure MCP REST surfaces |
| `test_inventory_asst_endpoints.py` | integration, api, inventory_asst | Agent Framework inventory assistant orchestration |
| `test_mcp_orchestrator.py` | unit, mcp | `MCPOrchestratorAgent` — dependency injection, tool dispatch, `aclose` |
| `test_mcp_orchestrator_enhancements.py` | unit, mcp | *(skipped)* Planned CircuitBreaker + ToolResultCache features |
| `test_eol_orchestrator.py` | unit, eol | `EOLOrchestratorAgent` — injection, Cosmos cache hit, cleanup lifecycle |
| `test_sre_mcp_tools.py` | unit, mcp_sre | All 24 SRE MCP tool functions with mocked Azure SDK |
| `test_inventory_mcp_tools.py` | unit, mcp_inventory | All 7 Inventory MCP tool functions with mocked Log Analytics |
| `test_sre_orchestrator_inventory.py` | unit, mcp_sre | SRE orchestrator inventory sub-flows |
| `test_sre_agent_enhancements.py` | unit | `SREResponseFormatter`, `SREInteractionHandler`, `SRECacheManager` |
| `test_sre_user_interactions.py` | unit | SRE user interaction flows and follow-up handling |
| `test_resource_inventory_integration.py` | integration | `ResourceInventoryCache` integration with Cosmos mock |
| `cache/test_resource_inventory_cache.py` | unit, cache | `ResourceInventoryCache` L1/L2 hit/miss, TTL, eviction, batch ops |
| `services/test_cve_alert_history_manager.py` | unit, services | CVE alert history state transitions and repository-facing manager behavior |
| `utils/test_nvd_client.py` | unit, utils | NVD client request/response normalization |
| `utils/test_vendor_feed_client.py` | unit, utils | Vendor feed client parsing and normalization |
| `utils/test_repository_state.py` | unit, utils | Repository initialization and readiness helpers |
| `test_cosmos_query_optimization.py` | integration | Cosmos query builders, QuerySpec, indexing policy, end-to-end pipeline |
| `test_resource_discovery_engine.py` | unit | Azure Resource Graph discovery engine |
| `test_inventory_feature_flags.py` | unit | Inventory feature flag evaluation and rollout logic |
| `test_inventory_metrics.py` | unit | Inventory metrics aggregation and reporting |
| `test_e2e_inventory.py` | integration | End-to-end inventory fetch → cache → API response |
| `test_nodejs_agent.py` | unit, eol | Node.js EOL date lookup and version matching |
| `test_redhat_agent.py` | unit, eol | Red Hat Enterprise Linux EOL lifecycle agent |
| `test_ubuntu_agent_releases.py` | unit, eol | Ubuntu LTS release and EOL date parsing |
| `test_microsoft_agent_windows.py` | unit, eol | Windows client OS EOL agent |
| `test_microsoft_agent_windows_server.py` | unit, eol | Windows Server EOL agent |
| `test_microsoft_agent_sql_server.py` | unit, eol | SQL Server EOL agent |
| `test_oracle_agent.py` | unit, eol | Oracle JRE/JDK EOL agent |
| `test_php_agent.py` | unit, eol | PHP EOL agent |
| `test_postgresql_agent.py` | unit, eol | PostgreSQL EOL agent |

**Non-test Python files:**

| File | Purpose |
|------|---------|
| `conftest.py` | Shared fixtures and marker registration |
| `mock_data.py` | `MockDataGenerator` — deterministic mock inventory data |
| `mock_agents.py` | `MockSoftwareInventoryAgent`, `MockOSInventoryAgent` — drop-in agent fakes |
| `run_tests.sh` | Primary test runner with all flag handling |
| `run_comprehensive_tests.py` | Legacy category-based runner (no pytest) |

---

## Key Fixtures

Defined in `conftest.py`. See [TESTING_GUIDELINES.md §3](TESTING_GUIDELINES.md#3-available-fixtures)
for the full table.

| Fixture | Scope | Use for |
|---------|-------|---------|
| `client` | function | All API endpoint tests — fresh `AsyncClient` per test |
| `mock_data` | session | Generating deterministic mock inventory/OS/EOL data |
| `test_software_name` | function | Tests that take a software name query param |
| `test_software_version` | function | Tests that take a version query param |
| `test_alert_config` | function | Alert endpoint tests — full config dict with SMTP disabled |

---

## Configuration

### `pytest.ini` (project root)

```ini
[pytest]
testpaths = app/agentic/eol/tests
asyncio_mode = strict          # @pytest.mark.asyncio required on every async test
addopts = -v --strict-markers --tb=short
```

`--strict-markers` means **every marker you use must be declared** in `pytest.ini`
under `[markers]`. Using an undeclared marker is a collection error.

### Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `USE_MOCK_DATA` | `true` | `true` → ASGI transport + mock agents; `false` → live HTTP |
| `TESTING` | `true` | Signals app to skip startup tasks that need Azure |
| `BASE_URL` | `http://localhost:8000` | Override the base URL for the `client` fixture |
| `MOCK_NUM_COMPUTERS` | `50` | Number of computers generated by `MockDataGenerator` |
| `LOG_LEVEL` | *(app default)* | Set to `DEBUG` for verbose output (set by `--debug` flag) |

### Declared markers (from `pytest.ini`)

```
unit            integration     api             inventory_asst
ui              slow            cache           eol
inventory       alerts          asyncio         azure
mcp             mcp_sre         mcp_inventory   mcp_monitor
mcp_os_eol      mcp_azure_cli   mcp_azure       remote
```

### Suppressed warnings

The following deprecation warnings are silenced in `pytest.ini` to reduce noise
from upstream libraries (Pydantic v1 validators, `datetime.utcnow()`,
`TemplateResponse` signature):

```ini
filterwarnings =
    ignore:datetime\.datetime\.utcnow\(\) is deprecated:DeprecationWarning
    ignore:Pydantic V1 style `@validator`:DeprecationWarning
    ...
```

---

## See Also

- **[TESTING_GUIDELINES.md](TESTING_GUIDELINES.md)** — comprehensive guide:
  async patterns, mock strategies, MCP/orchestrator testing patterns, CI checklist,
  common pitfalls

---

## Troubleshooting

### "Virtual environment not found"

```
❌ Virtual environment not found at: .../.venv
```

Create the venv from the project root:

```bash
python -m venv /path/to/gcc-demo/.venv
source /path/to/gcc-demo/.venv/bin/activate
pip install -r app/agentic/eol/requirements.txt
```

---

### "ModuleNotFoundError: No module named 'utils'"

You are running pytest from the wrong directory. Always run from the `eol/`
directory or use `run_tests.sh` (which `cd`s to the right place automatically):

```bash
cd app/agentic/eol
pytest tests/ -v
# or
cd app/agentic/eol/tests && ./run_tests.sh
```

---

### "PytestUnraisableExceptionWarning" or test silently passes without assertions

You are missing `@pytest.mark.asyncio` on an async test under `asyncio_mode=strict`.
The coroutine object is created but never awaited. Add the decorator (or
`pytestmark = [pytest.mark.asyncio]` at module level).

---

### "Marker X is not registered" (collection error)

`--strict-markers` is set. You used a marker that is not in `pytest.ini`.
Either add it to the `[markers]` section or fix the typo in your decorator.

---

### Tests pass in isolation but fail when run together

You have a shared-state ordering dependency. Common sources:

1. Module-level `mock_generator` singleton — use `MockDataGenerator(seed=42)` for
   a fresh instance.
2. Module-level audit trail or cache list in an MCP server — reset with
   `monkeypatch.setattr(...)` in an `autouse` fixture.
3. A `scope="session"` fixture whose state is mutated by an earlier test.

Run `pytest --randomly-seed=last` to reproduce the same order, then narrow down
with `pytest -x` to find the culprit.

---

### Coverage report not generated

Requires `pytest-cov`:

```bash
pip install pytest-cov
./run_tests.sh --coverage
open htmlcov/index.html
```

---

### Parallel tests failing randomly (`--parallel N`)

Requires `pytest-xdist`:

```bash
pip install pytest-xdist
```

Parallel execution exposes shared-state bugs. Fix the root cause (see ordering
issue above) rather than running without parallelism.

---

### "AsyncClient" transport error in remote mode

When running `--remote`, the `client` fixture switches to a direct HTTP client.
If the Azure deployment is unreachable or the URL has changed, update
`run_tests.sh`:

```bash
# Current remote URL is set in run_tests.sh:
TEST_URL="https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"

# Override for a different environment:
./run_tests.sh --url https://my-staging-env.azurecontainerapps.io
```
