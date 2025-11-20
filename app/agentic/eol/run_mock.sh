#!/bin/bash
# Run the EOL application with mock data (no Azure dependencies)

echo "🧪 Starting EOL Application in MOCK MODE"
echo "========================================="
echo ""
echo "Configuration:"
echo "  - Mock Data: ENABLED"
echo "  - Mock Computers: 50"
echo "  - Windows Ratio: 60%"
echo "  - Port: 8000"
echo ""
echo "Starting server..."
echo ""

# Set environment variables for mock mode
export USE_MOCK_DATA=true
export MOCK_NUM_COMPUTERS=50
export MOCK_WINDOWS_RATIO=0.6
export MOCK_SOFTWARE_MIN=5
export MOCK_SOFTWARE_MAX=20
export TEST_CACHE_ENABLED=false

# Change to the eol directory
cd "$(dirname "$0")"

# Resolve the project root so we can use the workspace virtual environment
PROJECT_ROOT="$(cd ../../.. && pwd)"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
	echo "⚠️  Virtual environment not found at $PYTHON_BIN"
	echo "    Falling back to system python3"
	PYTHON_BIN="python3"
fi

# Run the FastAPI app with uvicorn using the selected interpreter
"$PYTHON_BIN" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
