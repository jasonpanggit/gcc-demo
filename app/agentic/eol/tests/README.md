# Local Testing with Mock Data

This directory contains a complete mock testing environment that allows you to test the EOL application **without any Azure dependencies**. Perfect for local development, CI/CD, and validation of refactored code.

## 📁 Files

| File | Purpose |
|------|---------|
| `mock_data.py` | Generates realistic mock data matching Azure Log Analytics formats |
| `mock_agents.py` | Mock versions of inventory agents that return generated data |
| `test_config.py` | Configuration for test mode and mock data parameters |
| `run_tests.py` | Automated test runner for all API endpoints |

## 🚀 Quick Start

### Option 1: Run Automated Tests

```bash
# From the eol directory
cd app/agentic/eol

# Run all API tests with mock data
python -m tests.run_tests
```

Expected output:
```
🧪 API TEST SUITE - Mock Data Mode
====================================================================================================
Test Config: 25 computers, Mock Mode: True
Started: 2025-10-15T10:30:00.000000
----------------------------------------------------------------------------------------------------
Status | Test Name                                | Time     | Details
----------------------------------------------------------------------------------------------------
✅ PASS | GET /api/health                          |  0.103s | All agents healthy
✅ PASS | GET /api/inventory (software)            |  0.156s | 312 items
✅ PASS | GET /api/inventory?filter=Python         |  0.142s | 18 items
✅ PASS | GET /api/inventory/summary               |  0.187s | 87 software, 25 computers
✅ PASS | GET /api/inventory/raw/os                |  0.124s | 25 items
✅ PASS | GET /api/inventory/os/summary            |  0.139s | 25 computers (Win: 15, Linux: 10)
✅ PASS | POST /api/cache/clear                    |  0.098s | Software & OS caches cleared
----------------------------------------------------------------------------------------------------

📊 TEST SUMMARY
  Total Tests: 7
  ✅ Passed: 7
  ❌ Failed: 0
  ⏱️  Total Duration: 0.949s
  📅 Completed: 2025-10-15T10:30:00.949000

🎉 All tests passed!
```

### Option 2: Interactive Testing

```bash
# Test mock data generation
python -m tests.mock_data

# Test mock agents
python -m tests.mock_agents

# Check test configuration
python -m tests.test_config
```

## 🔧 Configuration

### Environment Variables

Set these before running tests to customize behavior:

```bash
# Enable/disable mock mode
export USE_MOCK_DATA=true

# Number of mock computers to generate
export MOCK_NUM_COMPUTERS=50

# Windows to Linux ratio (0.0 = all Linux, 1.0 = all Windows)
export MOCK_WINDOWS_RATIO=0.6

# Software per computer range
export MOCK_SOFTWARE_MIN=5
export MOCK_SOFTWARE_MAX=20

# Test cache settings
export TEST_CACHE_ENABLED=false
export TEST_CACHE_TTL=300

# Logging level
export TEST_LOG_LEVEL=INFO

# Random seed for reproducible data
export MOCK_DATA_SEED=42
```

### Programmatic Configuration

```python
from tests.test_config import enable_mock_mode, disable_mock_mode

# Enable mock mode with custom settings
enable_mock_mode(
    num_computers=100,
    windows_ratio=0.7,
    cache_enabled=True
)

# Disable mock mode (use real Azure data)
disable_mock_mode()
```

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
