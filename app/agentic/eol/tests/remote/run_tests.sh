#!/usr/bin/env bash
# Run tests for this directory only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/../../../../" && pwd)"
cd "$REPO_ROOT"

# Activate venv if needed
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d "$REPO_ROOT/.venv" ]; then
    source "$REPO_ROOT/.venv/bin/activate"
fi

# Get the test directory name
TEST_DIR="$(basename "$SCRIPT_DIR")"
echo "Running $TEST_DIR tests..."

# Run tests for this directory using the pytest wrapper
exec python "$TESTS_DIR/run_pytest.py" -v "app/agentic/eol/tests/$TEST_DIR" "$@"
