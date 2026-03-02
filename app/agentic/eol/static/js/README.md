# Frontend JavaScript

Client-side JavaScript for dashboards, chat/assistant UI, analytics views, and shared utilities.

## Structure

- Core scripts in this folder (UI pages and shared behavior)
- ES module variants in `modules/`
- Build/validation helpers: `build.sh`, `performance-budget.json`

## Validate bundle/size checks

From this folder:

```bash
./build.sh
```

Use module files for new JS work where possible; keep compatibility with existing page script loading patterns.
