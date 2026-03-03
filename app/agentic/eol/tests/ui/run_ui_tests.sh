#!/bin/bash

# UI Test Runner Script
# Runs Playwright UI tests for the Azure Agentic Platform

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Azure Agentic Platform - UI Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "conftest.py" ]; then
    echo -e "${RED}Error: Must run from tests/ui directory${NC}"
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not found. Install with: pip install -r ui-requirements.txt${NC}"
    exit 1
fi

# Check if playwright is installed
if ! command -v playwright &> /dev/null; then
    echo -e "${RED}Error: playwright not found. Installing...${NC}"
    pip install playwright
    playwright install chromium
fi

# Parse command line arguments
MODE="all"
HEADED=""
SLOWMO=""
BROWSER="chromium"
PARALLEL=""
HTML_REPORT=""
VIDEO=""
SCREENSHOT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --headed)
            HEADED="--headed"
            shift
            ;;
        --slowmo)
            SLOWMO="--slowmo=1000"
            shift
            ;;
        --browser)
            BROWSER="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL="-n auto"
            shift
            ;;
        --html)
            HTML_REPORT="--html=ui_test_report.html --self-contained-html"
            shift
            ;;
        --video)
            VIDEO="--video=on"
            shift
            ;;
        --screenshot)
            SCREENSHOT="--screenshot=only-on-failure"
            shift
            ;;
        --help)
            echo "Usage: ./run_ui_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --headed          Run tests in headed mode (visible browser)"
            echo "  --slowmo          Run tests with 1s delay between actions"
            echo "  --browser NAME    Browser to use (chromium, firefox, webkit)"
            echo "  --parallel        Run tests in parallel"
            echo "  --html            Generate HTML report"
            echo "  --video           Record video of test execution"
            echo "  --screenshot      Take screenshots on failure"
            echo "  --help            Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_ui_tests.sh                          # Run all tests"
            echo "  ./run_ui_tests.sh --headed --slowmo        # Debug mode"
            echo "  ./run_ui_tests.sh --parallel --html        # Fast with report"
            echo "  ./run_ui_tests.sh --browser firefox        # Test in Firefox"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set base URL if not already set
if [ -z "$APP_BASE_URL" ]; then
    # TODO: make it easier to override this for local and remote testing
    export APP_BASE_URL="https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"
    echo -e "${YELLOW}Using default APP_BASE_URL: $APP_BASE_URL${NC}"
else
    echo -e "${GREEN}Using APP_BASE_URL: $APP_BASE_URL${NC}"
fi

echo ""

# Build pytest command
PYTEST_CMD="pytest . -v --browser=$BROWSER $HEADED $SLOWMO $PARALLEL $HTML_REPORT $VIDEO $SCREENSHOT"

echo -e "${GREEN}Running UI tests...${NC}"
echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"
echo ""

# Run tests
if eval $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ All UI tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ -n "$HTML_REPORT" ]; then
        echo -e "${GREEN}HTML report generated: ui_test_report.html${NC}"
    fi

    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Some UI tests failed${NC}"
    echo -e "${RED}========================================${NC}"

    if [ -n "$HTML_REPORT" ]; then
        echo -e "${YELLOW}Check HTML report: ui_test_report.html${NC}"
    fi

    exit 1
fi
