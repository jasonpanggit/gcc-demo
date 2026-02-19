#!/bin/bash

################################################################################
# UI/UX Testing Runner Script
# EOL Agentic Platform - Task #10
#
# This script runs all UI/UX tests including:
# - Lighthouse CI audits
# - Accessibility tests (axe-core)
# - Visual regression tests (optional)
# - Performance benchmarks
#
# Usage:
#   ./run-ui-tests.sh [options]
#
# Options:
#   --lighthouse    Run Lighthouse CI audits only
#   --a11y          Run accessibility tests only
#   --performance   Run performance benchmarks only
#   --all           Run all tests (default)
#   --ci            CI mode (non-interactive, exit on failure)
#   --help          Show this help message
################################################################################

set -e  # Exit on error in CI mode (can be overridden)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Default options
RUN_LIGHTHOUSE=false
RUN_A11Y=false
RUN_PERFORMANCE=false
RUN_ALL=true
CI_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --lighthouse)
      RUN_LIGHTHOUSE=true
      RUN_ALL=false
      shift
      ;;
    --a11y)
      RUN_A11Y=true
      RUN_ALL=false
      shift
      ;;
    --performance)
      RUN_PERFORMANCE=true
      RUN_ALL=false
      shift
      ;;
    --all)
      RUN_ALL=true
      shift
      ;;
    --ci)
      CI_MODE=true
      shift
      ;;
    --help)
      grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# //'
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# If --all, enable all tests
if [ "$RUN_ALL" = true ]; then
  RUN_LIGHTHOUSE=true
  RUN_A11Y=true
  RUN_PERFORMANCE=true
fi

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

################################################################################
# Helper Functions
################################################################################

print_header() {
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
  echo ""
}

print_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "${RED}✗ $1${NC}"
}

print_warning() {
  echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
  echo -e "${BLUE}ℹ $1${NC}"
}

check_command() {
  if ! command -v "$1" &> /dev/null; then
    print_error "$1 is not installed"
    return 1
  fi
  return 0
}

check_server() {
  local url="$1"
  if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|302"; then
    return 0
  else
    return 1
  fi
}

record_test_result() {
  TESTS_TOTAL=$((TESTS_TOTAL + 1))
  if [ $1 -eq 0 ]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    print_success "$2"
  else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    print_error "$2"
    if [ "$CI_MODE" = true ]; then
      exit 1
    fi
  fi
}

################################################################################
# Pre-flight Checks
################################################################################

print_header "Pre-flight Checks"

# Check if Node.js is installed (for Lighthouse)
if check_command "node"; then
  NODE_VERSION=$(node --version)
  print_success "Node.js installed: $NODE_VERSION"
else
  print_error "Node.js is required for Lighthouse CI"
  exit 1
fi

# Check if npm is installed
if check_command "npm"; then
  NPM_VERSION=$(npm --version)
  print_success "npm installed: $NPM_VERSION"
else
  print_error "npm is required"
  exit 1
fi

# Check if Python is installed (for Flask app)
if check_command "python3" || check_command "python"; then
  PYTHON_CMD=$(command -v python3 || command -v python)
  PYTHON_VERSION=$($PYTHON_CMD --version)
  print_success "Python installed: $PYTHON_VERSION"
else
  print_error "Python is required to run the Flask application"
  exit 1
fi

# Check if application server is running
print_info "Checking if application server is running..."
if check_server "http://localhost:5000"; then
  print_success "Application server is running at http://localhost:5000"
  SERVER_STARTED_BY_SCRIPT=false
else
  print_warning "Application server is not running"
  print_info "Starting Flask application..."

  # Navigate to app directory
  cd "$PROJECT_ROOT/app/agentic/eol" || exit 1

  # Start Flask in background
  nohup python3 main.py > /tmp/flask-ui-test.log 2>&1 &
  FLASK_PID=$!
  SERVER_STARTED_BY_SCRIPT=true

  # Wait for server to start (max 30 seconds)
  for i in {1..30}; do
    if check_server "http://localhost:5000"; then
      print_success "Application server started (PID: $FLASK_PID)"
      break
    fi
    if [ $i -eq 30 ]; then
      print_error "Failed to start application server"
      print_info "Check logs at /tmp/flask-ui-test.log"
      exit 1
    fi
    sleep 1
  done
fi

################################################################################
# Lighthouse CI Tests
################################################################################

if [ "$RUN_LIGHTHOUSE" = true ]; then
  print_header "Lighthouse CI Audits"

  # Check if Lighthouse CI is installed
  if ! check_command "npx"; then
    print_error "npx is required for Lighthouse CI"
    record_test_result 1 "Lighthouse CI: Dependency check failed"
  else
    # Install @lhci/cli if not available
    print_info "Installing Lighthouse CI (if not already installed)..."
    npm list -g @lhci/cli &> /dev/null || npm install -g @lhci/cli@0.13.x

    # Run Lighthouse CI
    print_info "Running Lighthouse audits on all pages..."
    cd "$SCRIPT_DIR" || exit 1

    if npx @lhci/cli@0.13.x autorun --config=lighthouse.config.js; then
      record_test_result 0 "Lighthouse CI: All audits passed"

      # Check if HTML report was generated
      if [ -f "lighthouse-report.html" ]; then
        print_info "Lighthouse report saved to: $SCRIPT_DIR/lighthouse-report.html"
      fi
    else
      record_test_result 1 "Lighthouse CI: Some audits failed (see output above)"
    fi
  fi
