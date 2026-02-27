# Testing Strategy

Comprehensive testing approach for the GCC Demo platform.

---

## Overview

The GCC Demo platform uses **pytest** for Python testing with support for:
- Unit tests (isolated component testing)
- Integration tests (API endpoint testing)
- Remote tests (Azure service integration)
- MCP server tool tests
- End-to-end (E2E) tests
- Async testing with `pytest-asyncio`

---

## Test Configuration

### Pytest Configuration (`pytest.ini`)

**Location:** Root directory (`gcc-demo/pytest.ini`)

**Key Settings:**
```ini
[pytest]
testpaths = app/agentic/eol/tests
pythonpath = app/agentic/eol
asyncio_mode = strict
console_output_style = progress
```

**Options:**
- `-v` - Verbose output
- `--strict-markers` - Enforce marker registration
- `--tb=short` - Short traceback format
- `--asyncio-mode=strict` - Strict async test validation

---

## Test Markers

### Available Markers

| Marker | Purpose | Usage |
|--------|---------|-------|
| `unit` | Pure unit tests (no Azure dependencies) | `@pytest.mark.unit` |
| `integration` | Integration tests for APIs | `@pytest.mark.integration` |
| `api` | API endpoint tests | `@pytest.mark.api` |
| `remote` | Tests requiring Azure access | `@pytest.mark.remote` |
| `azure` | Tests requiring Azure services | `@pytest.mark.azure` |
| `mcp` | MCP-related tests (all servers) | `@pytest.mark.mcp` |
| `mcp_sre` | SRE MCP server tests | `@pytest.mark.mcp_sre` |
| `mcp_inventory` | Inventory MCP server tests | `@pytest.mark.mcp_inventory` |
| `mcp_monitor` | Monitor MCP server tests | `@pytest.mark.mcp_monitor` |
| `mcp_os_eol` | OS EOL MCP server tests | `@pytest.mark.mcp_os_eol` |
| `mcp_azure_cli` | Azure CLI Executor tests | `@pytest.mark.mcp_azure_cli` |
| `mcp_azure` | Azure MCP (@azure/mcp) tests | `@pytest.mark.mcp_azure` |
| `slow` | Tests taking > 1 second | `@pytest.mark.slow` |
| `cache` | Caching functionality tests | `@pytest.mark.cache` |
| `eol` | EOL analysis functionality | `@pytest.mark.eol` |
| `inventory` | Inventory endpoints | `@pytest.mark.inventory` |
| `alerts` | Alert management | `@pytest.mark.alerts` |
| `inventory_asst` | Agent Framework tests | `@pytest.mark.inventory_asst` |
| `ui` | UI/HTML endpoint tests | `@pytest.mark.ui` |
| `e2e` | End-to-end integration tests | `@pytest.mark.e2e` |
| `stub` | Stub/placeholder tests | `@pytest.mark.stub` |

**Usage Example:**
```python
import pytest

@pytest.mark.unit
@pytest.mark.cache
async def test_eol_cache():
    """Test EOL cache functionality."""
    pass

@pytest.mark.remote
@pytest.mark.azure
async def test_cosmos_integration():
    """Test Cosmos DB integration (requires Azure access)."""
    pass
```

---

## Test Files

### Test Suite Inventory (16 Test Files)

```
app/agentic/eol/tests/
├── test_router.py                      # Router tests
├── test_sre_gateway.py                 # SRE gateway classification
├── test_sre_tool_registry.py           # Tool registry tests
├── test_sre_incident_memory.py         # Incident memory tests
├── test_tool_embedder.py               # Tool embedding tests
├── test_tool_retriever.py              # Tool retrieval tests
├── test_tool_manifest_index.py         # Manifest index tests
├── test_unified_domain_registry.py     # Domain registry tests
├── test_pipeline_routing.py            # Pipeline routing tests
├── test_resource_inventory_service.py  # Inventory service tests
├── test_cli_executor_safety.py         # CLI executor safety
├── test_security_compliance_agent.py   # Security compliance tests
├── test_remote_sre.py                  # Remote SRE tests
├── test_remote_tool_selection.py       # Remote tool selection
├── test_phase6_pipeline.py             # Phase 6 pipeline tests
└── test_phase7_default.py              # Phase 7 default tests
```

