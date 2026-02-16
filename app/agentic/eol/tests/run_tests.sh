#!/bin/bash

# Test Runner Script for EOL Agentic Platform
# Runs all tests using the venv Python environment

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/../../../.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}EOL Agentic Platform - Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if venv exists
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}❌ Virtual environment not found at: $VENV_PATH${NC}"
    echo -e "${YELLOW}💡 Create it with: python -m venv $VENV_PATH${NC}"
    exit 1
fi

# Check if venv Python exists
if [ ! -f "$VENV_PATH/bin/python" ]; then
    echo -e "${RED}❌ Python not found in venv: $VENV_PATH/bin/python${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Using venv: $VENV_PATH${NC}"
echo -e "${GREEN}✅ Python: $("$VENV_PATH/bin/python" --version)${NC}"
echo ""

# Change to project directory
cd "$PROJECT_ROOT"

# Parse command line arguments
PYTEST_ARGS="-v"
TEST_PATH="tests/"
TEST_URL=""
USE_REMOTE=false
MCP_SERVER=""
GENERATE_COVERAGE=false
TEST_CATEGORY=""
PARALLEL=""
VERBOSE_MODE=false
DEBUG_MODE=false

# Check for specific test file or custom args
if [ $# -gt 0 ]; then
    if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
        echo "Usage: $0 [options] [test_path] [pytest_args]"
        echo ""
        echo "Options:"
        echo "  --remote              Run tests against Azure production deployment"
        echo "  --url URL             Run tests against custom URL"
        echo "  --mcp                 Run only MCP-related tests"
        echo "  --mcp-server NAME     Run tests for specific MCP server (sre, inventory, monitor, os_eol, azure_cli, azure)"
        echo "  --coverage            Generate coverage report (HTML format)"
        echo "  --coverage-module MOD Generate coverage for specific module (mcp_servers, agents, utils)"
        echo "  --unit                Run only unit tests"
        echo "  --integration         Run only integration tests"
        echo "  --parallel N          Run tests in parallel with N workers"
        echo "  --verbose             Show detailed output (-vv)"
        echo "  --debug               Show debug logs and stdout/stderr"
        echo "  -h, --help            Show this help message"
        echo ""
        echo "Examples:"
        echo "  # Basic usage"
        echo "  $0                                    # Run all tests (local)"
        echo "  $0 --remote                           # Run all tests (Azure production)"
        echo "  $0 --url http://localhost:5000        # Run against custom URL"
        echo ""
        echo "  # MCP-specific testing"
        echo "  $0 --mcp                              # Run all MCP tests"
        echo "  $0 --mcp-server sre                   # Run only SRE MCP server tests"
        echo "  $0 --mcp-server inventory             # Run only Inventory MCP server tests"
        echo "  $0 --mcp --remote                     # Run MCP tests against Azure"
        echo ""
        echo "  # Coverage reports"
        echo "  $0 --coverage                         # Generate coverage for all modules"
        echo "  $0 --coverage --mcp-server sre        # Coverage for SRE MCP server"
        echo "  $0 --coverage-module mcp_servers      # Coverage for mcp_servers only"
        echo ""
        echo "  # Test categories"
        echo "  $0 --unit                             # Run only unit tests"
        echo "  $0 --integration                      # Run only integration tests"
        echo "  $0 --parallel 4                       # Run tests with 4 workers"
        echo ""
        echo "  # Specific files and patterns"
        echo "  $0 tests/test_azure_mcp_endpoints.py  # Run specific file"
        echo "  $0 tests/ -k test_mcp                 # Run tests matching pattern"
        echo "  $0 tests/ -x                          # Stop at first failure"
        echo "  $0 tests/ --maxfail=3                 # Stop after 3 failures"
        echo "  $0 tests/ -m api                      # Run tests with @pytest.mark.api"
        echo ""
        echo "  # Debug and verbose"
        echo "  $0 --verbose tests/test_sre_mcp_tools.py  # Detailed output"
        echo "  $0 --debug tests/test_inventory_mcp_tools.py  # Debug logs"
        echo ""
        exit 0
    fi

    # Process all flags
    while [ $# -gt 0 ]; do
        case "$1" in
            --remote)
                USE_REMOTE=true
                TEST_URL="https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"
                shift
                ;;
            --url)
                if [ -z "$2" ]; then
                    echo -e "${RED}❌ Error: --url requires a URL argument${NC}"
                    exit 1
                fi
                TEST_URL="$2"
                shift 2
                ;;
            --mcp)
                # Run all MCP tests
                PYTEST_ARGS="$PYTEST_ARGS -m mcp"
                shift
                ;;
            --mcp-server)
                if [ -z "$2" ]; then
                    echo -e "${RED}❌ Error: --mcp-server requires server name (sre, inventory, monitor, os_eol, azure_cli, azure)${NC}"
                    exit 1
                fi
                MCP_SERVER="$2"
                PYTEST_ARGS="$PYTEST_ARGS -m mcp_$MCP_SERVER"
                shift 2
                ;;
            --coverage)
                GENERATE_COVERAGE=true
                shift
                ;;
            --coverage-module)
                if [ -z "$2" ]; then
                    echo -e "${RED}❌ Error: --coverage-module requires module name${NC}"
                    exit 1
                fi
                GENERATE_COVERAGE=true
                COVERAGE_MODULE="$2"
                shift 2
                ;;
            --unit)
                PYTEST_ARGS="$PYTEST_ARGS -m unit"
                shift
                ;;
            --integration)
                PYTEST_ARGS="$PYTEST_ARGS -m integration"
                shift
                ;;
            --parallel)
                if [ -z "$2" ]; then
                    echo -e "${RED}❌ Error: --parallel requires number of workers${NC}"
                    exit 1
                fi
                PARALLEL="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE_MODE=true
                PYTEST_ARGS="$PYTEST_ARGS -vv"
                shift
                ;;
            --debug)
                DEBUG_MODE=true
                export LOG_LEVEL=DEBUG
                PYTEST_ARGS="$PYTEST_ARGS -s"  # Show stdout/stderr
                shift
                ;;
            tests/*|*test*.py)
                TEST_PATH="$1"
                shift
                ;;
            *)
                # Any remaining args go to pytest
                PYTEST_ARGS="$PYTEST_ARGS $1"
                shift
                ;;
        esac
    done
fi

echo -e "${BLUE}📋 Test Configuration:${NC}"
echo -e "   Test Path: ${YELLOW}$TEST_PATH${NC}"
echo -e "   Arguments: ${YELLOW}$PYTEST_ARGS${NC}"
if [ -n "$MCP_SERVER" ]; then
    echo -e "   MCP Server: ${YELLOW}$MCP_SERVER${NC}"
fi
if [ "$GENERATE_COVERAGE" = true ]; then
    echo -e "   Coverage: ${GREEN}✅ Enabled${NC}"
fi
if [ -n "$PARALLEL" ]; then
    echo -e "   Parallel: ${GREEN}$PARALLEL workers${NC}"
fi
if [ -n "$TEST_URL" ]; then
    echo -e "   Target URL: ${YELLOW}$TEST_URL${NC}"
    if [ "$USE_REMOTE" = true ]; then
        echo -e "   Mode: ${GREEN}🌐 Azure Production${NC}"
    else
        echo -e "   Mode: ${GREEN}🔧 Custom URL${NC}"
    fi
else
    echo -e "   Mode: ${GREEN}🏠 Local (Mock Data)${NC}"
fi
echo ""

# Set environment variables for remote testing
if [ -n "$TEST_URL" ]; then
    export BASE_URL="$TEST_URL"
    export USE_MOCK_DATA="false"
else
    export USE_MOCK_DATA="true"
fi

# Add coverage arguments
if [ "$GENERATE_COVERAGE" = true ]; then
    if [ -n "$COVERAGE_MODULE" ]; then
        PYTEST_ARGS="$PYTEST_ARGS --cov=$COVERAGE_MODULE --cov-report=html --cov-report=term"
    else
        PYTEST_ARGS="$PYTEST_ARGS --cov=mcp_servers --cov=agents --cov=utils --cov-report=html --cov-report=term"
    fi
fi

# Add parallel execution
if [ -n "$PARALLEL" ]; then
    PYTEST_ARGS="$PYTEST_ARGS -n $PARALLEL"
    echo -e "${BLUE}ℹ️  Note: Parallel execution requires pytest-xdist (pip install pytest-xdist)${NC}"
    echo ""
fi

# Run pytest with venv Python
echo -e "${BLUE}🚀 Running tests...${NC}"
echo ""

set +e  # Don't exit on test failures
"$VENV_PATH/bin/python" -m pytest $TEST_PATH $PYTEST_ARGS
TEST_EXIT_CODE=$?
set -e

echo ""
echo -e "${BLUE}========================================${NC}"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
elif [ $TEST_EXIT_CODE -eq 5 ]; then
    echo -e "${YELLOW}⚠️  No tests collected${NC}"
else
    echo -e "${RED}❌ Tests failed (exit code: $TEST_EXIT_CODE)${NC}"
fi

echo -e "${BLUE}========================================${NC}"

exit $TEST_EXIT_CODE
