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
./generate-appsettings.sh appsettings.json
./deploy-container.sh
./show-logs.sh
```

## Metadata refresh

```bash
python update_mcp_tool_metadata.py
python update_monitor_community_metadata.py
```

`appsettings.json` is generated per environment and should be treated as local runtime config.
