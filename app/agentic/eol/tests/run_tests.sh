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

# Check for specific test file or custom args
if [ $# -gt 0 ]; then
    if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
        echo "Usage: $0 [options] [test_path] [pytest_args]"
        echo ""
        echo "Options:"
        echo "  --remote              Run tests against Azure production deployment"
        echo "  --url URL             Run tests against custom URL"
        echo "  -h, --help            Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                                    # Run all tests (local)"
        echo "  $0 --remote                           # Run all tests (Azure production)"
        echo "  $0 --url http://localhost:5000        # Run against custom URL"
        echo "  $0 tests/test_azure_mcp_endpoints.py  # Run specific file"
        echo "  $0 tests/ -k test_mcp                 # Run tests matching pattern"
        echo "  $0 tests/ -x                          # Stop at first failure"
        echo "  $0 tests/ --maxfail=3                 # Stop after 3 failures"
        echo "  $0 tests/ -m api                      # Run tests with @pytest.mark.api"
        echo "  $0 --remote tests/ -k health          # Run health tests on Azure"
        echo ""
        exit 0
    fi
    
    # Check for remote flag
    if [ "$1" == "--remote" ]; then
        USE_REMOTE=true
        TEST_URL="https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"
        shift
    elif [ "$1" == "--url" ]; then
        if [ -z "$2" ]; then
            echo -e "${RED}❌ Error: --url requires a URL argument${NC}"
            exit 1
        fi
        TEST_URL="$2"
        shift 2
    fi
    
    # If first arg looks like a file/path, use it as test path
    if [[ "$1" == tests/* ]] || [[ "$1" == *test*.py ]]; then
        TEST_PATH="$1"
        shift
    fi
    
    # Add any remaining args as pytest arguments
    if [ $# -gt 0 ]; then
        PYTEST_ARGS="$PYTEST_ARGS $@"
    fi
fi

echo -e "${BLUE}📋 Test Configuration:${NC}"
echo -e "   Test Path: ${YELLOW}$TEST_PATH${NC}"
echo -e "   Arguments: ${YELLOW}$PYTEST_ARGS${NC}"
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