### Test Categories

| Category | Files | Purpose |
|----------|-------|---------|
| **Unit Tests** | 11 | Component isolation testing |
| **Integration Tests** | 2 | Remote API testing |
| **Phase Tests** | 2 | Feature phase validation |
| **Security Tests** | 1 | Security compliance validation |
| **Total** | 16 | |

---

## Test Execution

### Running Tests

#### All Tests
```bash
cd app/agentic/eol/tests
pytest
```

#### Unit Tests Only (No Azure Dependencies)
```bash
pytest -m unit
```

#### Integration Tests
```bash
pytest -m integration
```

#### Remote Tests (Requires Azure Access)
```bash
pytest -m remote
```

#### MCP Server Tests
```bash
# All MCP tests
pytest -m mcp

# Specific MCP server
pytest -m mcp_sre
pytest -m mcp_inventory
pytest -m mcp_monitor
pytest -m mcp_os_eol
pytest -m mcp_azure_cli
pytest -m mcp_azure
```

#### Slow Tests
```bash
pytest -m slow
```

#### Specific Test File
```bash
pytest test_sre_gateway.py
```

#### Specific Test Function
```bash
pytest test_sre_gateway.py::test_classification
```

---

### Test Script (Legacy)

**Note:** The repository previously had `run_tests.sh`, but it's no longer present. Use `pytest` directly.

**Typical Run Script Pattern:**
```bash
#!/bin/bash
# Example run_tests.sh pattern

MODE="$1"

case "$MODE" in
    --remote)
        pytest -m remote
        ;;
    --mcp-server)
        SERVER="$2"
        pytest -m "mcp_${SERVER}"
        ;;
    --coverage)
        pytest --cov=. --cov-report=html --cov-report=term
        ;;
    *)
        pytest
        ;;
esac
```

---

## Coverage

### Coverage Configuration

**Configuration Location:** `pytest.ini`

```ini
[coverage:run]
source = .
omit =
    tests/*
    */site-packages/*
    */dist-packages/*

[coverage:report]
precision = 2
show_missing = True
skip_covered = False

[coverage:html]
directory = htmlcov
```

### Running with Coverage

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```

### Coverage Metrics

**Target Coverage:**
- Overall: 80%+
- Critical paths: 90%+
- Utils: 85%+
- Agents: 75%+

**Current Coverage Areas:**
- ✅ Response models (high coverage)
- ✅ Caching logic (high coverage)
- ✅ MCP clients (moderate coverage)
- ⚠️ Agents (variable coverage)
- ⚠️ Orchestrators (needs improvement)

---

## Testing Patterns

### Unit Test Pattern

```python
import pytest
from utils.response_models import StandardResponse

@pytest.mark.unit
def test_standard_response_success():
    """Test StandardResponse success format."""
    response = StandardResponse.success_response(
        data={"key": "value"},
        cached=True
    )
    assert response.success is True
    assert response.data == {"key": "value"}
    assert response.cached is True
    assert response.error is None
```

### Async Test Pattern

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.unit
async def test_eol_cache():
    """Test EOL cache operations."""
    from utils.eol_cache import eol_cache

    # Set value
    eol_cache.set("test_key", {"data": "value"})

    # Get value
    result = eol_cache.get("test_key")
    assert result == {"data": "value"}
```

