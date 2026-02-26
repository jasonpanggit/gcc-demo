/**
 * Resource Inventory Monitoring Dashboard
 *
 * Provides real-time cache performance charts, resource distribution
 * visualisations, discovery status indicators, and trend analysis.
 *
 * Data sources:
 *   /api/resource-inventory/stats           (cache statistics)
 *   /api/resource-inventory/metrics?detail=true  (full monitoring metrics)
 *   /healthz/inventory                      (health check)
 *
 * Charts: Chart.js (loaded via CDN in the HTML template)
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const DASHBOARD_CONFIG = {
    pollIntervalMs: 15000,      // refresh every 15s
    historyMaxPoints: 30,       // keep last 30 data points in time-series
    apiBase: '/api/resource-inventory',
    healthEndpoint: '/healthz/inventory',
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let pollTimer = null;
let cacheHitChart = null;
let resourceDistChart = null;
let locationDistChart = null;

// Time-series history (ring buffers)
const history = {
    labels: [],
    l1HitRate: [],
    l2HitRate: [],
    missRate: [],
    totalRequests: [],
};

// ---------------------------------------------------------------------------
// Colour palette (Azure-inspired)
// ---------------------------------------------------------------------------
const COLORS = {
    l1:       'rgba(0, 120, 212, 0.85)',    // Azure blue
    l2:       'rgba(0, 163, 108, 0.85)',    // Green
    miss:     'rgba(233, 113, 50, 0.7)',    // Orange
    grid:     'rgba(0, 0, 0, 0.06)',
    text:     '#6c757d',
    healthy:  '#198754',
    degraded: '#ffc107',
    error:    '#dc3545',
    types: [
        '#0078D4', '#00A36C', '#E97132', '#512BD4', '#326CE5',
        '#0D9748', '#CC2927', '#FFB900', '#005F9E', '#7B2D8E',
        '#0078D4',
    ],
};

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
function initDashboard() {
    createCacheHitChart();
    createResourceDistChart();
    createLocationDistChart();
    refreshDashboard();
    startPolling();
}

// Auto-init when DOM is ready (called from HTML)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDashboard);
} else {
    initDashboard();
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(refreshDashboard, DASHBOARD_CONFIG.pollIntervalMs);
}

function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ---------------------------------------------------------------------------
// Data fetch
// ---------------------------------------------------------------------------
async function fetchStats() {
    try {
        const resp = await fetch(`${DASHBOARD_CONFIG.apiBase}/stats`);
        return await resp.json();
    } catch (err) {
        console.error('Dashboard stats fetch error:', err);
        return { success: false, error: err.message };
    }
}

async function fetchHealth() {
    try {
        const resp = await fetch(DASHBOARD_CONFIG.healthEndpoint);
        return await resp.json();
    } catch (err) {
        return { success: false, error: err.message };
    }
}

async function fetchMetrics() {
    try {
        const resp = await fetch(`${DASHBOARD_CONFIG.apiBase}/metrics?detail=true`);
        return await resp.json();
    } catch (err) {
        console.error('Dashboard metrics fetch error:', err);
        return { success: false, error: err.message };
    }
}

// ---------------------------------------------------------------------------
// Main refresh loop
// ---------------------------------------------------------------------------
async function refreshDashboard() {
    const [statsResult, healthResult, metricsResult] = await Promise.all([
        fetchStats(), fetchHealth(), fetchMetrics()
    ]);

    const hasMetrics = metricsResult.success && metricsResult.data && metricsResult.data.cache;

    // Use stats endpoint for L1 entry counts and as fallback for cache metrics
    if (statsResult.success && statsResult.data) {
        updateCacheMetrics(statsResult.data, hasMetrics);
    }

    if (healthResult.success && healthResult.data) {
        updateHealthIndicators(healthResult.data);
    }

    // Integrate real monitoring metrics from InventoryMetrics (Task #20)
    if (hasMetrics) {
        const m = metricsResult.data;

        // Update cache time-series with precise hit rates from metrics
        updateCacheMetricsFromMonitoring(m.cache);

        // Update resource distribution chart with real per-type counts
        if (m.resources && m.resources.by_type) {
            updateExternalMetrics({
                per_type_counts: m.resources.by_type,
                api_call_reduction_percent: m.cache
                    ? Math.round((m.cache.api_calls_saved / Math.max(m.cache.api_calls_saved + m.cache.l1_misses + m.cache.l2_misses, 1)) * 100)
                    : undefined,
            });
        }

        // Update discovery metrics
        updateDiscoveryMetrics(m.discovery || {});

        // Update performance panel with real data
        updatePerformanceMetrics(m);
    }

    updateTimestamp();
}

// ---------------------------------------------------------------------------
// Cache performance metrics
// ---------------------------------------------------------------------------
function updateCacheMetrics(data, skipTimeSeries) {
    const cache = data.cache || {};
    const l1Rate = cache.l1_hit_rate_percent || 0;
    const l2Rate = cache.l2_hit_rate_percent || 0;
    const missRate = cache.miss_rate_percent || 0;
    const totalReqs = cache.total_requests || 0;
    const writes = cache.writes || 0;
    const hitRate = cache.hit_rate_percent || 0;

    // Always update L1 entry counts (only available from stats endpoint)
    setText('dash-l1-entries', cache.l1_entries || 0);
    setText('dash-l1-valid', cache.l1_valid_entries || 0);

    // Update other stat cards only if metrics endpoint didn't provide data
    if (!skipTimeSeries) {
        setText('dash-hit-rate', `${hitRate}%`);
        setText('dash-total-reqs', totalReqs);
        setText('dash-writes', writes);
        setText('dash-miss-rate', `${missRate}%`);

        // Push to time-series (only if metrics endpoint isn't providing data)
        const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        pushHistory('labels', now);
        pushHistory('l1HitRate', l1Rate);
        pushHistory('l2HitRate', l2Rate);
        pushHistory('missRate', missRate);
        pushHistory('totalRequests', totalReqs);

        // Redraw chart
        if (cacheHitChart) {
            cacheHitChart.data.labels = history.labels;
            cacheHitChart.data.datasets[0].data = history.l1HitRate;
            cacheHitChart.data.datasets[1].data = history.l2HitRate;
            cacheHitChart.data.datasets[2].data = history.missRate;
            cacheHitChart.update('none');
        }
    }
}

// ---------------------------------------------------------------------------
// Resource distribution (uses real per-type counts from monitoring metrics)
// ---------------------------------------------------------------------------
function updateResourceCounts(data) {
    // Fallback: if metrics endpoint hasn't provided per-type counts yet,
    // show L1 valid/expired breakdown from stats endpoint
    const cache = data.cache || {};
    const l1 = cache.l1_entries || 0;
    const l1Valid = cache.l1_valid_entries || 0;
    const l1Expired = l1 - l1Valid;

    // Only update doughnut if we haven't received real per-type data
    if (resourceDistChart && !resourceDistChart._hasRealData) {
        resourceDistChart.data.datasets[0].data = [l1Valid, l1Expired];
        resourceDistChart.update('none');
    }
}

// ---------------------------------------------------------------------------
// Monitoring metrics integration (from /api/resource-inventory/metrics)
// ---------------------------------------------------------------------------

/**
 * Update cache time-series chart with precise hit rates from InventoryMetrics.
 * These rates are computed from actual l1_hits/l1_misses/l2_hits/l2_misses
 * counters, making them more accurate than the stats endpoint approximations.
 */
