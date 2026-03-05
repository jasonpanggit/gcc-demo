#!/usr/bin/env bash
# run_remote_examples.sh — Execute all 40 SRE example prompts against the deployed app
#
# Usage:
#   ./run_remote_examples.sh                          # Use default APP_BASE_URL
#   APP_BASE_URL=https://... ./run_remote_examples.sh # Override URL
#   ./run_remote_examples.sh --category health        # Run one category only
#   ./run_remote_examples.sh --phase 1                # Run phase-tagged tests only
#   ./run_remote_examples.sh --fast                   # Skip slow tests (< 10s expected)
#   ./run_remote_examples.sh --report                 # Generate JSON report + log failures
#
# Requirements:
#   - .venv with pytest, playwright, pytest-json-report installed
#   - Playwright browsers installed: playwright install chromium
#   - APP_BASE_URL or default remote URL accessible

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../../../../" && pwd)"
RESULTS_DIR="$SCRIPT_DIR/test-results"
REPORT_FILE="$RESULTS_DIR/pytest-report.json"

cd "$REPO_ROOT"

# Activate venv
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d "$REPO_ROOT/.venv" ]; then
    source "$REPO_ROOT/.venv/bin/activate"
fi

# Defaults
CATEGORY=""
PHASE=""
EXTRA_MARKERS="remote"
JSON_REPORT_ARGS=""
FAST=false
LOG_FAILURES=false

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --category)
            CATEGORY="$2"; shift 2 ;;
        --phase)
            PHASE="$2"; shift 2 ;;
        --fast)
            FAST=true; shift ;;
        --report)
            LOG_FAILURES=true
            mkdir -p "$RESULTS_DIR"
            JSON_REPORT_ARGS="--json-report --json-report-file=$REPORT_FILE"
            shift ;;
        *)
            echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

# Build marker expression
MARKER_EXPR="$EXTRA_MARKERS"
if [[ -n "$PHASE" ]]; then
    MARKER_EXPR="$MARKER_EXPR and phase${PHASE}"
fi
if [[ "$FAST" == "true" ]]; then
    MARKER_EXPR="$MARKER_EXPR and not slow"
fi

# Build keyword expression for category filtering
KEYWORD_ARGS=""
if [[ -n "$CATEGORY" ]]; then
    case "$CATEGORY" in
        health)      KEYWORD_ARGS="-k TestHealthAvailability" ;;
        incident)    KEYWORD_ARGS="-k TestIncidentTriage" ;;
        network)     KEYWORD_ARGS="-k TestNetworkDiagnostics" ;;
        security)    KEYWORD_ARGS="-k TestSecurityCompliance" ;;
        cost)        KEYWORD_ARGS="-k TestInventoryCost" ;;
        performance) KEYWORD_ARGS="-k TestPerformanceSlo" ;;
        validation)  KEYWORD_ARGS="-k TestResourceValidation" ;;
        *)           echo "Unknown category: $CATEGORY. Use: health|incident|network|security|cost|performance|validation" >&2; exit 1 ;;
    esac
fi

echo "============================================"
echo "  SRE Example Prompts — Remote E2E Tests"
echo "============================================"
echo "  URL:      ${APP_BASE_URL:-default remote}"
echo "  Markers:  $MARKER_EXPR"
echo "  Category: ${CATEGORY:-all}"
echo "  Phase:    ${PHASE:-all}"
echo "  Report:   ${LOG_FAILURES}"
echo "============================================"
echo ""

# Run tests using the pytest wrapper
# shellcheck disable=SC2086
python "$TESTS_DIR/run_pytest.py" \
    -v \
    -m "$MARKER_EXPR" \
    $KEYWORD_ARGS \
    $JSON_REPORT_ARGS \
    --timeout=60 \
    "app/agentic/eol/tests/ui/pages/test_sre_assistant.py"

EXIT_CODE=$?

# Log failures if requested
if [[ "$LOG_FAILURES" == "true" && -f "$REPORT_FILE" ]]; then
    echo ""
    echo "Logging failures to issue log..."
    python "$SCRIPT_DIR/log_test_failures.py" "$REPORT_FILE"
fi

echo ""
echo "Done. Exit code: $EXIT_CODE"
exit $EXIT_CODE
