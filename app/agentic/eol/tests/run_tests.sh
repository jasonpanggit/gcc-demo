#!/usr/bin/env bash
# Run the EOL agentic test suite
#
# IMPORTANT: This script uses run_pytest.py wrapper to fix import path issues
# caused by namespace collision between local 'agents' module and agent-framework-core

set -euo pipefail

# Find the repo root (where .venv and pytest.ini live)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"

# Change to repo root for correct paths
cd "$REPO_ROOT"

# Activate venv if it exists and we're not already in it
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d "$REPO_ROOT/.venv" ]; then
    echo "Activating virtual environment..."
    source "$REPO_ROOT/.venv/bin/activate"
fi

echo "Running tests from: $(pwd)"
echo "Using run_pytest.py wrapper to fix import paths..."

# Default: run all tests excluding remote
# Use the run_pytest.py wrapper which fixes the namespace collision
exec python "$SCRIPT_DIR/run_pytest.py" -v -m "not remote" "$@"
