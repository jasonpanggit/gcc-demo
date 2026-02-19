/**
 * Chart.js Theme Configuration
 *
 * Applies design tokens from design-tokens.css to Chart.js visualizations.
 * Provides consistent styling across all charts in the EOL Agentic Platform.
 *
 * Usage:
 *   <script src="/static/js/chart-theme.js"></script>
 *   const myChart = new Chart(ctx, applyChartTheme(config));
 *
 * Version: 1.0.0
 */

// Extract CSS custom properties from :root
function getCSSVariable(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Color palette extracted from design tokens
const ChartColors = {
    // Primary colors
    primary: getCSSVariable('--color-primary') || '#0078d4',
    primaryDark: getCSSVariable('--color-primary-dark') || '#005a9e',
    primaryLight: getCSSVariable('--color-primary-light') || '#50a7ff',
    primaryPale: getCSSVariable('--color-primary-pale') || '#e6f3ff',

    // Semantic colors
    success: getCSSVariable('--color-success') || '#0a8754',
    successLight: getCSSVariable('--color-success-light') || '#d4edda',
    warning: getCSSVariable('--color-warning') || '#f59e0b',
    warningLight: getCSSVariable('--color-warning-light') || '#fff3cd',
    error: getCSSVariable('--color-error') || '#dc2626',
    errorLight: getCSSVariable('--color-error-light') || '#f8d7da',
    info: getCSSVariable('--color-info') || '#0891b2',
    infoLight: getCSSVariable('--color-info-light') || '#d1ecf1',

    // Neutral grays
    gray900: getCSSVariable('--gray-900') || '#111827',
    gray800: getCSSVariable('--gray-800') || '#1f2937',
    gray700: getCSSVariable('--gray-700') || '#374151',
    gray600: getCSSVariable('--gray-600') || '#4b5563',
    gray500: getCSSVariable('--gray-500') || '#6b7280',
    gray400: getCSSVariable('--gray-400') || '#9ca3af',
    gray300: getCSSVariable('--gray-300') || '#d1d5db',
    gray200: getCSSVariable('--gray-200') || '#e5e7eb',
    gray100: getCSSVariable('--gray-100') || '#f3f4f6',
    gray50: getCSSVariable('--gray-50') || '#f9fafb',

    // Agent-specific colors
    agentMcp: getCSSVariable('--agent-mcp') || '#0078d4',
    agentSre: getCSSVariable('--agent-sre') || '#dc3545',
    agentInventory: getCSSVariable('--agent-inventory') || '#28a745',
    agentEol: getCSSVariable('--agent-eol') || '#ffc107',
    agentMicrosoft: getCSSVariable('--agent-microsoft') || '#dc3545',
    agentUbuntu: getCSSVariable('--agent-ubuntu') || '#fd7e14',
    agentRedhat: getCSSVariable('--agent-redhat') || '#ee0000',
    agentOracle: getCSSVariable('--agent-oracle') || '#d63384',

    // Chart-specific palette (high contrast, colorblind-friendly)
    chartPalette: [
        '#0078d4', // Azure Blue
        '#0a8754', // Green
        '#f59e0b', // Amber
        '#dc2626', // Red
        '#0891b2', // Cyan
        '#7c3aed', // Purple
        '#db2777', // Pink
        '#ea580c', // Orange
        '#059669', // Emerald
        '#2563eb', // Blue
        '#8b5cf6', // Violet
        '#ec4899', // Fuchsia
    ]
};

// Typography from design tokens
const ChartTypography = {
    fontFamily: getCSSVariable('--font-family-base') ||
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    fontSizeXs: '12px',
    fontSizeSm: '14px',
    fontSizeBase: '16px',
    fontSizeLg: '20px',
    fontWeightNormal: 400,
    fontWeightMedium: 500,
    fontWeightSemibold: 600,
    fontWeightBold: 700,
};

/**
 * Default Chart.js theme configuration
 * Apply this to your chart config for consistent styling
 */
const ChartTheme = {
    // Global defaults
    responsive: true,
    maintainAspectRatio: true,

    // Plugin defaults
    plugins: {
        legend: {
            display: true,
            position: 'top',
            align: 'center',
            labels: {
                font: {
                    family: ChartTypography.fontFamily,
                    size: 14,
                    weight: ChartTypography.fontWeightMedium,
                },
                color: ChartColors.gray700,
                padding: 16,
                boxWidth: 12,
                boxHeight: 12,
                usePointStyle: true,
                pointStyle: 'circle',
            }
        },
        tooltip: {
            enabled: true,
            backgroundColor: ChartColors.gray900,
            titleColor: '#ffffff',
            bodyColor: '#ffffff',
            borderColor: ChartColors.gray700,
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            titleFont: {
                family: ChartTypography.fontFamily,
                size: 14,
                weight: ChartTypography.fontWeightSemibold,
            },
            bodyFont: {
                family: ChartTypography.fontFamily,
                size: 13,
                weight: ChartTypography.fontWeightNormal,
            },
            displayColors: true,
            boxWidth: 10,
            boxHeight: 10,
            boxPadding: 6,
            usePointStyle: true,
        },
        title: {
            display: false, // Prefer using card headers
            font: {
                family: ChartTypography.fontFamily,
                size: 18,
                weight: ChartTypography.fontWeightSemibold,
            },
            color: ChartColors.gray900,
            padding: {
                top: 10,
                bottom: 20,
            }
        }
    },

    // Scale defaults
    scales: {
        x: {
            grid: {
                display: true,
                color: ChartColors.gray200,
                drawBorder: false,
                lineWidth: 1,
            },
            ticks: {
                font: {
                    family: ChartTypography.fontFamily,
                    size: 12,
                },
                color: ChartColors.gray600,
                padding: 8,
            },
            border: {
                display: false,
            }
        },
        y: {
            grid: {
                display: true,
                color: ChartColors.gray200,
                drawBorder: false,
                lineWidth: 1,
            },
            ticks: {
                font: {
                    family: ChartTypography.fontFamily,
                    size: 12,
                },
                color: ChartColors.gray600,
                padding: 8,
            },
            border: {
                display: false,
            },
            beginAtZero: true,
        }
    },

    // Animation
    animation: {
        duration: 300,
        easing: 'easeInOutQuart',
    },

    // Interaction
    interaction: {
        mode: 'index',
        intersect: false,
    },
};

/**
 * Apply theme to a Chart.js configuration object
 * Deep merges theme with provided config
 *
 * @param {Object} config - Chart.js configuration object
 * @returns {Object} - Merged configuration with theme applied
 */
function applyChartTheme(config) {
    // Deep merge helper
    function deepMerge(target, source) {
        const output = Object.assign({}, target);
        if (isObject(target) && isObject(source)) {
            Object.keys(source).forEach(key => {
                if (isObject(source[key])) {
                    if (!(key in target)) {
                        Object.assign(output, { [key]: source[key] });
                    } else {
                        output[key] = deepMerge(target[key], source[key]);
                    }
                } else {
                    Object.assign(output, { [key]: source[key] });
                }
            });
        }
        return output;
    }

    function isObject(item) {
        return item && typeof item === 'object' && !Array.isArray(item);
    }

    return deepMerge(ChartTheme, config);
}

/**
 * Get a color from the chart palette by index
 * Wraps around if index exceeds palette length
 *
 * @param {number} index - Color index
 * @param {number} alpha - Optional alpha value (0-1)
 * @returns {string} - Color value
 */
function getChartColor(index, alpha = 1) {
    const color = ChartColors.chartPalette[index % ChartColors.chartPalette.length];
    if (alpha < 1) {
        // Convert hex to rgba
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
    return color;
}

/**
 * Generate gradient for chart background
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {string} colorStart - Start color
 * @param {string} colorEnd - End color (optional, defaults to transparent)
 * @returns {CanvasGradient} - Gradient object
 */
function createChartGradient(ctx, colorStart, colorEnd = null) {
    const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);

    // Parse color if it's from our palette
    const startColor = colorStart.startsWith('#') ? colorStart : ChartColors[colorStart] || colorStart;

    if (!colorEnd) {
        // Auto-generate transparent version
        const match = startColor.match(/^#([0-9a-f]{6})$/i);
        if (match) {
            const r = parseInt(match[1].slice(0, 2), 16);
            const g = parseInt(match[1].slice(2, 4), 16);
            const b = parseInt(match[1].slice(4, 6), 16);
            gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.4)`);
            gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.01)`);
        } else {
            gradient.addColorStop(0, startColor);
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        }
    } else {
        gradient.addColorStop(0, startColor);
        gradient.addColorStop(1, colorEnd);
    }

    return gradient;
}

