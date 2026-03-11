# Azure Agentic Application

FastAPI-based agentic application for software lifecycle and Azure operations workflows.

## Current capabilities

- End-of-life and software lifecycle analysis
- Azure MCP and SRE-assisted operations
- Resource inventory and inventory assistant workflows
- CVE search, syncing, inventory scanning, dashboarding, and alerting
- Patch mapping and remediation workflows tied to CVE results

## Key areas

- API routers: `api/`
- Orchestrators and agents: `agents/`
- Local MCP servers: `mcp_servers/`
- Utility and client layer: `utils/`
- Web UI: `templates/` and `static/`
- Tests: `tests/`

## Current application shape

- `agents/`: 43 Python modules
- `api/`: 29 Python modules
- `mcp_servers/`: 10 local MCP servers
- `utils/`: 119 Python modules

Major API areas include CVE routes (`cve*`), patch management, SRE audit/orchestration, inventory, and UI support routes.

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

## Environment variables

- This app reads configuration from process environment variables (`os.getenv`).
- Local runs should export variables in your shell before starting the app.
- Deployed runs should set variables in Azure App Service/Container Apps configuration.
- There is no runtime dependency on an `.env.example` template file.

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
