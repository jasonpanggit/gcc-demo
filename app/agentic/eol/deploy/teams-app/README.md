# Teams App Package for MCP Orchestrator Bot

This directory contains the Teams app manifest and icons needed to install the bot in Microsoft Teams.

## Files Required

- `manifest.json` - Teams app manifest (✅ included)
- `color.png` - 192x192 color icon (⚠️ needs to be created)
- `outline.png` - 32x32 outline icon (⚠️ needs to be created)

## Quick Setup

### Option 1: Use Placeholder Icons (Fast)

If you just want to test the bot quickly, you can use any PNG images:

```bash
cd /Users/jasonmba/Library/CloudStorage/OneDrive-Microsoft/workspace/gcc-demo/app/agentic/eol/deploy/teams-app

# Create simple color icon (192x192)
# You can use any image editor or download an Azure icon from:
# https://docs.microsoft.com/en-us/azure/architecture/icons/

# Create simple outline icon (32x32)
# This should be a simple line drawing version
```

### Option 2: Generate Icons with ImageMagick

```bash
cd /Users/jasonmba/Library/CloudStorage/OneDrive-Microsoft/workspace/gcc-demo/app/agentic/eol/deploy/teams-app

# Install ImageMagick if not already installed
# macOS: brew install imagemagick

# Create color icon (192x192) - Blue background with white text
convert -size 192x192 xc:'#0078D4' \
  -gravity center \
  -pointsize 120 \
  -fill white \
  -font Arial-Bold \
  -annotate +0+0 'MCP' \
  color.png

# Create outline icon (32x32) - Transparent background with blue text
convert -size 32x32 xc:transparent \
  -gravity center \
  -pointsize 20 \
  -fill '#0078D4' \
  -font Arial-Bold \
  -annotate +0+0 'M' \
  outline.png
```

### Option 3: Download Azure Icons

1. Go to https://docs.microsoft.com/en-us/azure/architecture/icons/
2. Download an appropriate Azure service icon (e.g., Container Apps, Logic Apps)
3. Resize to 192x192 for color.png
4. Create a 32x32 outline version for outline.png

## Create App Package

Once you have all three files (manifest.json, color.png, outline.png):

```bash
cd /Users/jasonmba/Library/CloudStorage/OneDrive-Microsoft/workspace/gcc-demo/app/agentic/eol/deploy/teams-app

# Create the Teams app package
zip -r mcp-orchestrator-teams-app.zip manifest.json color.png outline.png

# Verify the package
unzip -l mcp-orchestrator-teams-app.zip
```

## Install in Teams

### Method 1: Direct Upload (Recommended)

1. Open Microsoft Teams
2. Click **Apps** in the left sidebar
3. Click **Manage your apps** (or **Upload an app** if available)
4. Click **Upload a custom app**
5. Select the `mcp-orchestrator-teams-app.zip` file
6. Click **Add** to install for yourself, or **Add to a team** to install for a team

### Method 2: Via Azure Portal

1. Go to Azure Portal → Your bot resource: `mcp-orchestrator-bot`
2. Click **Channels** → **Microsoft Teams**
3. Click **Open in Teams** button
4. This will use the manifest from Azure Bot Service (may be different from custom manifest)

## Troubleshooting Manifest Errors

### "Manifest parsing error"

This usually means:
- Missing or invalid manifest.json
- Missing icon files (color.png or outline.png)
- Icon files not in correct size (192x192 and 32x32)
- Invalid Bot ID in manifest

**Solution:**
1. Verify all three files exist in the zip
2. Check manifest.json is valid JSON (use jsonlint.com)
3. Verify bot ID matches: `bd0f04dc-9706-4111-a4fc-54c4c11a58b6`
4. Check icon sizes: `file color.png` should show 192x192, `file outline.png` should show 32x32

### "Bot not found" error

This means the Bot ID in manifest.json doesn't match the Azure Bot Service registration.

**Solution:**
- Verify `id` and `botId` in manifest.json match: `bd0f04dc-9706-4111-a4fc-54c4c11a58b6`
- Check Azure Portal → Bot resource → Configuration → Microsoft App ID

### "App not available in this tenant"

This means the bot's Microsoft App registration is not accessible in your tenant.

**Solution:**
- Verify the app registration is set to "Multi Tenant"
- Check Azure Portal → App Registrations → Search for `bd0f04dc-9706-4111-a4fc-54c4c11a58b6`
- Ensure "Supported account types" is set to "Accounts in any organizational directory"

## Testing the Bot

Once installed, try these commands:

```
Hello
```
```
List my resource groups
```
```
Show all container apps
```
```
Check health of my container app
```
```
Get performance metrics for /subscriptions/a87a8e64-a52a-4aa8-a760-5e8919d23cd1/resourceGroups/rg-gcc-demo/providers/Microsoft.App/containerapps/azure-agentic-platform-vnet
```

## App Manifest Schema

The manifest follows the Microsoft Teams app schema v1.16:
- Schema: https://developer.microsoft.com/en-us/json-schemas/teams/v1.16/MicrosoftTeams.schema.json
- Documentation: https://docs.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema

## Security Notes

- The bot only responds to authenticated Teams users
- All requests are verified using HMAC signature (if configured)
- Webhook endpoint: `https://azure-agentic-platform-vnet.jollywater-179e4f4a.australiaeast.azurecontainerapps.io/api/teams-bot/messages`
- Bot credentials are stored securely in Container App environment variables
