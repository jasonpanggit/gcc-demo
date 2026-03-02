# Teams App Package

Teams app manifest assets for installing the bot in Microsoft Teams.

## Required files

- `manifest.json`
- `color.png` (192x192)
- `outline.png` (32x32)

## Create package

From this folder:

```bash
./create-teams-app-package.sh
```

If needed, equivalent manual packaging:

```bash
zip -r mcp-orchestrator-teams-app.zip manifest.json color.png outline.png
```

Upload the zip in Teams via **Apps** → **Upload a custom app**.
