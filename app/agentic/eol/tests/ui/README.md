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

Marker examples:

- `pytest tests/ui/pages/test_inventory_ai_v2.py -v -m remote`
- `APP_BASE_URL=http://127.0.0.1:8000 pytest tests/ui/pages/test_inventory_ai_v2.py -v -m local`

Inventory Assistant V2 remote examples:

- Browser/page coverage with remote-safe mocked endpoint interception:
	`APP_BASE_URL=https://your-remote-app pytest tests/ui/pages/test_inventory_ai_v2.py -v -m remote`
- Real remote API integration checks for deterministic preview and blocked execute flows:
	`APP_BASE_URL=https://your-remote-app pytest tests/ui/pages/test_inventory_ai_v2_remote.py -v -m remote`

Many markdown result files in this folder are historical test reports/artifacts.
