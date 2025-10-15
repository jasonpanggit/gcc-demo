#!/bin/bash
#
# Wrapper script to run debug_bing_search.py with the .venv environment
#

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to the workspace root (4 levels up from tests/)
WORKSPACE_ROOT="$SCRIPT_DIR/../../../.."
cd "$WORKSPACE_ROOT"

echo "📍 Workspace: $WORKSPACE_ROOT"
echo "🐍 Activating .venv..."

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Error: .venv directory not found in $WORKSPACE_ROOT"
    echo "   Please create a virtual environment first:"
    echo "   python3 -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install playwright"
    echo "   playwright install chromium"
    exit 1
fi

# Activate the virtual environment
source .venv/bin/activate

# Check if playwright is installed
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "⚠️  Playwright not found in .venv, installing..."
    pip3 install playwright
    echo "📦 Installing Playwright browsers..."
    python3 -m playwright install chromium
fi

echo "✅ Environment ready"
echo "🚀 Running debug_bing_search.py..."
echo ""

# Run the Python script
python3 "$SCRIPT_DIR/debug_bing_search.py"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ Script completed successfully"
else
    echo ""
    echo "❌ Script failed with exit code: $exit_code"
fi

exit $exit_code
