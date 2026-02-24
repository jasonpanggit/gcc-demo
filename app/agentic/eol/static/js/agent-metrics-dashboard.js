/**
 * Agent Metrics Dashboard
 *
 * Enhanced visualizations for agent performance metrics including:
 * - Response time trends
 * - Success/failure rates
 * - Agent activity distribution
 * - Token usage over time
 *
 * Requires: Chart.js 4.x, chart-theme.js
 *
 * Usage:
 *   <div id="agent-metrics-dashboard"></div>
 *   <script>AgentMetrics.init('agent-metrics-dashboard');</script>
 *
 * Version: 1.0.0
 */

const AgentMetrics = (function() {
    'use strict';

    // Configuration
    const config = {
        refreshInterval: 30000, // 30 seconds
        maxDataPoints: 20,
        apiEndpoint: '/api/agents/metrics',
    };

    let charts = {};
    let refreshTimer = null;

    /**
     * Initialize the agent metrics dashboard
     */
    async function init(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`AgentMetrics: Container "${containerId}" not found`);
            return;
        }

        const settings = { ...config, ...options };

        // Render dashboard structure
        renderDashboard(container);

        // Load initial data
        await refresh(containerId);

        // Start auto-refresh
        if (settings.refreshInterval > 0) {
            refreshTimer = setInterval(() => refresh(containerId), settings.refreshInterval);
        }
    }

    /**
     * Render dashboard HTML structure
     */
    function renderDashboard(container) {
        container.innerHTML = `
            <div class="agent-metrics-dashboard">
                <!-- Summary Cards -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <div class="metric-label">Total Requests</div>
                                        <div class="metric-value" id="metric-total-requests">--</div>
                                    </div>
                                    <div class="metric-icon bg-primary">
                                        <i class="fas fa-chart-line"></i>
                                    </div>
                                </div>
                                <div class="metric-sparkline" id="sparkline-requests"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <div class="metric-label">Success Rate</div>
                                        <div class="metric-value text-success" id="metric-success-rate">--</div>
                                    </div>
                                    <div class="metric-icon bg-success">
                                        <i class="fas fa-check-circle"></i>
                                    </div>
                                </div>
                                <div class="metric-sparkline" id="sparkline-success"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <div class="metric-label">Avg Response</div>
                                        <div class="metric-value text-info" id="metric-avg-response">--</div>
                                    </div>
                                    <div class="metric-icon bg-info">
                                        <i class="fas fa-clock"></i>
                                    </div>
                                </div>
                                <div class="metric-sparkline" id="sparkline-response"></div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <div class="metric-label">Active Agents</div>
                                        <div class="metric-value text-primary" id="metric-active-agents">--</div>
                                    </div>
                                    <div class="metric-icon bg-warning">
                                        <i class="fas fa-robot"></i>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Charts Row 1 -->
                <div class="row mb-4">
                    <div class="col-lg-8">
                        <div class="card">
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-area me-2"></i>Response Time Trends
                                </h5>
                                <button class="btn btn-sm btn-outline-secondary" onclick="AgentMetrics.exportChart('response-time-chart')">
                                    <i class="fas fa-download"></i>
                                </button>
                            </div>
                            <div class="card-body">
                                <canvas id="response-time-chart" aria-label="Response time trend chart"></canvas>
                            </div>
                        </div>
                    </div>
                    <div class="col-lg-4">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-pie me-2"></i>Success vs Failures
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="success-failure-chart" aria-label="Success vs failure distribution"></canvas>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Charts Row 2 -->
                <div class="row mb-4">
                    <div class="col-lg-6">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-robot me-2"></i>Agent Activity Distribution
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="agent-activity-chart" aria-label="Agent activity distribution"></canvas>
                            </div>
                        </div>
                    </div>
                    <div class="col-lg-6">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-coins me-2"></i>Token Usage Over Time
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="token-usage-chart" aria-label="Token usage over time"></canvas>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Fetch metrics data from API
     */
    async function fetchMetrics() {
        try {
            const response = await fetch(config.apiEndpoint);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            return data.success ? data.data : null;
        } catch (error) {
            console.error('Error fetching agent metrics:', error);
            return null;
        }
    }

    /**
     * Refresh dashboard with new data
     */
    async function refresh(containerId) {
        const data = await fetchMetrics();
        if (!data) {
            console.warn('No metrics data available');
            return;
        }

        updateSummaryCards(data);
        updateCharts(data);
    }

    /**
     * Update summary metric cards
     */
    function updateSummaryCards(data) {
        // Total requests
        const totalEl = document.getElementById('metric-total-requests');
        if (totalEl) {
            totalEl.textContent = formatNumber(data.totalRequests || 0);
        }

        // Success rate
        const successRateEl = document.getElementById('metric-success-rate');
        if (successRateEl) {
            const rate = data.totalRequests > 0
                ? ((data.successfulRequests / data.totalRequests) * 100).toFixed(1)
                : 0;
            successRateEl.textContent = `${rate}%`;
        }

        // Average response time
        const avgResponseEl = document.getElementById('metric-avg-response');
        if (avgResponseEl) {
            avgResponseEl.textContent = `${(data.avgResponseTime || 0).toFixed(0)}ms`;
        }

        // Active agents
        const activeEl = document.getElementById('metric-active-agents');
        if (activeEl) {
            activeEl.textContent = data.activeAgents || 0;
        }

        // Update sparklines
        if (typeof Sparklines !== 'undefined') {
            if (data.requestsHistory) {
                const sparklineEl = document.getElementById('sparkline-requests');
                if (sparklineEl) {
                    Sparklines.create(sparklineEl, {
                        values: data.requestsHistory,
                        type: 'area',
                        color: ChartColors?.primary || '#0078d4',
                        height: 40,
                        width: 150
                    });
                }
            }

            if (data.successRateHistory) {
                const sparklineEl = document.getElementById('sparkline-success');
                if (sparklineEl) {
                    Sparklines.create(sparklineEl, {
                        values: data.successRateHistory,
                        type: 'line',
                        color: ChartColors?.success || '#0a8754',
                        height: 40,
                        width: 150
                    });
                }
            }

            if (data.responseTimeHistory) {
                const sparklineEl = document.getElementById('sparkline-response');
                if (sparklineEl) {
                    Sparklines.create(sparklineEl, {
                        values: data.responseTimeHistory,
                        type: 'bar',
                        color: ChartColors?.info || '#0891b2',
                        height: 40,
                        width: 150
                    });
                }
            }
        }
    }

    /**
     * Update all charts
     */
    function updateCharts(data) {
        updateResponseTimeChart(data);
        updateSuccessFailureChart(data);
        updateAgentActivityChart(data);
        updateTokenUsageChart(data);
    }

    /**
     * Response time trend chart
     */
    function updateResponseTimeChart(data) {
        const ctx = document.getElementById('response-time-chart');
        if (!ctx) return;

        if (charts.responseTime) {
            charts.responseTime.destroy();
        }

        const chartData = {
            labels: data.timeLabels || [],
            datasets: [
                {
                    label: 'Avg Response Time (ms)',
                    data: data.responseTimeHistory || [],
                    borderColor: ChartColors?.primary || '#0078d4',
                    backgroundColor: createChartGradient(ctx.getContext('2d'), ChartColors?.primary || '#0078d4'),
                    fill: true,
                    tension: 0.4,
                },
                {
                    label: 'P95 Response Time (ms)',
                    data: data.p95ResponseTimeHistory || [],
                    borderColor: ChartColors?.warning || '#f59e0b',
                    backgroundColor: 'transparent',
                    borderDash: [5, 5],
                    tension: 0.4,
                }
            ]
        };

        charts.responseTime = new Chart(ctx, applyChartTheme({
            type: 'line',
            data: chartData,
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Response Time (ms)'
                        }
                    }
                }
            }
        }));
    }

    /**
     * Success vs failure pie chart
     */
    function updateSuccessFailureChart(data) {
        const ctx = document.getElementById('success-failure-chart');
        if (!ctx) return;

        if (charts.successFailure) {
            charts.successFailure.destroy();
        }

        const chartData = {
            labels: ['Success', 'Failures'],
            datasets: [{
                data: [
                    data.successfulRequests || 0,
                    data.failedRequests || 0
                ],
                backgroundColor: [
                    ChartColors?.success || '#0a8754',
                    ChartColors?.error || '#dc2626'
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        };

        charts.successFailure = new Chart(ctx, applyChartTheme({
            type: 'doughnut',
            data: chartData,
            options: {
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        }));
    }

    /**
     * Agent activity bar chart
     */
    function updateAgentActivityChart(data) {
        const ctx = document.getElementById('agent-activity-chart');
        if (!ctx) return;

        if (charts.agentActivity) {
            charts.agentActivity.destroy();
        }

        const agents = data.agentActivity || [];
        const chartData = {
            labels: agents.map(a => a.name),
            datasets: [{
                label: 'Requests Handled',
                data: agents.map(a => a.requests),
                backgroundColor: agents.map((_, i) => getChartColor(i, 0.8)),
                borderColor: agents.map((_, i) => getChartColor(i)),
                borderWidth: 1,
                borderRadius: 4
            }]
        };

        charts.agentActivity = new Chart(ctx, applyChartTheme({
            type: 'bar',
            data: chartData,
            options: {
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true
                    }
                }
            }
        }));
    }

    /**
     * Token usage line chart
     */
    function updateTokenUsageChart(data) {
        const ctx = document.getElementById('token-usage-chart');
        if (!ctx) return;

        if (charts.tokenUsage) {
            charts.tokenUsage.destroy();
        }

        const chartData = {
            labels: data.timeLabels || [],
            datasets: [
                {
                    label: 'Input Tokens',
                    data: data.inputTokenHistory || [],
                    borderColor: ChartColors?.info || '#0891b2',
                    backgroundColor: getChartColor(4, 0.2),
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Output Tokens',
                    data: data.outputTokenHistory || [],
                    borderColor: ChartColors?.warning || '#f59e0b',
                    backgroundColor: getChartColor(2, 0.2),
                    fill: true,
                    tension: 0.4
                }
            ]
        };

        charts.tokenUsage = new Chart(ctx, applyChartTheme({
            type: 'line',
            data: chartData,
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        stacked: true,
                        title: {
                            display: true,
                            text: 'Tokens'
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatNumber(context.parsed.y);
                            }
                        }
                    }
                }
            }
        }));
    }

    /**
     * Export chart as image
     */
    function exportChart(chartId) {
        const canvas = document.getElementById(chartId);
        if (!canvas) return;

        const url = canvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.download = `${chartId}-${Date.now()}.png`;
        link.href = url;
        link.click();
    }

    /**
     * Destroy dashboard and cleanup
     */
    function destroy() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }

        Object.values(charts).forEach(chart => chart.destroy());
        charts = {};
    }

    // Public API
    return {
        init,
        refresh,
        exportChart,
        destroy
    };
})();

// Export to global scope
if (typeof window !== 'undefined') {
    window.AgentMetrics = AgentMetrics;
}
