# 🧪 Quick Start: Mock Testing Framework

## Run Tests in 30 Seconds

```bash
# 1. Navigate to the EOL directory
cd app/agentic/eol

# 2. Run all tests
python -m tests.run_tests
```

**Expected Output:**
```
🎉 All tests passed!
  Total Tests: 7
  ✅ Passed: 7
  ❌ Failed: 0
  ⏱️  Total Duration: 0.615s
```

## What Gets Tested?

| Endpoint | What It Tests |
|----------|---------------|
| `/api/health` | Agent health checks |
| `/api/inventory` | Software inventory retrieval |
| `/api/inventory?filter=Python` | Filtered queries work |
| `/api/inventory/summary` | Data aggregation |
| `/api/inventory/raw/os` | OS inventory retrieval |
| `/api/inventory/os/summary` | OS statistics |
| `/api/cache/clear` | Cache operations |

## Sample Mock Data

### Generated Automatically:
- **25 computers** (configurable)
- **300+ software installations**
- **25 OS records**
- Realistic names: `WEBSRV-EUS-042`, `DBSRV-WUS-018`
- Real software: Python 3.11.5, Node.js 20.10.0, PostgreSQL 16.1
- Real OS: Windows Server 2022, Ubuntu 22.04, RHEL 9.3

### Example Software Item:
```json
{
  "computer": "WEBSRV-EUS-042",
  "name": "Python",
  "version": "3.11.5",
  "publisher": "Python Software Foundation",
  "software_type": "Development Tool",
  "last_seen": "2025-10-15T08:30:00"
}
```

### Example OS Item:
```json
{
  "computer_name": "WEBSRV-EUS-042",
  "os_name": "Ubuntu",
  "os_version": "22.04",
  "os_type": "Linux",
  "computer_type": "Azure VM"
}
```

## Customize Test Data

```bash
# More computers
export MOCK_NUM_COMPUTERS=100
python -m tests.run_tests

# More Windows servers
export MOCK_WINDOWS_RATIO=0.8
python -m tests.run_tests

# Reproducible data
export MOCK_DATA_SEED=42
python -m tests.run_tests
```

## Use in Your Code

### Option 1: Environment Variable
```bash
USE_MOCK_DATA=true python your_script.py
```

### Option 2: Programmatic
```python
from tests.test_config import enable_mock_mode
from tests.mock_agents import get_software_inventory_agent

# Enable mock mode
enable_mock_mode(num_computers=50)

# Use mock agent
agent = get_software_inventory_agent()
result = await agent.get_software_inventory()
print(f"Got {result['count']} items")
```

## Common Commands

```bash
# Run all tests
python -m tests.run_tests

# Generate sample data
python -m tests.mock_data

# Test agents independently
python -m tests.mock_agents

# Check configuration
python -m tests.test_config
```

## Benefits

✅ **No Azure Required** - Test without credentials  
✅ **Fast** - 0.6 seconds vs 5+ seconds for real queries  
✅ **Consistent** - Same data every time (with seed)  
✅ **Scalable** - Test with 10 or 10,000 computers  
✅ **Realistic** - Data matches real Azure format  

## Troubleshooting

### Import Error?
```bash
# Make sure you're in the right directory
cd app/agentic/eol
pwd  # Should end with /app/agentic/eol
```

### No Output?
```bash
# Check Python version (need 3.8+)
python --version

# Try with python3
python3 -m tests.run_tests
```

### Tests Fail?
```bash
# Check test configuration
python -c "from tests.test_config import test_config; print(test_config)"
```

## What's Next?

After tests pass:
1. ✅ Tests validate your refactored code works
2. 🚀 Ready to integrate with real Azure data
3. 📊 Use mock data for demos and CI/CD
4. 🔍 Proceed with Phase 2 API standardization

## Full Documentation

See [tests/README.md](tests/README.md) for complete documentation including:
- All configuration options
- Writing new tests
- Integration patterns
- API response formats
- Advanced use cases

---

**Status**: ✅ All tests passing  
**Duration**: ~0.6 seconds  
**Zero Dependencies**: No Azure credentials needed
