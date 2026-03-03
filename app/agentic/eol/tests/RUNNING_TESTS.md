# Running Tests

This document explains how to run the test suite for the EOL agentic platform.

## Quick Start

### Run All Tests
```bash
cd app/agentic/eol/tests
./run_tests.sh
```

### Run Specific Test Category
Each test subdirectory has its own `run_tests.sh` script for convenience:

```bash
# Run agent tests only
cd app/agentic/eol/tests/agents
./run_tests.sh

# Run orchestrator tests only
cd app/agentic/eol/tests/orchestrators
./run_tests.sh

# Run UI tests only
cd app/agentic/eol/tests/ui
./run_tests.sh
```

## Available Test Categories

| Directory | Description | Script |
|-----------|-------------|--------|
| `agents/` | Agent implementation tests | `agents/run_tests.sh` |
| `cache/` | Caching layer tests | `cache/run_tests.sh` |
| `config/` | Configuration tests | `config/run_tests.sh` |
| `integration/` | Integration tests | `integration/run_tests.sh` |
| `mcp_servers/` | MCP server tests | `mcp_servers/run_tests.sh` |
| `network/` | Network functionality tests | `network/run_tests.sh` |
| `orchestrators/` | Orchestrator tests | `orchestrators/run_tests.sh` |
| `reliability/` | Reliability tests | `reliability/run_tests.sh` |
| `remote/` | Remote/Azure tests | `remote/run_tests.sh` |
| `routing/` | Routing tests | `routing/run_tests.sh` |
| `services/` | Service tests | `services/run_tests.sh` |
| `tools/` | Tool tests | `tools/run_tests.sh` |
| `ui/` | UI tests | `ui/run_tests.sh` |
| `unit/` | Unit tests | `unit/run_tests.sh` |

## Advanced Usage

### Run Specific Test File
```bash
cd app/agentic/eol/tests/agents
./run_tests.sh test_microsoft_agent.py
```

### Run Specific Test Function
```bash
cd app/agentic/eol/tests/agents
./run_tests.sh -k "test_agent_initialization"
```

### Run with Coverage
```bash
cd app/agentic/eol/tests
./run_tests.sh --cov=. --cov-report=html
```

### Run Remote Tests
```bash
cd app/agentic/eol/tests
./run_tests.sh -m remote
```

### Run Only Fast Tests
```bash
cd app/agentic/eol/tests
./run_tests.sh -m "not slow"
```

## Test Markers

The test suite uses pytest markers to categorize tests:

- `unit` - Unit tests (no external dependencies)
- `integration` - Integration tests
- `remote` - Tests requiring Azure access
- `slow` - Tests taking >1 second
- `mcp` - MCP server tests
- `ui` - UI/frontend tests
- `asyncio` - Async tests
- `azure` - Tests requiring Azure services

## Technical Details

### Import Path Fix
The test suite uses a custom pytest wrapper (`run_pytest.py`) to fix a namespace collision between the local `agents` module and the `agents` module from the `agent-framework-core` package. This is handled automatically by all `run_tests.sh` scripts.

### Virtual Environment
All test scripts automatically activate the `.venv` environment at the repo root if it's not already active.

### Working Directory
Tests must be run from the repository root directory for imports to work correctly. All `run_tests.sh` scripts handle this automatically.

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError` errors, ensure you're using the `run_tests.sh` scripts rather than running pytest directly.

### Virtual Environment Not Found
Make sure you've created the virtual environment:
```bash
cd /path/to/gcc-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/agentic/eol/requirements.txt
```

### Tests Not Found
Make sure you're running the script from the correct directory. Each `run_tests.sh` script is designed to be run from its own directory.

## Examples

```bash
# Run all agent tests
cd app/agentic/eol/tests/agents && ./run_tests.sh

# Run only Microsoft agent tests
cd app/agentic/eol/tests/agents && ./run_tests.sh test_microsoft_agent.py

# Run all tests except remote ones (default)
cd app/agentic/eol/tests && ./run_tests.sh

# Run all tests including remote ones
cd app/agentic/eol/tests && ./run_tests.sh -m ""

# Run with verbose output
cd app/agentic/eol/tests/orchestrators && ./run_tests.sh -vv

# Run with detailed failure info
cd app/agentic/eol/tests && ./run_tests.sh --tb=long
```
