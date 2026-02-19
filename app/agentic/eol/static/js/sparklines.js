/**
 * Sparklines - Lightweight inline chart library
 *
 * Creates small, simple charts for embedding in tables and compact dashboards.
 * Uses SVG for crisp rendering at any size. No dependencies.
 *
 * Usage:
 *   <span class="sparkline" data-values="[1,5,2,8,3,7,4]" data-type="line"></span>
 *   <script>Sparklines.init();</script>
 *
 * Or programmatically:
 *   Sparklines.create(element, { values: [1,5,2,8,3], type: 'bar' });
 *
 * Version: 1.0.0
 */

const Sparklines = (function() {
    'use strict';

    // Default configuration
    const defaults = {
        type: 'line',           // 'line', 'bar', 'area', 'trend'
        width: 100,
        height: 30,
        strokeWidth: 2,
        color: '#0078d4',       // Uses design token --color-primary
        fillOpacity: 0.2,
        padding: 2,
        showDots: false,
        dotRadius: 2,
        barSpacing: 1,
        smooth: true,           // Use curved lines
        min: null,              // Auto-calculate if null
        max: null,              // Auto-calculate if null
        tooltipEnabled: true,
        ariaLabel: null,        // Auto-generated if null
    };

    /**
     * Initialize all sparklines on the page
     * Looks for elements with class 'sparkline' and data-values attribute
     */
    function init() {
        const elements = document.querySelectorAll('.sparkline[data-values]');
        elements.forEach(element => {
            const values = JSON.parse(element.getAttribute('data-values'));
            const type = element.getAttribute('data-type') || defaults.type;
            const width = parseInt(element.getAttribute('data-width')) || defaults.width;
            const height = parseInt(element.getAttribute('data-height')) || defaults.height;
            const color = element.getAttribute('data-color') || defaults.color;

            create(element, {
                values,
                type,
                width,
                height,
                color
            });
        });
    }

    /**
     * Create a sparkline in the specified element
     *
     * @param {HTMLElement} element - Container element
     * @param {Object} options - Configuration options
     */
    function create(element, options) {
        const config = { ...defaults, ...options };

        if (!config.values || config.values.length === 0) {
            console.warn('Sparklines: No values provided');
            return;
        }

        // Parse color from CSS variable if needed
        if (config.color.startsWith('--')) {
            config.color = getComputedStyle(document.documentElement)
                .getPropertyValue(config.color).trim() || defaults.color;
        }

        // Calculate min/max if not provided
        const values = config.values;
        const min = config.min !== null ? config.min : Math.min(...values);
        const max = config.max !== null ? config.max : Math.max(...values);
        const range = max - min || 1; // Avoid division by zero

        // Create SVG
        const svg = createSVG(config.width, config.height);

        // Add accessible label
        const ariaLabel = config.ariaLabel || generateAriaLabel(values, config.type);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', ariaLabel);

        // Render based on type
        switch (config.type) {
            case 'line':
            case 'area':
                renderLine(svg, values, min, max, range, config);
                break;
            case 'bar':
                renderBar(svg, values, min, max, range, config);
                break;
            case 'trend':
                renderTrend(svg, values, min, max, range, config);
                break;
            default:
                console.warn(`Sparklines: Unknown type "${config.type}"`);
        }

        // Add tooltip if enabled
        if (config.tooltipEnabled) {
            addTooltip(svg, values, config);
        }

        // Clear existing content and append SVG
        element.innerHTML = '';
        element.appendChild(svg);
        element.classList.add('sparkline-container');
    }

    /**
     * Create SVG element
     */
    function createSVG(width, height) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', width);
        svg.setAttribute('height', height);
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.style.display = 'inline-block';
        svg.style.verticalAlign = 'middle';
        return svg;
    }

    /**
     * Render line/area chart
     */
    function renderLine(svg, values, min, max, range, config) {
        const width = config.width;
        const height = config.height;
        const padding = config.padding;
        const innerWidth = width - padding * 2;
        const innerHeight = height - padding * 2;

        const points = values.map((value, index) => {
            const x = padding + (index / (values.length - 1)) * innerWidth;
            const y = padding + innerHeight - ((value - min) / range) * innerHeight;
            return { x, y, value };
        });

        // Create path
        let pathData = '';
        if (config.smooth && values.length > 2) {
            // Smooth curve using quadratic bezier
            pathData = `M ${points[0].x},${points[0].y}`;
            for (let i = 0; i < points.length - 1; i++) {
                const current = points[i];
                const next = points[i + 1];
                const midX = (current.x + next.x) / 2;
                pathData += ` Q ${current.x},${current.y} ${midX},${(current.y + next.y) / 2}`;
                if (i === points.length - 2) {
                    pathData += ` T ${next.x},${next.y}`;
                }
            }
        } else {
            // Straight lines
            pathData = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ');
        }

        // Draw area if type is 'area'
        if (config.type === 'area') {
            const areaPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            const areaData = pathData + ` L ${points[points.length - 1].x},${height - padding} L ${padding},${height - padding} Z`;
            areaPath.setAttribute('d', areaData);
            areaPath.setAttribute('fill', config.color);
            areaPath.setAttribute('fill-opacity', config.fillOpacity);
            areaPath.setAttribute('stroke', 'none');
            svg.appendChild(areaPath);
        }

        // Draw line
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('stroke', config.color);
        path.setAttribute('stroke-width', config.strokeWidth);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(path);

        // Draw dots if enabled
        if (config.showDots) {
            points.forEach(point => {
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', point.x);
                circle.setAttribute('cy', point.y);
                circle.setAttribute('r', config.dotRadius);
                circle.setAttribute('fill', config.color);
                svg.appendChild(circle);
            });
        }

        // Store points for tooltip
        svg._sparklinePoints = points;
    }

    /**
     * Render bar chart
     */
    function renderBar(svg, values, min, max, range, config) {
        const width = config.width;
        const height = config.height;
        const padding = config.padding;
        const innerWidth = width - padding * 2;
        const innerHeight = height - padding * 2;

        const barWidth = (innerWidth / values.length) - config.barSpacing;
        const points = [];

        values.forEach((value, index) => {
            const barHeight = ((value - min) / range) * innerHeight;
            const x = padding + (index * (innerWidth / values.length)) + config.barSpacing / 2;
            const y = height - padding - barHeight;

            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', x);
            rect.setAttribute('y', y);
            rect.setAttribute('width', barWidth);
            rect.setAttribute('height', barHeight);
            rect.setAttribute('fill', config.color);
            rect.setAttribute('rx', 1); // Slight rounding
            svg.appendChild(rect);

            points.push({ x: x + barWidth / 2, y, value });
        });

        // Store points for tooltip
        svg._sparklinePoints = points;
    }

    /**
     * Render trend indicator (simple line from first to last point)
     */
    function renderTrend(svg, values, min, max, range, config) {
        const width = config.width;
        const height = config.height;
        const padding = config.padding;
        const innerHeight = height - padding * 2;

        const firstValue = values[0];
        const lastValue = values[values.length - 1];

        const y1 = padding + innerHeight - ((firstValue - min) / range) * innerHeight;
        const y2 = padding + innerHeight - ((lastValue - min) / range) * innerHeight;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', padding);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', width - padding);
        line.setAttribute('y2', y2);

        // Color based on trend direction
        const trendColor = lastValue >= firstValue ?
            (getComputedStyle(document.documentElement).getPropertyValue('--color-success').trim() || '#0a8754') :
            (getComputedStyle(document.documentElement).getPropertyValue('--color-error').trim() || '#dc2626');

        line.setAttribute('stroke', trendColor);
        line.setAttribute('stroke-width', config.strokeWidth);
        line.setAttribute('stroke-linecap', 'round');
        svg.appendChild(line);

        // Add arrow at the end
        const arrowSize = 4;
        const angle = Math.atan2(y2 - y1, width - padding * 2);
        const arrowX = width - padding;
        const arrowY = y2;

        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        const points = [
            [arrowX, arrowY],
            [arrowX - arrowSize * Math.cos(angle - Math.PI / 6), arrowY - arrowSize * Math.sin(angle - Math.PI / 6)],
            [arrowX - arrowSize * Math.cos(angle + Math.PI / 6), arrowY - arrowSize * Math.sin(angle + Math.PI / 6)]
        ].map(p => p.join(',')).join(' ');

        arrow.setAttribute('points', points);
        arrow.setAttribute('fill', trendColor);
        svg.appendChild(arrow);
    }

    /**
     * Add interactive tooltip
     */
    function addTooltip(svg, values, config) {
        const tooltip = document.createElement('div');
        tooltip.className = 'sparkline-tooltip';
        tooltip.style.cssText = `
            position: absolute;
            background: var(--gray-900, #111827);
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-family: var(--font-family-base);
            pointer-events: none;
            opacity: 0;
            transition: opacity 150ms ease;
            z-index: 1000;
            white-space: nowrap;
        `;
        document.body.appendChild(tooltip);

        svg.addEventListener('mouseenter', () => {
            tooltip.style.opacity = '1';
        });

        svg.addEventListener('mouseleave', () => {
            tooltip.style.opacity = '0';
        });

        svg.addEventListener('mousemove', (e) => {
            const rect = svg.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const points = svg._sparklinePoints || [];

            if (points.length === 0) return;

            // Find closest point
            const closest = points.reduce((prev, curr) => {
                return Math.abs(curr.x - x) < Math.abs(prev.x - x) ? curr : prev;
            });

            tooltip.textContent = `Value: ${closest.value.toFixed(2)}`;
            tooltip.style.left = `${e.clientX + 10}px`;
            tooltip.style.top = `${e.clientY - 30}px`;
        });

        // Cleanup tooltip on element removal
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.removedNodes.forEach((node) => {
                    if (node === svg || node.contains(svg)) {
                        tooltip.remove();
                        observer.disconnect();
                    }
                });
            });
        });
        observer.observe(svg.parentElement, { childList: true, subtree: true });
    }

    /**
     * Generate accessible label
     */
    function generateAriaLabel(values, type) {
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        const trend = values[values.length - 1] > values[0] ? 'increasing' : 'decreasing';

        return `${type} chart with ${values.length} data points, ranging from ${min.toFixed(1)} to ${max.toFixed(1)}, average ${avg.toFixed(1)}, ${trend} trend`;
    }

    /**
     * Update existing sparkline with new values
     *
     * @param {HTMLElement} element - Container element
     * @param {Array} newValues - New data values
     */
    function update(element, newValues) {
        // Extract current config from element attributes
        const type = element.querySelector('svg')?.getAttribute('data-type') || defaults.type;
        const width = parseInt(element.querySelector('svg')?.getAttribute('width')) || defaults.width;
        const height = parseInt(element.querySelector('svg')?.getAttribute('height')) || defaults.height;
        const color = element.querySelector('svg path, svg rect')?.getAttribute('stroke') ||
                     element.querySelector('svg path, svg rect')?.getAttribute('fill') || defaults.color;

        create(element, {
            values: newValues,
            type,
            width,
            height,
            color
        });
    }

    // Auto-initialize on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Public API
    return {
        init,
        create,
        update,
        defaults
    };
})();

// Export to global scope
if (typeof window !== 'undefined') {
    window.Sparklines = Sparklines;
}