fi

################################################################################
# Accessibility Tests (axe-core)
################################################################################

if [ "$RUN_A11Y" = true ]; then
  print_header "Accessibility Tests (axe-core)"

  # Check if @axe-core/cli is installed
  print_info "Installing axe-core CLI (if not already installed)..."
  npm list -g @axe-core/cli &> /dev/null || npm install -g @axe-core/cli

  # Pages to test
  PAGES=(
    "http://localhost:5000/"
    "http://localhost:5000/agents"
    "http://localhost:5000/inventory"
    "http://localhost:5000/eol"
    "http://localhost:5000/cache"
    "http://localhost:5000/azure-mcp"
    "http://localhost:5000/azure-ai-sre"
  )

  A11Y_FAILED=0

  for page in "${PAGES[@]}"; do
    PAGE_NAME=$(echo "$page" | sed 's|http://localhost:5000||' | sed 's|^/||' | sed 's|^$|home|')
    print_info "Testing accessibility: $PAGE_NAME..."

    if axe "$page" --exit > "$SCRIPT_DIR/axe-report-$PAGE_NAME.json" 2>&1; then
      print_success "  ✓ No accessibility violations found"
    else
      print_error "  ✗ Accessibility violations found (see axe-report-$PAGE_NAME.json)"
      A11Y_FAILED=1
    fi
  done

  if [ $A11Y_FAILED -eq 0 ]; then
    record_test_result 0 "Accessibility Tests: All pages passed"
  else
    record_test_result 1 "Accessibility Tests: Some pages have violations"
  fi
fi

################################################################################
# Performance Benchmarks
################################################################################

if [ "$RUN_PERFORMANCE" = true ]; then
  print_header "Performance Benchmarks"

  # Use Lighthouse for performance testing
  print_info "Running performance benchmarks using Lighthouse..."

  # Pages to benchmark
  PAGES=(
    "http://localhost:5000/"
    "http://localhost:5000/agents"
    "http://localhost:5000/inventory"
    "http://localhost:5000/eol"
  )

  PERF_FAILED=0

  for page in "${PAGES[@]}"; do
    PAGE_NAME=$(echo "$page" | sed 's|http://localhost:5000||' | sed 's|^/||' | sed 's|^$|home|')
    print_info "Benchmarking: $PAGE_NAME..."

    # Run Lighthouse with performance-only preset
    REPORT_FILE="$SCRIPT_DIR/performance-$PAGE_NAME.json"

    if npx lighthouse "$page" \
        --only-categories=performance \
        --output=json \
        --output-path="$REPORT_FILE" \
        --chrome-flags="--headless --no-sandbox" \
        --quiet; then

      # Extract performance score (requires jq)
      if check_command "jq"; then
        PERF_SCORE=$(jq -r '.categories.performance.score * 100' "$REPORT_FILE" 2>/dev/null || echo "N/A")
        LCP=$(jq -r '.audits."largest-contentful-paint".numericValue / 1000' "$REPORT_FILE" 2>/dev/null || echo "N/A")
        FCP=$(jq -r '.audits."first-contentful-paint".numericValue / 1000' "$REPORT_FILE" 2>/dev/null || echo "N/A")

        print_info "  Performance Score: $PERF_SCORE/100"
        print_info "  FCP: ${FCP}s"
        print_info "  LCP: ${LCP}s"

        # Check if score meets threshold (90+)
        if [ "$PERF_SCORE" != "N/A" ]; then
          SCORE_INT=$(echo "$PERF_SCORE" | cut -d. -f1)
          if [ "$SCORE_INT" -ge 90 ]; then
            print_success "  ✓ Performance score meets target (90+)"
          else
            print_warning "  ⚠ Performance score below target (90+)"
            PERF_FAILED=1
          fi
        fi
      else
        print_warning "jq not installed - cannot parse performance scores"
      fi
    else
      print_error "  ✗ Lighthouse performance test failed"
      PERF_FAILED=1
    fi
  done

  if [ $PERF_FAILED -eq 0 ]; then
    record_test_result 0 "Performance Benchmarks: All pages meet targets"
  else
    record_test_result 1 "Performance Benchmarks: Some pages below target"
  fi
fi

################################################################################
# Cleanup
################################################################################

print_header "Cleanup"

# Stop Flask server if we started it
if [ "$SERVER_STARTED_BY_SCRIPT" = true ]; then
  print_info "Stopping Flask application (PID: $FLASK_PID)..."
  kill $FLASK_PID 2>/dev/null || true
  print_success "Flask application stopped"
fi

################################################################################
# Test Summary
################################################################################

print_header "Test Summary"

echo -e "Total Tests:  ${BLUE}$TESTS_TOTAL${NC}"
echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
  print_success "All UI/UX tests passed! 🎉"
  echo ""
  echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  SUCCESS: UI/UX improvements validated${NC}"
  echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
  exit 0
else
  print_error "$TESTS_FAILED test(s) failed"
  echo ""
  echo -e "${RED}═══════════════════════════════════════════════════════${NC}"
  echo -e "${RED}  FAILURE: Some tests did not pass${NC}"
  echo -e "${RED}═══════════════════════════════════════════════════════${NC}"

  if [ "$CI_MODE" = true ]; then
    exit 1
  else
    print_info "Review test output above for details"
    exit 0  # Don't fail in interactive mode
  fi
fi
