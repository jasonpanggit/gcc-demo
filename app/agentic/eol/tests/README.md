# Comprehensive Test Suite

This directory contains a comprehensive pytest-based test suite for the EOL Agentic app with **122 automated tests** (including async coverage and orchestrator unit tests). The suite runs entirely against mock data, so no Azure resources are required.

## 📁 Test Infrastructure

| File | Purpose |
|------|---------|
| `conftest.py` | Pytest configuration, fixtures (AsyncClient, mock data) |
| `run_comprehensive_tests.py` | Intelligent test runner with category execution |
| `mock_data.py` | Generates realistic mock data (500+ software items, 50 OS) |
| `mock_agents.py` | Mock inventory agents for testing |
| `test_*.py` | 9 test modules covering all endpoint categories |
| `TEST_RESULTS_SUMMARY.md` | Detailed test results and analysis |

## 🧪 Test Modules

| Module | Focus |
|--------|-------|
| `test_health_endpoints.py` | Platform and dependency health probes |
| `test_inventory_endpoints.py` | Software & OS inventory APIs |
| `test_eol_search_endpoints.py` | EOL risk analysis endpoints |
| `test_cache_endpoints.py` | Cache CRUD and statistics APIs |
| `test_cache_advanced_endpoints.py` | Advanced cache maintenance workflows |
| `test_alert_endpoints.py` | Alert configuration & SMTP validation |
| `test_agent_endpoints.py` | Agent lifecycle and configuration APIs |
| `test_cosmos_endpoints.py` | Cosmos DB caching operations |
| `test_communication_endpoints.py` | Email and notification history APIs |
| `test_inventory_asst_endpoints.py` | Agent Framework inventory assistant orchestration APIs |
| `test_azure_mcp_endpoints.py` | Azure MCP REST surfaces |
| `test_mcp_orchestrator.py` | Dependency-injected MCP orchestrator behaviors |
| `test_eol_orchestrator.py` | EOL orchestrator dependency injection & cleanup |
| `test_ui_endpoints.py` | HTML routes and UI health |

## 🚀 Quick Start

### Run All Tests

```bash
# From the eol directory
cd app/agentic/eol

# Test local server with mock data (default)
python3 tests/run_comprehensive_tests.py

# Test remote Azure server with live data
python3 tests/run_comprehensive_tests.py --remote

# Or using environment variable
USE_MOCK_DATA=false python3 tests/run_comprehensive_tests.py

# Test with custom URL
python3 tests/run_comprehensive_tests.py --url http://localhost:5000
```

Expected output (Local/Mock):
```
================================================================================
EOL MULTI-AGENT APP - COMPREHENSIVE TEST SUITE
================================================================================
Start Time: 2025-10-15T07:54:23.580165
Test Mode: LOCAL (Mock Data)
Base URL: http://localhost:8000
Mock Data: ENABLED
--------------------------------------------------------------------------------

📋 Testing: Health & Status Endpoints
   Module: test_health_endpoints.py
   ------------------------------------------------------------
   ✅ test_root_endpoint
   ✅ test_health_endpoint
   ✅ test_api_health_endpoint
   ✅ test_api_status_endpoint
   ✅ test_api_info_endpoint

📋 Testing: Cache Management Endpoints
   Module: test_cache_endpoints.py
   ------------------------------------------------------------
   ✅ test_get_cache_status
   ✅ test_clear_cache
   ...

================================================================================
TEST SUMMARY
================================================================================
✅ Health & Status Endpoints: PASSED
✅ Inventory Endpoints: PASSED
✅ Cache Management Endpoints: PASSED
...
--------------------------------------------------------------------------------
Total Categories: 9
Passed: 9
Failed: 0
Success Rate: 100.0%
End Time: 2025-10-15T07:54:31.924670
================================================================================
```

### Run Specific Category

```bash
# Test only cache endpoints (local)
python3 tests/run_comprehensive_tests.py --category cache

# Test only inventory endpoints (remote Azure server)
python3 tests/run_comprehensive_tests.py --category inventory --remote

# Quick smoke test (health endpoints only)
python3 tests/run_comprehensive_tests.py --quick
```

### Test Modes

The test suite supports two modes:

**1. Local Mode (Mock Data)** - Default
- Base URL: `http://localhost:8000`
- Uses mock data (500+ software items, 50 OS entries)
- No Azure dependencies required
- Fast execution
- Perfect for development and CI/CD

**2. Remote Mode (Live Data)**
- Base URL: `https://app-eol-agentic-gcc-demo.azurewebsites.net`
- Tests against live Azure App Service
- Uses real Azure data
- Validates production deployment
- Requires network access

```bash
# Enable remote mode
python3 tests/run_comprehensive_tests.py --remote

# Or via environment variable
USE_MOCK_DATA=false python3 tests/run_comprehensive_tests.py

# Custom URL (e.g., staging environment)
BASE_URL=https://staging.example.com python3 tests/run_comprehensive_tests.py
```

