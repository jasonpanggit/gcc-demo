# Deployment Scripts

Deployment helpers for the EOL agentic app.

## Files in this folder

- `Dockerfile`
- `generate-appsettings.sh`
- `deploy-container.sh`
- `show-logs.sh`
- `update_mcp_tool_metadata.py`
- `update_monitor_community_metadata.py`
- `appsettings.json.example`

## Typical flow

From `app/agentic/eol/deploy`:

```bash
export AZURE_SP_CLIENT_SECRET=...
export TEAMS_BOT_APP_PASSWORD=...
./generate-appsettings.sh appsettings.json
./deploy-container.sh
./show-logs.sh
```

Secrets should not be written directly into `appsettings*.json`. Use environment-variable references such as `${AZURE_SP_CLIENT_SECRET}` and `${TEAMS_BOT_APP_PASSWORD}` in the JSON files, and let the deploy scripts resolve them at runtime.

## Metadata refresh

```bash
python update_mcp_tool_metadata.py
python update_monitor_community_metadata.py
```

`appsettings.json` is generated per environment and should be treated as local runtime config. It is gitignored; keep sensitive values in environment variables, not in the file contents.
