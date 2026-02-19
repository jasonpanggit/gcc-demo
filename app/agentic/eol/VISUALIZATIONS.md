# Data Visualizations - Task #6

**Enhanced data visualizations with charts and graphs for the EOL Agentic Platform**

---

## Overview

This task implements comprehensive data visualization enhancements using Chart.js with design tokens, sparklines, agent metrics dashboards, token usage analytics, and EOL risk heatmaps.

---

## Components Created

### 1. Chart.js Theme (`static/js/chart-theme.js`)

Applies design tokens from `design-tokens.css` to all Chart.js visualizations for consistent styling.

**Features:**
- Extracts CSS custom properties from design tokens
- Provides color palette (primary, success, warning, error, agent-specific)
- Typography settings from design system
- Default chart configurations (responsive, accessible)
- Helper functions: `applyChartTheme()`, `getChartColor()`, `createChartGradient()`

**Usage:**
```javascript
const myChart = new Chart(ctx, applyChartTheme({
    type: 'line',
    data: chartData,
    options: customOptions
}));
```

**Exports:**
- `ChartColors` - Color palette object
- `ChartTypography` - Font settings
- `ChartTheme` - Default configuration
- `ChartPresets` - Common chart type presets
- `applyChartTheme()` - Apply theme to config
- `getChartColor()` - Get color from palette by index
- `createChartGradient()` - Generate gradient for backgrounds

---

### 2. Sparklines (`static/js/sparklines.js`)

Lightweight SVG-based inline charts for tables and compact dashboards. No dependencies.

**Features:**
- Four chart types: line, area, bar, trend
- Auto-initialization via data attributes
- Accessible (ARIA labels)
- Interactive tooltips
- Responsive sizing

**Usage:**
```html
<!-- Declarative -->
<span class="sparkline"
      data-values="[1,5,2,8,3,7,4]"
      data-type="line"
      data-height="40"
      data-width="150"></span>

<!-- Programmatic -->
<script>
Sparklines.create(element, {
    values: [1, 5, 2, 8, 3],
    type: 'bar',
    color: '#0078d4'
});
</script>
```

**API:**
- `Sparklines.init()` - Auto-initialize all sparklines
- `Sparklines.create(element, options)` - Create sparkline
- `Sparklines.update(element, newValues)` - Update existing

---

### 3. EOL Risk Heatmap (`templates/components/eol_heatmap.html`)

Color-coded visualization of End-of-Life risk across resources.

**Features:**
- Five risk levels (Critical, High, Medium, Low, Safe)
- Color-coded based on days to EOL
- Sortable and filterable
- Accessible (ARIA labels, semantic HTML)
- Responsive design

**Risk Thresholds:**
- Critical: < 30 days (red)
- High: 30-90 days (orange)
- Medium: 90-180 days (cyan)
- Low: 180-365 days (green)
- Safe: > 365 days (blue)

**Usage:**
```html
{% include 'components/eol_heatmap.html' %}

<div id="heatmap-container"></div>

<script>
EOLHeatmap.init('heatmap-container', {
    data: [
        { name: 'Windows Server 2012', vendor: 'Microsoft', daysToEOL: 15, type: 'OS' },
        { name: 'Ubuntu 18.04', vendor: 'Ubuntu', daysToEOL: 180, type: 'OS' }
    ],
    title: 'EOL Risk Analysis',
    showLegend: true
});
</script>
```

**API:**
- `EOLHeatmap.init(containerId, options)` - Initialize heatmap
- `EOLHeatmap.update(containerId, newData)` - Update with new data
- `EOLHeatmap.renderLoading(container)` - Show loading state
- `EOLHeatmap.getRiskLevel(daysToEOL)` - Get risk level object
- `EOLHeatmap.formatDays(days)` - Format days to readable string

---

### 4. Agent Metrics Dashboard (`static/js/agent-metrics-dashboard.js`)

Real-time performance monitoring for AI agents.

**Features:**
- Summary metric cards with sparklines
- Response time trends (line chart)
- Success vs failure distribution (doughnut chart)
- Agent activity breakdown (horizontal bar chart)
- Token usage over time (stacked area chart)
- Auto-refresh capability
- Export chart functionality

**Usage:**
```html
<div id="agent-metrics-dashboard"></div>

<script>
AgentMetrics.init('agent-metrics-dashboard', {
    refreshInterval: 30000,  // 30 seconds
    apiEndpoint: '/api/agents/metrics'
});
</script>
```

**API:**
- `AgentMetrics.init(containerId, options)` - Initialize dashboard
- `AgentMetrics.refresh(containerId)` - Manual refresh
- `AgentMetrics.exportChart(chartId)` - Export chart as PNG
- `AgentMetrics.destroy()` - Cleanup and destroy

**Expected API Response:**
```json
{
    "totalRequests": 1547,
    "successfulRequests": 1423,
    "failedRequests": 124,
    "avgResponseTime": 342,
    "activeAgents": 8,
    "timeLabels": ["00:00", "04:00", "08:00"],
    "responseTimeHistory": [280, 310, 295],
    "agentActivity": [
        { "name": "MCP Orchestrator", "requests": 450 }
    ]
}
```

---

### 5. Token Usage Visualization (`static/js/token-usage-viz.js`)

Track AI model token consumption with cost estimates.

**Features:**
- Summary cards (total, input, output, cost)
- Period selector (1h, 24h, 7d, 30d)
- Token usage timeline (stacked area chart)
- Token distribution pie chart
- Usage by agent (horizontal stacked bar)
- Detailed cost breakdown table with sparklines
- Cost estimation based on model pricing