### Integration Test Pattern

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.mark.integration
@pytest.mark.api
def test_health_endpoint():
    """Test /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

### Remote Test Pattern

```python
import pytest
import os

@pytest.mark.remote
@pytest.mark.azure
@pytest.mark.skipif(
    not os.getenv("AZURE_COSMOS_DB_ENDPOINT"),
    reason="Cosmos DB not configured"
)
async def test_cosmos_cache():
    """Test Cosmos DB cache (requires Azure)."""
    from utils.cosmos_cache import base_cosmos

    if not base_cosmos.is_available():
        pytest.skip("Cosmos DB not available")

    # Test cache operations
    await base_cosmos.store_response("test_key", {"data": "value"})
    result = await base_cosmos.get_response("test_key")
    assert result == {"data": "value"}
```

### MCP Server Test Pattern

```python
import pytest

@pytest.mark.mcp
@pytest.mark.mcp_sre
async def test_sre_mcp_tools():
    """Test SRE MCP server tools."""
    from utils.sre_mcp_client import sre_mcp_client

    # Initialize client
    await sre_mcp_client.initialize()

    # List tools
    tools = await sre_mcp_client.list_tools()
    assert len(tools) > 0

    # Call tool
    result = await sre_mcp_client.call_tool("tool_name", {"arg": "value"})
    assert result["success"] is True
```

---

## Test Data & Fixtures

### Pytest Fixtures

**Common Fixtures:**
```python
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def test_client():
    """FastAPI test client fixture."""
    return TestClient(app)

@pytest.fixture
def mock_config():
    """Mock configuration fixture."""
    from utils import config
    return config

@pytest.fixture
async def cosmos_client():
    """Cosmos DB client fixture."""
    from utils.cosmos_cache import base_cosmos
    if not base_cosmos.is_available():
        pytest.skip("Cosmos DB not available")
    yield base_cosmos
```

### Test Data Location

```
utils/data/
└── (Test data files)
```

---

## Mock Mode Testing

### Running Without Azure Dependencies

**Mock Script Pattern:**
```bash
#!/bin/bash
# run_mock.sh

export DEBUG_MODE=true
export AZURE_COSMOS_DB_ENDPOINT=""
export LOG_ANALYTICS_WORKSPACE_ID="mock-workspace"

uvicorn main:app --reload --port 8000
```

**Usage:**
```bash
cd app/agentic/eol
./run_mock.sh
```

**Mock Mode Behavior:**
- Cosmos DB disabled (L1 cache only)
- Log Analytics queries return empty results
- MCP servers skip Azure SDK calls
- EOL agents use cached or placeholder data

---

## CI/CD Integration

### GitHub Actions Pattern

**Workflow Example:**
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          cd app/agentic/eol
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          cd app/agentic/eol
          pytest -m unit --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Test Naming Conventions

### File Names
- Pattern: `test_<module>.py`
- Example: `test_sre_gateway.py`, `test_router.py`

### Test Function Names
- Pattern: `test_<functionality>`
- Example: `test_classification()`, `test_cache_hit()`

### Test Class Names
- Pattern: `Test<Feature>`
- Example: `TestSREGateway`, `TestCaching`

---

## Testing Best Practices

### 1. Isolation
- Unit tests MUST NOT depend on external services
- Use mocks/stubs for external dependencies
- Mark tests appropriately (`unit`, `integration`, `remote`)

### 2. Async Testing
- Use `@pytest.mark.asyncio` for async tests
- Set `asyncio_mode = strict` in pytest.ini
- Use `await` for async operations

### 3. Markers
- Always mark tests with appropriate markers
- Use multiple markers when applicable
- Example: `@pytest.mark.unit`, `@pytest.mark.cache`

### 4. Skipping Tests
```python
@pytest.mark.skipif(
    not os.getenv("AZURE_COSMOS_DB_ENDPOINT"),
    reason="Cosmos DB not configured"
)
async def test_cosmos():
    pass
```

### 5. Parameterized Tests
```python
@pytest.mark.parametrize("input,expected", [
    ("Windows Server 2025", "2025-10-14"),
    ("Ubuntu 24.04", "2029-04-01"),
])
async def test_eol_dates(input, expected):
    result = await agent.get_eol_data(input)
    assert result["eol_date"] == expected
```

### 6. Fixtures Over Globals
```python
# Good
@pytest.fixture
def config():
    return ConfigManager()

def test_config(config):
    assert config.app.version

# Bad
config = ConfigManager()
def test_config():
    assert config.app.version
```

---

## Test Maintenance

### When to Add Tests

1. **New Features:**
   - Add unit tests for new utilities
   - Add integration tests for new API endpoints
   - Add MCP tests for new MCP servers

2. **Bug Fixes:**
   - Add regression test for the bug
   - Verify fix with test pass

3. **Refactoring:**
   - Ensure existing tests pass
   - Add tests for new code paths

### Test Review Checklist

- [ ] Tests are properly marked
- [ ] Tests are isolated (unit tests don't call Azure)
- [ ] Async tests use `@pytest.mark.asyncio`
- [ ] Tests have clear docstrings
- [ ] Tests follow naming conventions
- [ ] Mock data is used (no hardcoded credentials)
- [ ] Tests are repeatable (no flakiness)

---

## Common Test Scenarios

### 1. API Endpoint Test
```python
@pytest.mark.api
def test_eol_endpoint(test_client):
    response = test_client.get("/api/eol/status?software=Windows+Server+2025")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

### 2. Cache Test
```python
@pytest.mark.unit
@pytest.mark.cache
def test_cache_hit():
    from utils.eol_cache import eol_cache
    eol_cache.set("key", "value")
    assert eol_cache.get("key") == "value"
```

### 3. Agent Test
```python
@pytest.mark.unit
@pytest.mark.eol
async def test_microsoft_agent():
    from agents.microsoft_agent import MicrosoftEOLAgent
    agent = MicrosoftEOLAgent()
    result = await agent.get_eol_data("Windows Server 2025", "2025")
    assert result["success"] is True
```

### 4. MCP Tool Test
```python
@pytest.mark.mcp
@pytest.mark.mcp_inventory
async def test_inventory_tools():
    from utils.inventory_mcp_client import inventory_mcp_client
    await inventory_mcp_client.initialize()
    result = await inventory_mcp_client.call_tool("law_get_os_inventory", {})
    assert result["success"] is True
```

---

## Troubleshooting

### Common Issues

**1. Import Errors:**
```
ModuleNotFoundError: No module named 'utils'
```
**Solution:** Ensure `pythonpath = app/agentic/eol` in `pytest.ini`

**2. Async Test Not Running:**
```
RuntimeWarning: coroutine 'test_async' was never awaited
```
**Solution:** Add `@pytest.mark.asyncio` decorator

**3. Marker Not Recognized:**
```
PytestUnknownMarkWarning: Unknown pytest.mark
```
**Solution:** Add marker to `pytest.ini` markers section

**4. Cosmos DB Tests Failing:**
```
Cosmos DB not available
```
**Solution:** Set `AZURE_COSMOS_DB_ENDPOINT` or skip with `pytest -m "not azure"`

---

## Test Coverage Gaps

### Current Gaps (Needs Improvement)

1. **Orchestrators:**
   - `eol_orchestrator.py` - Needs more unit tests
   - `sre_orchestrator.py` - Needs workflow tests

2. **Complex Agents:**
   - Multi-step agent flows
   - Agent error handling paths

3. **MCP Composite Client:**
   - Tool aggregation logic
   - Fallback behavior

4. **UI Templates:**
   - HTML rendering tests
   - JavaScript functionality tests

### Recommended Additions

- [ ] Add E2E tests for full workflows
- [ ] Add load tests for performance validation
- [ ] Add security tests for input validation
- [ ] Add contract tests for API endpoints
- [ ] Add visual regression tests for UI

---

## Performance Testing

### Load Testing Pattern

**Tool:** `locust` or `pytest-benchmark`

```python
import pytest

@pytest.mark.slow
@pytest.mark.performance
def test_eol_endpoint_performance(benchmark):
    def call_endpoint():
        response = client.get("/api/eol/status?software=Windows")
        return response.status_code

    result = benchmark(call_endpoint)
    assert result == 200
```

---

## Security Testing

### CLI Executor Safety Tests

**File:** `test_cli_executor_safety.py`

**Purpose:** Validate CLI command safety

**Tests:**
- Command injection prevention
- Allowlist validation
- Privilege escalation prevention

---

**Last Updated:** 2026-02-27
**Source:** `pytest.ini` + test file analysis
**Maintainer:** Development Team
