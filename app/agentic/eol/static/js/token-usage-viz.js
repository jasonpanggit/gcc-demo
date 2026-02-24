/**
 * Token Usage Visualization Component
 *
 * Displays real-time and historical token consumption metrics with:
 * - Total token usage (input + output)
 * - Cost estimation
 * - Usage by agent/endpoint
 * - Daily/hourly trends
 *
 * Requires: Chart.js 4.x, chart-theme.js
 *
 * Usage:
 *   <div id="token-usage-viz"></div>
 *   <script>TokenUsageViz.init('token-usage-viz', { period: '24h' });</script>
 *
 * Version: 1.0.0
 */

const TokenUsageViz = (function() {
    'use strict';

    // Configuration
    const config = {
        apiEndpoint: '/api/agents/token-usage',
        refreshInterval: 60000, // 1 minute
        periods: {
            '1h': { label: '1 Hour', dataPoints: 12 },
            '24h': { label: '24 Hours', dataPoints: 24 },
            '7d': { label: '7 Days', dataPoints: 7 },
            '30d': { label: '30 Days', dataPoints: 30 }
        },
        // Pricing per 1M tokens (example - adjust as needed)
        pricing: {
            'gpt-4o-mini': { input: 0.15, output: 0.60 },  // $0.15/$0.60 per 1M tokens
            'gpt-4o': { input: 5.00, output: 15.00 },
            'gpt-4': { input: 30.00, output: 60.00 }
        },
        defaultModel: 'gpt-4o-mini'
    };

    let charts = {};
    let refreshTimer = null;
    let currentPeriod = '24h';

    /**
     * Initialize token usage visualization
     */
    async function init(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`TokenUsageViz: Container "${containerId}" not found`);
            return;
        }

        const settings = { ...config, ...options };
        currentPeriod = options.period || '24h';

        // Render dashboard structure
        renderDashboard(container);

        // Load initial data
        await refresh(containerId);

        // Start auto-refresh
        if (settings.refreshInterval > 0) {
            refreshTimer = setInterval(() => refresh(containerId), settings.refreshInterval);
        }

        // Setup period selector
        setupPeriodSelector(containerId);
    }

    /**
     * Render dashboard HTML structure
     */
    function renderDashboard(container) {
        container.innerHTML = `
            <div class="token-usage-viz">
                <!-- Header with period selector -->
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h4 class="mb-0">
                        <i class="fas fa-coins me-2"></i>Token Usage Analytics
                    </h4>
                    <div class="btn-group" role="group" aria-label="Time period selector">
                        ${Object.entries(config.periods).map(([key, value]) => `
                            <button type="button"
                                    class="btn btn-sm btn-outline-primary period-btn ${key === currentPeriod ? 'active' : ''}"
                                    data-period="${key}">
                                ${value.label}
                            </button>
                        `).join('')}
                    </div>
                </div>

                <!-- Summary Cards -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="metric-label">Total Tokens</div>
                                <div class="metric-value text-primary" id="token-total">--</div>
                                <div class="metric-sublabel" id="token-total-change">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="metric-label">Input Tokens</div>
                                <div class="metric-value text-info" id="token-input">--</div>
                                <div class="metric-sublabel" id="token-input-percent">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="metric-label">Output Tokens</div>
                                <div class="metric-value text-warning" id="token-output">--</div>
                                <div class="metric-sublabel" id="token-output-percent">--</div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card metric-card">
                            <div class="card-body">
                                <div class="metric-label">Estimated Cost</div>
                                <div class="metric-value text-success" id="token-cost">--</div>
                                <div class="metric-sublabel" id="token-cost-model">--</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Charts -->
                <div class="row mb-4">
                    <div class="col-lg-8">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-line me-2"></i>Token Usage Over Time
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="token-timeline-chart" aria-label="Token usage timeline"></canvas>
                            </div>
                        </div>
                    </div>
                    <div class="col-lg-4">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-chart-pie me-2"></i>Token Distribution
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="token-distribution-chart" aria-label="Token distribution by type"></canvas>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Agent breakdown -->
                <div class="row mb-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-robot me-2"></i>Token Usage by Agent
                                </h5>
                            </div>
                            <div class="card-body">
                                <canvas id="token-agent-chart" aria-label="Token usage by agent"></canvas>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Cost breakdown table -->
                <div class="row">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h5 class="mb-0">
                                    <i class="fas fa-table me-2"></i>Detailed Cost Breakdown
                                </h5>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-sm table-hover" id="token-cost-table">
                                        <thead>
                                            <tr>
                                                <th>Agent</th>
                                                <th class="text-end">Input Tokens</th>
                                                <th class="text-end">Output Tokens</th>
                                                <th class="text-end">Total Tokens</th>
                                                <th class="text-end">Estimated Cost</th>
                                                <th style="width: 100px;">Trend</th>
                                            </tr>
                                        </thead>
                                        <tbody id="token-cost-tbody">
                                            <tr>
                                                <td colspan="6" class="text-center text-muted">Loading...</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Setup period selector buttons
     */
    function setupPeriodSelector(containerId) {
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                currentPeriod = e.target.dataset.period;
                document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                await refresh(containerId);
            });
        });
    }

    /**
     * Fetch token usage data from API
     */
    async function fetchData(period) {
        try {
            const response = await fetch(`${config.apiEndpoint}?period=${period}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            return data.success ? data.data : null;
        } catch (error) {
            console.error('Error fetching token usage data:', error);
            return null;
        }
    }

    /**
     * Refresh all visualizations
     */
    async function refresh(containerId) {
        const data = await fetchData(currentPeriod);
        if (!data) {
            console.warn('No token usage data available');
            return;
        }

        updateSummaryCards(data);
        updateCharts(data);
        updateCostTable(data);
    }

    /**
     * Update summary metric cards
     */
    function updateSummaryCards(data) {
        const total = (data.totalInputTokens || 0) + (data.totalOutputTokens || 0);
        const inputPercent = total > 0 ? ((data.totalInputTokens / total) * 100).toFixed(1) : 0;
        const outputPercent = total > 0 ? ((data.totalOutputTokens / total) * 100).toFixed(1) : 0;

        document.getElementById('token-total').textContent = formatNumber(total);
        document.getElementById('token-total-change').textContent =
            data.changePercent ? `${data.changePercent > 0 ? '+' : ''}${data.changePercent.toFixed(1)}% vs previous period` : '';

        document.getElementById('token-input').textContent = formatNumber(data.totalInputTokens || 0);
        document.getElementById('token-input-percent').textContent = `${inputPercent}% of total`;

        document.getElementById('token-output').textContent = formatNumber(data.totalOutputTokens || 0);
        document.getElementById('token-output-percent').textContent = `${outputPercent}% of total`;

        const cost = calculateCost(data.totalInputTokens || 0, data.totalOutputTokens || 0, data.model);
        document.getElementById('token-cost').textContent = `$${cost.toFixed(2)}`;
        document.getElementById('token-cost-model').textContent = `Model: ${data.model || config.defaultModel}`;
    }

    /**
     * Calculate estimated cost
     */
    function calculateCost(inputTokens, outputTokens, model = null) {
        const modelPricing = config.pricing[model || config.defaultModel] || config.pricing[config.defaultModel];
        const inputCost = (inputTokens / 1000000) * modelPricing.input;
        const outputCost = (outputTokens / 1000000) * modelPricing.output;
        return inputCost + outputCost;
    }

    /**
     * Update all charts
     */
    function updateCharts(data) {
        updateTimelineChart(data);
        updateDistributionChart(data);
        updateAgentChart(data);
    }

    /**
     * Token usage timeline chart
     */
    function updateTimelineChart(data) {
        const ctx = document.getElementById('token-timeline-chart');
        if (!ctx) return;

        if (charts.timeline) {
            charts.timeline.destroy();
        }

        const chartData = {
            labels: data.timeLabels || [],
            datasets: [
                {
                    label: 'Input Tokens',
                    data: data.inputTokenHistory || [],
                    borderColor: ChartColors?.info || '#0891b2',
                    backgroundColor: createChartGradient(ctx.getContext('2d'), ChartColors?.info || '#0891b2'),
                    fill: true,
                    tension: 0.4,
                },
                {
                    label: 'Output Tokens',
                    data: data.outputTokenHistory || [],
                    borderColor: ChartColors?.warning || '#f59e0b',
                    backgroundColor: createChartGradient(ctx.getContext('2d'), ChartColors?.warning || '#f59e0b'),
                    fill: true,
                    tension: 0.4,
                }
            ]
        };

        charts.timeline = new Chart(ctx, applyChartTheme({
            type: 'line',
            data: chartData,
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Tokens'
                        },
                        ticks: {
                            callback: function(value) {
                                return formatNumber(value);
                            }
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
     * Token distribution pie chart
     */
    function updateDistributionChart(data) {
        const ctx = document.getElementById('token-distribution-chart');
        if (!ctx) return;

        if (charts.distribution) {
            charts.distribution.destroy();
        }

        const chartData = {
            labels: ['Input Tokens', 'Output Tokens'],
            datasets: [{
                data: [
                    data.totalInputTokens || 0,
                    data.totalOutputTokens || 0
                ],
                backgroundColor: [
                    ChartColors?.info || '#0891b2',
                    ChartColors?.warning || '#f59e0b'
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        };

        charts.distribution = new Chart(ctx, applyChartTheme({
            type: 'doughnut',
            data: chartData,
            options: {
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percent = ((context.parsed / total) * 100).toFixed(1);
                                return `${context.label}: ${formatNumber(context.parsed)} (${percent}%)`;
                            }
                        }
                    }
                }
            }
        }));
    }

    /**
     * Token usage by agent chart
     */
    function updateAgentChart(data) {
        const ctx = document.getElementById('token-agent-chart');
        if (!ctx) return;

        if (charts.agent) {
            charts.agent.destroy();
        }

        const agents = data.agentTokens || [];
        const chartData = {
            labels: agents.map(a => a.name),
            datasets: [
                {
                    label: 'Input Tokens',
                    data: agents.map(a => a.inputTokens),
                    backgroundColor: ChartColors?.info || '#0891b2',
                },
                {
                    label: 'Output Tokens',
                    data: agents.map(a => a.outputTokens),
                    backgroundColor: ChartColors?.warning || '#f59e0b',
                }
            ]
        };

        charts.agent = new Chart(ctx, applyChartTheme({
            type: 'bar',
            data: chartData,
            options: {
                indexAxis: 'y',
                scales: {
                    x: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return formatNumber(value);
                            }
                        }
                    },
                    y: {
                        stacked: true
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatNumber(context.parsed.x);
                            }
                        }
                    }
                }
            }
        }));
    }

    /**
     * Update cost breakdown table
     */
    function updateCostTable(data) {
        const tbody = document.getElementById('token-cost-tbody');
        if (!tbody) return;

        const agents = data.agentTokens || [];

        if (agents.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No data available</td></tr>';
            return;
        }

        tbody.innerHTML = agents.map(agent => {
            const total = agent.inputTokens + agent.outputTokens;
            const cost = calculateCost(agent.inputTokens, agent.outputTokens, data.model);
            const trend = agent.trend || [];

            return `
                <tr>
                    <td><strong>${agent.name}</strong></td>
                    <td class="text-end">${formatNumber(agent.inputTokens)}</td>
                    <td class="text-end">${formatNumber(agent.outputTokens)}</td>
                    <td class="text-end"><strong>${formatNumber(total)}</strong></td>
                    <td class="text-end text-success">$${cost.toFixed(4)}</td>
                    <td>
                        ${trend.length > 0 ?
                            `<span class="sparkline" data-values='${JSON.stringify(trend)}' data-type="line" data-height="20" data-width="80"></span>` :
                            '<span class="text-muted">--</span>'
                        }
                    </td>
                </tr>
            `;
        }).join('');

        // Initialize sparklines
        if (typeof Sparklines !== 'undefined') {
            Sparklines.init();
        }
    }

    /**
     * Destroy visualization and cleanup
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
        destroy,
        calculateCost
    };
})();

// Export to global scope
if (typeof window !== 'undefined') {
    window.TokenUsageViz = TokenUsageViz;
}