/**
 * Presets for common chart types
 */
const ChartPresets = {
    /**
     * Line chart preset with area fill
     */
    lineArea: {
        type: 'line',
        options: {
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2,
        }
    },

    /**
     * Bar chart preset
     */
    bar: {
        type: 'bar',
        options: {
            borderRadius: 4,
            borderWidth: 0,
        }
    },

    /**
     * Doughnut chart preset
     */
    doughnut: {
        type: 'doughnut',
        options: {
            cutout: '65%',
            borderWidth: 2,
            borderColor: '#ffffff',
            spacing: 2,
        }
    },

    /**
     * Pie chart preset
     */
    pie: {
        type: 'pie',
        options: {
            borderWidth: 2,
            borderColor: '#ffffff',
            spacing: 2,
        }
    },

    /**
     * Time series preset
     */
    timeSeries: {
        type: 'line',
        options: {
            scales: {
                x: {
                    type: 'time',
                    time: {
                        tooltipFormat: 'MMM d, HH:mm',
                    },
                    title: {
                        display: false,
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                intersect: false,
            }
        }
    }
};

/**
 * Utility: Format large numbers (e.g., 1000 -> 1K)
 */
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

/**
 * Utility: Format percentage
 */
function formatPercentage(value, total) {
    if (total === 0) return '0%';
    return ((value / total) * 100).toFixed(1) + '%';
}

// Export to global scope
if (typeof window !== 'undefined') {
    window.ChartColors = ChartColors;
    window.ChartTypography = ChartTypography;
    window.ChartTheme = ChartTheme;
    window.ChartPresets = ChartPresets;
    window.applyChartTheme = applyChartTheme;
    window.getChartColor = getChartColor;
    window.createChartGradient = createChartGradient;
    window.formatNumber = formatNumber;
    window.formatPercentage = formatPercentage;
}