### Run with Coverage

```bash
# Generate coverage report
python3 tests/run_comprehensive_tests.py --coverage

# View coverage report
open htmlcov/index.html
```

### Using pytest directly

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_cache_endpoints.py -v

# Run tests with specific marker
pytest -m cache -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## 🔧 Configuration

### Environment Variables

Set these before running tests to customize behavior:

```bash
# Enable mock mode (required for tests)
export USE_MOCK_DATA=true
export TESTING=true

# Number of mock computers to generate
export MOCK_NUM_COMPUTERS=50

# Windows to Linux ratio (0.0 = all Linux, 1.0 = all Windows)
export MOCK_WINDOWS_RATIO=0.6

# Software per computer range
export MOCK_SOFTWARE_MIN=5
export MOCK_SOFTWARE_MAX=20
```

## 🔍 Test Markers

Tests are tagged with markers for selective execution:

```bash
# Run only API tests
pytest -m api

# Run only UI tests
pytest -m ui

# Run only cache-related tests
pytest -m cache

# Run only fast tests (exclude slow)
pytest -m "not slow"

# Combine markers
pytest -m "api and cache"
```

Available markers:
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.ui` - UI/HTML route tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.cache` - Cache functionality tests
- `@pytest.mark.eol` - EOL analysis tests
- `@pytest.mark.inventory` - Inventory tests
- `@pytest.mark.alerts` - Alert management tests
- `@pytest.mark.slow` - Tests taking >1 second

## 📊 Mock Data Details

### Software Inventory Data

Generated data includes:
- **50 computers** by default (configurable)
- **5-20 software items** per computer (configurable)
- Realistic software names: Python, Node.js, PostgreSQL, SQL Server, etc.
- Proper version numbers: "3.11.5", "20.10.0", "16.1", etc.
- Correct publishers: Microsoft, Oracle, Python Foundation, etc.
- Software types: Application, Database, Server Application, Development Tool
- Timestamps and metadata

Example item:
```json
{
  "computer": "WEBSRV-EUS-042",
  "name": "Python",
  "version": "3.11.5",
  "publisher": "Python Software Foundation",
  "software_type": "Development Tool",
  "install_date": null,
  "last_seen": "2025-10-15T08:30:00.000000",
  "computer_count": 1,
  "source": "log_analytics_configurationdata"
}
```

### OS Inventory Data

Generated data includes:
- Same computers as software inventory
- **60% Windows, 40% Linux** by default (configurable)
- Realistic OS versions: Windows Server 2022, Ubuntu 22.04, RHEL 9.3, etc.
- Computer types: Azure VM, Arc-enabled Server
- Resource IDs matching Azure format
- Heartbeat timestamps

Example item:
```json
{
  "computer_name": "WEBSRV-EUS-042",
  "os_name": "Ubuntu",
  "os_version": "22.04",
  "os_type": "Linux",
  "vendor": "Canonical Ltd.",
  "computer_environment": "Azure",
  "computer_type": "Azure VM",
  "resource_id": "/subscriptions/sub-abc123/resourceGroups/rg-websrv/providers/Microsoft.Compute/virtualMachines/WEBSRV-EUS-042",
  "last_heartbeat": "2025-10-15T10:28:00.000000",
  "source": "log_analytics_heartbeat"
}
```

### EOL Date Data

Mock EOL dates for common software:
- Python: 2.7 (EOL), 3.8 (2024), 3.9 (2025), 3.10 (2026), 3.11 (2027)
- Node.js: 14 (EOL), 16 (EOL), 18 (2025), 20 (2026)
- PostgreSQL: 9.6-11 (EOL), 12 (2024), 13-16 (2025-2028)
- PHP: 5.6 (EOL), 7.4 (EOL), 8.1 (2024), 8.2 (2025)
- Windows Server: 2012 R2 (EOL), 2016-2022 (2027-2031)
- Ubuntu: 18.04-22.04 LTS (2028-2032)

## 🧪 Testing Scenarios

### 1. Basic Functionality Test

```bash
python -m tests.run_tests
```

Validates:
- All API endpoints return data
- Response formats match expected structure
- No Python errors or exceptions
- Cache operations work

### 2. Filtered Query Test

```python
from tests.mock_agents import get_software_inventory_agent
import asyncio

async def test_filter():
    agent = get_software_inventory_agent()
    result = await agent.get_software_inventory(software_filter="Python")
    print(f"Found {result['count']} Python installations")
    for item in result['data']:
        print(f"  - {item['computer']}: {item['name']} {item['version']}")

asyncio.run(test_filter())
```

### 3. Large Dataset Test

```python
from tests.test_config import enable_mock_mode
from tests.mock_agents import get_software_inventory_agent
import asyncio

async def test_large_dataset():
    # Generate data for 500 computers
    enable_mock_mode(num_computers=500)
    
    agent = get_software_inventory_agent()
    result = await agent.get_software_inventory()
    print(f"Generated {result['count']} software installations across 500 computers")

asyncio.run(test_large_dataset())
```

