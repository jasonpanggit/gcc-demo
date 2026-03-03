# Test Infrastructure Summary

## Files Moved to `tests/` Directory (Not Git-Tracked)

All test-related files have been moved into the `tests/` directory so they won't be tracked in Git (per `.gitignore` configuration).

### Core Test Infrastructure
- **`tests/conftest.py`** - Root pytest configuration that fixes namespace collision between local `agents` module and `agent-framework-core` package
- **`tests/run_pytest.py`** - Custom pytest wrapper that ensures correct import paths before test collection
- **`tests/run_tests.sh`** - Main test runner script

### Individual Test Category Runners
Each test subdirectory now has its own `run_tests.sh` script for convenience:
- `tests/agents/run_tests.sh`
- `tests/cache/run_tests.sh`
- `tests/config/run_tests.sh`
- `tests/integration/run_tests.sh`
- `tests/mcp_servers/run_tests.sh`
- `tests/network/run_tests.sh`
- `tests/orchestrators/run_tests.sh`
- `tests/reliability/run_tests.sh`
- `tests/remote/run_tests.sh`
- `tests/routing/run_tests.sh`
- `tests/services/run_tests.sh`
- `tests/tools/run_tests.sh`
- `tests/ui/run_tests.sh`
- `tests/unit/run_tests.sh`

### Documentation
- **`tests/RUNNING_TESTS.md`** - Comprehensive guide on running tests

## Why These Files Are Not Tracked

According to the project's `.gitignore`:
```
tests/
```

This means:
- ✅ All files in `tests/` directories are ignored by git
- ✅ Test infrastructure stays local to each developer
- ✅ No test file conflicts during merges
- ✅ Keeps repository focused on production code

## Usage

### Run all tests:
```bash
cd app/agentic/eol/tests
./run_tests.sh
```

### Run specific test category:
```bash
cd app/agentic/eol/tests/agents
./run_tests.sh
```

### Run with filters:
```bash
cd app/agentic/eol/tests/agents
./run_tests.sh -k "test_agent_initialization"
```

## Technical Details

### Import Path Fix
The namespace collision fix works by:
1. `conftest.py` modifies `sys.path` before pytest starts collecting tests
2. Ensures local `app/agentic/eol/agents` is checked BEFORE site-packages `agents` module
3. `run_pytest.py` wrapper ensures this happens before pytest's assertion rewrite phase

### Virtual Environment
All scripts automatically activate `.venv` if it exists and isn't already active.

### Working Directory
All scripts change to the repo root before running tests, ensuring correct import paths.
