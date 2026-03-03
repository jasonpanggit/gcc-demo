#!/usr/bin/env bash
# Run remote tool-selection tests against the live Container App.
#
# Usage
# -----
#   # Default: uses URL from appsettings.json
#   ./tests/run_remote_tool_tests.sh
#
#   # Custom URL
#   TEST_BASE_URL=https://myapp.azurecontainerapps.io ./tests/run_remote_tool_tests.sh
#
#   # Run only a subset by keyword
#   ./tests/run_remote_tool_tests.sh -k virtual_networks
#
#   # Verbose + stop on first failure
#   ./tests/run_remote_tool_tests.sh -v -x
#
# The script resolves the Container App URL from appsettings.json when
# TEST_BASE_URL is not set in the environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"   # app/agentic/eol/tests → workspace root
EOL_DIR="$REPO_ROOT/app/agentic/eol"
APPSETTINGS="$EOL_DIR/deploy/appsettings.json"

# ---------------------------------------------------------------------------
# Resolve TEST_BASE_URL
# ---------------------------------------------------------------------------
if [[ -z "${TEST_BASE_URL:-}" ]]; then
  if command -v jq &>/dev/null && [[ -f "$APPSETTINGS" ]]; then
    TEST_BASE_URL=$(jq -r '.Deployment.ContainerApp.Url' "$APPSETTINGS" | sed 's|/$||')
    echo "ℹ️  Using Container App URL from appsettings.json: $TEST_BASE_URL"
  else
    TEST_BASE_URL="https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io"
    echo "ℹ️  Using hard-coded default URL: $TEST_BASE_URL"
  fi
fi
export TEST_BASE_URL

# ---------------------------------------------------------------------------
# Activate venv if not already active
# ---------------------------------------------------------------------------
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="$REPO_ROOT/.venv"
  if [[ -f "$VENV/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    echo "ℹ️  Activated venv: $VENV"
  fi
fi

# Ensure httpx is available
python -c "import httpx" 2>/dev/null || pip install httpx -q

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------
echo ""
echo "🚀 Running remote tool-selection tests against: $TEST_BASE_URL"
echo "   Endpoint: $TEST_BASE_URL/api/azure-mcp/inspect-plan"
echo ""

cd "$REPO_ROOT"
exec pytest \
  app/agentic/eol/tests/test_remote_tool_selection.py \
  -m remote \
  --tb=short \
  -v \
  "$@"