**Usage:**
```html
<div id="token-usage-viz"></div>

<script>
TokenUsageViz.init('token-usage-viz', {
    period: '24h',
    refreshInterval: 60000,  // 1 minute
    apiEndpoint: '/api/agents/token-usage'
});
</script>
```

**API:**
- `TokenUsageViz.init(containerId, options)` - Initialize visualization
- `TokenUsageViz.refresh(containerId)` - Manual refresh
- `TokenUsageViz.destroy()` - Cleanup
- `TokenUsageViz.calculateCost(inputTokens, outputTokens, model)` - Calculate cost

**Expected API Response:**
```json
{
    "totalInputTokens": 125000,
    "totalOutputTokens": 87000,
    "changePercent": 12.5,
    "model": "gpt-4o-mini",
    "timeLabels": ["Mon", "Tue", "Wed"],
    "inputTokenHistory": [15000, 18000, 22000],
    "outputTokenHistory": [10000, 12000, 15000],
    "agentTokens": [
        {
            "name": "MCP Orchestrator",
            "inputTokens": 45000,
            "outputTokens": 32000,
            "trend": [8000, 9000, 8500]
        }
    ]
}
```

---

### 6. Chart Components CSS (`static/css/chart-components.css`)

Styles for all visualization components.

**Features:**
- Metric card styles with hover effects
- Chart container layouts
- Loading and error states
- Responsive design (mobile, tablet, desktop)
- Accessibility (focus states, screen reader support)
- Print styles
- High contrast mode support

---

### 7. Visualizations Demo Page (`templates/visualizations.html`)

Comprehensive showcase of all visualization components with live examples and code samples.

**URL:** `/visualizations`

**Sections:**
1. Sparklines demo (line, area, bar, trend)
2. EOL Risk Heatmap with sample data
3. Agent Metrics Dashboard with mock data
4. Token Usage Analytics with mock data
5. Chart Theme Examples (line, bar, doughnut, stacked area)

---

## Files Modified

### `api/ui.py`
- Added `/visualizations` route
- Updated module docstring

### `templates/base.html`
- Added "Data Visualizations" link to navigation menu

---

## Design System Integration

All components use CSS custom properties from `design-tokens.css`:

**Colors:**
- `--color-primary` (#0078d4)
- `--color-success` (#0a8754)
- `--color-warning` (#f59e0b)
- `--color-error` (#dc2626)
- `--color-info` (#0891b2)
- Agent-specific colors (`--agent-mcp`, `--agent-sre`, etc.)

**Typography:**
- `--font-family-base`
- `--font-size-*` (xs, sm, base, lg, xl, 2xl, 3xl)
- `--font-weight-*` (normal, medium, semibold, bold)

**Spacing:**
- `--spacing-*` (xs, sm, md, lg, xl, 2xl, 3xl)

**Other:**
- `--radius-*` (border radius)
- `--shadow-*` (box shadows)
- `--transition-*` (animations)

---

## Accessibility Features

All components follow WCAG 2.1 AA guidelines:

1. **Semantic HTML** - Proper element roles and structure
2. **ARIA Labels** - Descriptive labels for charts and interactive elements
3. **Keyboard Navigation** - Full keyboard support
4. **Focus Indicators** - Visible focus states
5. **Color Contrast** - Meets AA standards
6. **Screen Reader Support** - Accessible text alternatives
7. **Responsive Design** - Works on all screen sizes
8. **High Contrast Mode** - Enhanced for users with visual impairments

---

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

---

## Performance Considerations

1. **Chart.js** - Loaded from CDN with caching
2. **Sparklines** - Pure JavaScript, no dependencies, minimal overhead
3. **Lazy Loading** - Charts initialized on page load, not server-side
4. **Auto-refresh** - Configurable intervals to balance freshness vs. load
5. **Responsive Charts** - `maintainAspectRatio: true` for proper scaling

---

## Testing

To test the visualizations:

1. Start the application:
   ```bash
   cd app/agentic/eol
   source ../../../.venv/bin/activate
   uvicorn main:app --reload
   ```

2. Navigate to: `http://localhost:8000/visualizations`

3. Test features:
   - Period selector in token usage
   - Chart export buttons
   - Responsive design (resize browser)
   - Keyboard navigation
   - Screen reader compatibility

---

## Future Enhancements

Potential improvements for future tasks:

1. **Real-time Updates** - WebSocket integration for live data
2. **Dark Mode** - Dark theme variant (Task #7)
3. **More Chart Types** - Radar, scatter, bubble charts
4. **Data Export** - CSV/Excel export for tables
5. **Custom Dashboards** - User-configurable dashboards
6. **Drill-down** - Click charts to see detailed views
7. **Comparison Mode** - Compare metrics across time periods
8. **Alerts Integration** - Visual alerts on charts

---

## Dependencies

- **Chart.js 4.4.1** - Charting library (CDN)
- **Font Awesome 6.4.0** - Icons (already included)
- **Bootstrap 5.3.0** - Grid and utilities (already included)
- **Design Tokens** - CSS custom properties

---

## Version

- **Version:** 1.0.0
- **Task:** #6 - Enhanced Data Visualizations
- **Date:** 2026-02-19
- **Author:** Claude Opus 4.6

---

## References

- Chart.js Documentation: https://www.chartjs.org/docs/latest/
- Design Tokens: `static/css/design-tokens.css`
- WCAG 2.1 Guidelines: https://www.w3.org/WAI/WCAG21/quickref/
