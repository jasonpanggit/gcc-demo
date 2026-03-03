#!/usr/bin/env python3
"""
Custom pytest wrapper that fixes import path BEFORE pytest starts.

This script resolves a namespace collision between the local `agents` directory
and the `agents` module from the agent-framework-core package. It ensures that
app/agentic/eol is at the BEGINNING of sys.path so the local modules are found first.

Usage:
    python run_pytest.py [pytest args...]

Example:
    python run_pytest.py app/agentic/eol/tests/agents/test_microsoft_agent.py -v
    python run_pytest.py -m "not remote" -v
"""

import sys
from pathlib import Path

# Get repo root (where this script is located)
repo_root = Path(__file__).parent
eol_path = repo_root / "app" / "agentic" / "eol"
eol_path_str = str(eol_path.resolve())

# Remove from sys.path if already there (avoid duplicates)
if eol_path_str in sys.path:
    sys.path.remove(eol_path_str)

# Insert at position 0 to ensure it's checked FIRST, before agent-framework
sys.path.insert(0, eol_path_str)

# Now import and run pytest
if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(sys.argv[1:]))