function updateCacheMetricsFromMonitoring(cache) {
    const l1Rate = Math.round((cache.l1_hit_rate || 0) * 100);
    const l2Rate = Math.round((cache.l2_hit_rate || 0) * 100);
    const overallRate = Math.round((cache.overall_hit_rate || 0) * 100);

    // Compute miss rate: 100% - overall hit rate
    const missRate = 100 - overallRate;

    const totalReqs = (cache.l1_hits || 0) + (cache.l1_misses || 0)
                    + (cache.l2_hits || 0) + (cache.l2_misses || 0);
    const writes = cache.total_sets || 0;

    // Update metric cards with real data
    setText('dash-hit-rate', `${overallRate}%`);
    setText('dash-total-reqs', totalReqs);
    setText('dash-writes', writes);
    setText('dash-miss-rate', `${missRate}%`);

    // Push to time-series
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    pushHistory('labels', now);
    pushHistory('l1HitRate', l1Rate);
    pushHistory('l2HitRate', l2Rate);
    pushHistory('missRate', missRate);
    pushHistory('totalRequests', totalReqs);

    // Redraw chart
    if (cacheHitChart) {
        cacheHitChart.data.labels = history.labels;
        cacheHitChart.data.datasets[0].data = history.l1HitRate;
        cacheHitChart.data.datasets[1].data = history.l2HitRate;
        cacheHitChart.data.datasets[2].data = history.missRate;
        cacheHitChart.update('none');
    }
}

/**
 * Update discovery-related metric displays.
 */
