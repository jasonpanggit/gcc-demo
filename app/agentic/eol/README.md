# EOL Agentic Application

FastAPI-based agentic application for software lifecycle and Azure operations workflows.

## Key areas

- API routers: `api/`
- Orchestrators and agents: `agents/`
- Local MCP servers: `mcp_servers/`
- Utility and client layer: `utils/`
- Web UI: `templates/` and `static/`
- Tests: `tests/`

## Run locally

From repo root:

```bash
cd app/agentic/eol
source ../../../.venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Mock-data run (no Azure dependencies):

```bash
./run_mock.sh
```

## Tests

```bash
cd tests
./run_tests.sh
```

Other common options:

- `./run_tests.sh --remote`
- `./run_tests.sh --mcp-server sre`

## Deployment docs

See `deploy/README.md` for container deployment scripts and appsettings generation.