### 4. Performance Test

```python
import asyncio
import time
from tests.mock_agents import get_software_inventory_agent, get_os_inventory_agent

async def performance_test():
    agents = {
        'software': get_software_inventory_agent(),
        'os': get_os_inventory_agent()
    }
    
    for name, agent in agents.items():
        start = time.time()
        if name == 'software':
            result = await agent.get_software_inventory()
        else:
            result = await agent.get_os_inventory()
        duration = time.time() - start
        print(f"{name}: {result['count']} items in {duration:.3f}s")

asyncio.run(performance_test())
```

## 🔄 Integration with Real Code

### Using Mock Agents in Main Application

You can integrate mock agents into `main.py` for development:

```python
# In main.py, add conditional import
import os

if os.getenv("USE_MOCK_DATA", "false").lower() == "true":
    from tests.mock_agents import get_software_inventory_agent, get_os_inventory_agent
    software_agent = get_software_inventory_agent()
    os_agent = get_os_inventory_agent()
    print("🧪 Running in MOCK MODE")
else:
    from agents.software_inventory_agent import SoftwareInventoryAgent
    from agents.os_inventory_agent import OSInventoryAgent
    software_agent = SoftwareInventoryAgent()
    os_agent = OSInventoryAgent()
```

Then run:
```bash
USE_MOCK_DATA=true python main.py
```

## 📝 Writing New Tests

### Add Test to run_tests.py

```python
async def test_new_feature(self):
    """Test description"""
    test_start = datetime.utcnow()
    try:
        # Your test logic here
        agent = get_software_inventory_agent()
        result = await agent.some_new_method()
        
        # Assertions
        assert result['success'], "Feature failed"
        assert 'data' in result, "Missing data"
        
        duration = (datetime.utcnow() - test_start).total_seconds()
        self.log_test("Test Name", True, duration, "Details")
        return result
        
    except Exception as e:
        duration = (datetime.utcnow() - test_start).total_seconds()
        self.log_test("Test Name", False, duration, str(e))
        return None
```

### Add to run_all_tests()

```python
async def run_all_tests(self):
    # ... existing tests ...
    await self.test_new_feature()
```

## 🐛 Troubleshooting

### Import Errors

If you get import errors:
```bash
# Ensure you're running from the eol directory
cd app/agentic/eol

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### No Data Generated

Check configuration:
```python
from tests.test_config import test_config
print(test_config)
```

Verify mock mode is enabled:
```python
assert test_config.use_mock_data == True
```

### Tests Failing

1. **Check Python version**: Requires Python 3.8+
2. **Verify imports**: All files should be in `tests/` directory
3. **Check async**: Make sure to use `asyncio.run()` for async functions
4. **Review logs**: Set `TEST_LOG_LEVEL=DEBUG` for detailed output

## 📚 API Response Formats

All mock agents return data in the exact format expected by real agents:

### Software Inventory Response
```python
{
    "success": True,
    "data": [...],  # List of software items
    "count": 312,
    "query_params": {
        "days": 90,
        "software_filter": None,
        "limit": 10000
    },
    "from_cache": False,
    "cached_at": "2025-10-15T10:30:00.000000"
}
```

### OS Inventory Response
```python
{
    "success": True,
    "data": [...],  # List of OS items
    "count": 50,
    "query_params": {
        "days": 7,
        "limit": 10000
    },
    "from_cache": False,
    "cached_at": "2025-10-15T10:30:00.000000"
}
```

## 🎯 Use Cases

### 1. Local Development
Test API changes without Azure credentials:
```bash
USE_MOCK_DATA=true python main.py
```

### 2. CI/CD Pipeline
Run automated tests in GitHub Actions:
```yaml
- name: Run Tests
  run: |
    cd app/agentic/eol
    python -m tests.run_tests
  env:
    USE_MOCK_DATA: true
    MOCK_NUM_COMPUTERS: 25
```

### 3. Demo Environment
Generate consistent demo data:
```bash
export MOCK_DATA_SEED=42  # Same data every time
python -m tests.run_tests
```

### 4. Load Testing
Test with large datasets:
```bash
export MOCK_NUM_COMPUTERS=1000
python -m tests.run_tests
```

## ✅ Validation Checklist

Before committing code, run:

- [ ] `python -m tests.run_tests` - All tests pass
- [ ] `python -m tests.mock_data` - Data generates correctly
- [ ] `python -m tests.mock_agents` - Agents work independently
- [ ] Response formats match real API
- [ ] No Azure dependencies required
- [ ] Documentation updated

## 📖 Additional Resources

- [PHASE1_COMPLETE.md](../PHASE1_COMPLETE.md) - Refactoring summary
- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - Implementation guide
- [INDEX.md](../INDEX.md) - Complete documentation index

---

**Created**: October 15, 2025  
**Status**: ✅ Complete and tested  
**Mode**: Mock data, no Azure dependencies required