function updateDiscoveryMetrics(discovery) {
    setText('dash-discovery-count', discovery.total_discoveries || 0);
    setText('dash-discovery-success-rate',
        discovery.success_rate !== undefined
            ? `${Math.round(discovery.success_rate * 100)}%`
            : '--'
    );
    setText('dash-discovery-avg-duration',
        discovery.avg_duration_seconds !== undefined
            ? `${discovery.avg_duration_seconds}s`
            : '--'
    );
    setText('dash-last-discovery',
        discovery.last_discovery
            ? new Date(discovery.last_discovery).toLocaleTimeString()
            : '--'
    );
    setText('dash-last-discovery-status',
        discovery.last_status
            ? discovery.last_status.charAt(0).toUpperCase() + discovery.last_status.slice(1)
            : '--'
    );

    // Color the status indicator
    const statusEl = document.getElementById('dash-last-discovery-status');
    if (statusEl && discovery.last_status) {
        statusEl.style.color = discovery.last_status === 'success' ? COLORS.healthy : COLORS.error;
        statusEl.style.fontWeight = '600';
    }
}

/**
 * Update the Performance panel with real metrics data.
 * - API call reduction = api_calls_saved as percentage of total operations
 * - Query performance stats
 */
function updatePerformanceMetrics(m) {
    const cache = m.cache || {};
    const queries = m.queries || {};
    const resources = m.resources || {};

    // API calls saved
    if (cache.api_calls_saved !== undefined) {
        setText('dash-api-reduction', `${cache.api_calls_saved} calls saved`);
    }

    // Total queries
    if (queries.total_queries !== undefined) {
        setText('dash-param-rate', `${queries.total_queries} queries`);
    }

    // Update total resources and subscription count
    if (resources.total_resources !== undefined) {
        setText('dash-total-resources', resources.total_resources);
    }
    if (resources.subscriptions !== undefined) {
        setText('dash-subscription-count', resources.subscriptions);
    }
}

// ---------------------------------------------------------------------------
// Health indicators
// ---------------------------------------------------------------------------
function updateHealthIndicators(data) {
    const status = data.status || 'unknown';
    const engineOk = data.engine_available || false;
    const l2Ready = (data.cache || {}).l2_ready || false;
    const cfg = data.config || {};

    // Status badge
    const el = document.getElementById('dash-health-status');
    if (el) {
        const color = status === 'healthy' ? COLORS.healthy
                    : status === 'degraded' ? COLORS.degraded
                    : COLORS.error;
        el.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        el.style.color = color;
        el.style.fontWeight = '700';
    }

    setText('dash-engine-status', engineOk ? 'Online' : 'Offline');
    setIndicator('dash-engine-dot', engineOk);
    setText('dash-l2-status', l2Ready ? 'Connected' : 'Offline');
    setIndicator('dash-l2-dot', l2Ready);

    // Config display
    setText('dash-scan-schedule', cfg.full_scan_schedule || '--');
    setText('dash-incr-interval', cfg.incremental_interval_min ? `${cfg.incremental_interval_min} min` : '--');
    setText('dash-l1-ttl', cfg.default_l1_ttl ? `${cfg.default_l1_ttl}s` : '--');
    setText('dash-l2-ttl', cfg.default_l2_ttl ? `${cfg.default_l2_ttl}s` : '--');
}

// ---------------------------------------------------------------------------
// Chart creation
// ---------------------------------------------------------------------------
function createCacheHitChart() {
    const ctx = document.getElementById('cache-hit-chart');
    if (!ctx) return;

    cacheHitChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'L1 Hit %',
                    data: [],
                    borderColor: COLORS.l1,
                    backgroundColor: 'rgba(0, 120, 212, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                },
                {
                    label: 'L2 Hit %',
                    data: [],
                    borderColor: COLORS.l2,
                    backgroundColor: 'rgba(0, 163, 108, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                },
                {
                    label: 'Miss %',
                    data: [],
                    borderColor: COLORS.miss,
                    backgroundColor: 'rgba(233, 113, 50, 0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                    borderDash: [4, 4],
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
                title: { display: true, text: 'Cache Hit Rate Over Time', font: { size: 13 } },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { callback: v => `${v}%`, font: { size: 10 } },
                    grid: { color: COLORS.grid },
                },
                x: {
                    ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { size: 10 } },
                    grid: { display: false },
                },
            },
        },
    });
}

