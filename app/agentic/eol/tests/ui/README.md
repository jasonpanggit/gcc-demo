# UI Test Suite

Playwright + pytest UI tests for the EOL app pages and assistant workflows.

## Folder contents

- Page test modules (`test_*.py`)
- Shared fixtures/config (`conftest.py`, `pytest.ini`)
- Convenience runner (`run_ui_tests.sh`)

## Run tests

From `app/agentic/eol`:

```bash
source ../../../.venv/bin/activate
pip install -r requirements.txt
pytest tests/ui -v
```

Common debug modes:

- `pytest tests/ui -v --headed`
- `pytest tests/ui -v --screenshot=only-on-failure`

Many markdown result files in this folder are historical test reports/artifacts.