function createResourceDistChart() {
    const ctx = document.getElementById('resource-dist-chart');
    if (!ctx) return;

    resourceDistChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Valid', 'Expired'],
            datasets: [{
                data: [0, 0],
                backgroundColor: [COLORS.l1, COLORS.miss],
                borderWidth: 1,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
                title: { display: true, text: 'L1 Cache Entries', font: { size: 13 } },
            },
        },
    });
}

function createLocationDistChart() {
    const ctx = document.getElementById('location-dist-chart');
    if (!ctx) return;

    locationDistChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['eastus', 'westus2', 'westeurope', 'southeastasia'],
            datasets: [{
                label: 'Resources',
                data: [0, 0, 0, 0],
                backgroundColor: COLORS.types.slice(0, 4),
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'Resources by Location', font: { size: 13 } },
            },
            scales: {
                x: { beginAtZero: true, grid: { color: COLORS.grid }, ticks: { font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { font: { size: 11 } } },
            },
        },
    });
}

// ---------------------------------------------------------------------------
// External metrics integration (fed from InventoryMetrics via /metrics API)
// ---------------------------------------------------------------------------

/**
 * Update charts and indicators with real monitoring data.
 *
 * Called by refreshDashboard() with data derived from InventoryMetrics.
 * Shape:
 * {
 *   api_call_reduction_percent: number,      // from cache.api_calls_saved
 *   param_auto_populate_rate: number,         // optional
 *   prometheus_scrape_ok: boolean,            // optional
 *   azure_monitor_connected: boolean,         // optional
 *   per_type_counts: { "Microsoft.Compute/virtualMachines": 42, ... },
 *   per_location_counts: { "eastus": 100, "westus2": 50, ... },
 * }
 */
function updateExternalMetrics(metrics) {
    if (!metrics) return;

    // API call reduction
    if (metrics.api_call_reduction_percent !== undefined) {
        setText('dash-api-reduction', `${metrics.api_call_reduction_percent}%`);
    }

    // Parameter auto-population success rate
    if (metrics.param_auto_populate_rate !== undefined) {
        setText('dash-param-rate', `${metrics.param_auto_populate_rate}%`);
    }

    // External monitoring status
    setIndicator('dash-prometheus-dot', metrics.prometheus_scrape_ok);
    setIndicator('dash-azure-monitor-dot', metrics.azure_monitor_connected);

    // Per-type resource counts → resource dist chart (replaces Valid/Expired placeholder)
    if (metrics.per_type_counts && resourceDistChart) {
        const labels = Object.keys(metrics.per_type_counts);
        const values = Object.values(metrics.per_type_counts);
        if (labels.length > 0) {
            resourceDistChart.data.labels = labels.map(shortTypeName);
            resourceDistChart.data.datasets[0].data = values;
            resourceDistChart.data.datasets[0].backgroundColor = COLORS.types.slice(0, labels.length);
            resourceDistChart._hasRealData = true;  // prevent fallback overwrite
            // Update chart title to reflect real data
            resourceDistChart.options.plugins.title.text = 'Resources by Type';
            resourceDistChart.update('none');
        }
    }

    // Per-location counts → location bar chart
    if (metrics.per_location_counts && locationDistChart) {
        const labels = Object.keys(metrics.per_location_counts);
        const values = Object.values(metrics.per_location_counts);
        locationDistChart.data.labels = labels;
        locationDistChart.data.datasets[0].data = values;
        locationDistChart.data.datasets[0].backgroundColor = COLORS.types.slice(0, labels.length);
        locationDistChart.update('none');
    }
}

function shortTypeName(fullType) {
    const parts = (fullType || '').split('/');
    return parts.length > 1 ? parts[1] : fullType;
}

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setIndicator(id, ok) {
    const el = document.getElementById(id);
    if (el) {
        el.style.backgroundColor = ok ? COLORS.healthy : COLORS.error;
    }
}

function pushHistory(key, value) {
    history[key].push(value);
    if (history[key].length > DASHBOARD_CONFIG.historyMaxPoints) {
        history[key].shift();
    }
}

function updateTimestamp() {
    setText('dash-last-updated', new Date().toLocaleTimeString());
}

// ---------------------------------------------------------------------------
// Manual controls (bound from HTML)
// ---------------------------------------------------------------------------
function toggleDashboardPolling() {
    if (pollTimer) {
        stopPolling();
        setText('dash-poll-btn-text', 'Start Auto-Refresh');
    } else {
        startPolling();
        refreshDashboard();
        setText('dash-poll-btn-text', 'Stop Auto-Refresh');
    }
}

function forceRefreshDashboard() {
    refreshDashboard();
}
