/**
 * EOL Shared Utilities
 * Common functions used across multiple templates for software EOL analysis
 */

window.eolUtils = window.eolUtils || {};

(function() {
    'use strict';

    /**
     * Clean software name by removing noise patterns
     * Removes Arc-enabled markers, architecture info, etc.
     * @param {string} name - Software name to clean
     * @returns {string} Cleaned software name
     */
    eolUtils.cleanSoftwareName = function(name) {
        if (!name) return name;

        // Remove common noise patterns that might interfere with EOL lookup
        let cleaned = name
            .replace(/\s*\(Arc-enabled\)/gi, '')  // Remove Arc-enabled markers
            .replace(/\s*\(x64\)/gi, '')          // Remove architecture markers
            .replace(/\s*\(x86\)/gi, '')
            .replace(/\s*64-bit/gi, '')
            .replace(/\s*32-bit/gi, '')
            .replace(/\s*\([^)]*bit[^)]*\)/gi, '') // Remove any parenthetical bit references
            .replace(/\s+/g, ' ')                  // Normalize whitespace
            .trim();

        return cleaned;
    };

    /**
     * Extract version information from software name
     * @param {string} name - Software name potentially containing version
     * @returns {Object} Object with {name, version} properties
     */
    eolUtils.parseVersionFromName = function(name) {
        if (!name) return { name: name, version: null };

        // Common version patterns to extract
        const versionPatterns = [
            // Standard version patterns: "Software 2019", "Windows Server 2016"
            /^(.+?)\s+(\d{4})$/i,
            // Version with dots: "Software 1.2.3"
            /^(.+?)\s+(v?(?:\d+\.)+\d+(?:\.\d+)*)$/i,
            // Version with single number: "Software 12"
            /^(.+?)\s+v?(\d+)$/i,
            // Ubuntu-style: "Ubuntu 20.04", "RHEL 8.5"
            /^(.+?)\s+(\d+\.\d+(?:\.\d+)?)$/i,
        ];

        for (const pattern of versionPatterns) {
            const match = name.match(pattern);
            if (match) {
                const baseName = match[1].trim();
                const version = match[2].trim();

                // Validate that we're not accidentally parsing a valid part of the name
                if (!eolUtils.isCommonSoftwareWord(version)) {
                    return {
                        name: baseName,
                        version: version
                    };
                }
            }
        }

        return { name: name, version: null };
    };

    /**
     * Check if word is a common software term (not a version)
     * @param {string} word - Word to check
     * @returns {boolean} True if common software word
     */
    eolUtils.isCommonSoftwareWord = function(word) {
        if (!word || typeof word !== 'string') {
            return false;
        }
        const commonWords = [
            'server', 'client', 'pro', 'professional', 'enterprise', 'standard',
            'express', 'developer', 'runtime', 'framework', 'sdk', 'tools',
            'service', 'pack', 'update', 'hotfix', 'patch'
        ];
        return commonWords.includes(word.toLowerCase());
    };

    /**
     * Calculate confidence level for EOL search
     * @param {string} name - Software name
     * @param {string} version - Software version (optional)
     * @returns {number} Confidence level between 0 and 1
     */
    eolUtils.calculateSearchConfidence = function(name, version) {
        let confidence = 0.5; // Base confidence

        // Increase confidence for well-known software patterns
        const knownPatterns = [
            /windows.*server/i, /microsoft.*office/i, /visual.*studio/i,
            /red.*hat/i, /rhel/i, /ubuntu/i, /centos/i,
            /sql.*server/i, /\.net/i, /iis/i
        ];

        if (knownPatterns.some(pattern => pattern.test(name))) {
            confidence += 0.3;
        }

        // Increase confidence if version is provided
        if (version) {
            confidence += 0.2;

            // Boost for year-based versions (common for enterprise software)
            if (/^\d{4}$/.test(version)) {
                confidence += 0.1;
            }
        }

        return Math.min(confidence, 1.0);
    };

    /**
     * Determine which agents would be selected based on software name
     * @param {string} softwareName - Software name to analyze
     * @returns {Array} Array of agent objects with name, type, icon, reason
     */
    eolUtils.getSelectedAgents = function(softwareName) {
        if (!softwareName || typeof softwareName !== 'string') {
            return [];
        }

        const softwareNameLower = softwareName.toLowerCase();
        const selectedAgents = [];

        // Agent configuration: keywords, name, type, icon, reason
        const agentConfigs = [
            {
                keywords: ['windows', 'microsoft', 'office', 'sql server', 'iis', 'visual studio', '.net'],
                name: 'Microsoft Agent',
                type: 'microsoft',
                icon: 'fab fa-microsoft',
                reason: 'Microsoft product detected'
            },
            {
                keywords: ['red hat', 'rhel', 'centos', 'fedora'],
                name: 'Red Hat Agent',
                type: 'redhat',
                icon: 'fab fa-redhat',
                reason: 'Red Hat product detected'
            },
            {
                keywords: ['ubuntu', 'canonical'],
                name: 'Ubuntu Agent',
                type: 'ubuntu',
                icon: 'fab fa-ubuntu',
                reason: 'Ubuntu product detected'
            },
            {
                keywords: ['python', 'py'],
                name: 'Python Agent',
                type: 'python',
                icon: 'fab fa-python',
                reason: 'Python detected'
            },
            {
                keywords: ['node', 'nodejs', 'node.js'],
                name: 'Node.js Agent',
                type: 'nodejs',
                icon: 'fab fa-node-js',
                reason: 'Node.js detected'
            },
            {
                keywords: ['php'],
                name: 'PHP Agent',
                type: 'php',
                icon: 'fab fa-php',
                reason: 'PHP detected'
            }
        ];

        // Check each agent configuration
        for (const config of agentConfigs) {
            if (config.keywords.some(keyword => softwareNameLower.includes(keyword))) {
                selectedAgents.push({
                    name: config.name,
                    type: config.type,
                    icon: config.icon,
                    reason: config.reason
                });
            }
        }

        // Always include endoflife.date as fallback
        selectedAgents.push({
            name: 'EndOfLife.date Agent',
            type: 'endoflife',
            icon: 'fas fa-calendar-times',
            reason: 'General EOL database'
        });

        return selectedAgents;
    };

    /**
     * Format date consistently across the application
     * @param {string|Date} dateString - Date string or Date object to format
     * @returns {string} Formatted date or 'N/A'
     */
    eolUtils.formatDate = function(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) {
                console.warn('Invalid date:', dateString);
                return 'N/A';
            }
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        } catch (e) {
            console.error('Error formatting date:', e);
            return 'N/A';
        }
    };

    /**
     * Format relative time (e.g., "5 minutes ago")
     * @param {string|Date} dateString - Date string or Date object to format
     * @returns {string} Relative time string
     */
    eolUtils.formatRelativeTime = function(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) {
                console.warn('Invalid date for relative time:', dateString);
                return 'Unknown';
            }
            const now = new Date();
            const diffInSeconds = Math.floor((now - date) / 1000);

            if (diffInSeconds < 60) return 'Just now';
            if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
            if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
            if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;

            return eolUtils.formatDate(dateString);
        } catch (e) {
            console.error('Error formatting relative time:', e);
            return 'Unknown';
        }
    };

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped HTML
     */
    eolUtils.escapeHtml = function(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    /**
     * Debounce function for search inputs
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} Debounced function
     */
    eolUtils.debounce = function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    /**
     * Show toast notification
     * @param {string} message - Message to display
     * @param {string} type - Toast type (success, danger, warning, info)
     * @param {number} duration - Duration in milliseconds
     */
    eolUtils.showToast = function(message, type = 'info', duration = 3000) {
        // Create toast container if it doesn't exist
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
        }

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        
        // Create structure using DOM methods to avoid XSS
        const flexDiv = document.createElement('div');
        flexDiv.className = 'd-flex';
        
        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'toast-body';
        bodyDiv.textContent = message; // Safe: uses textContent
        
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
        closeBtn.setAttribute('data-bs-dismiss', 'toast');
        
        flexDiv.appendChild(bodyDiv);
        flexDiv.appendChild(closeBtn);
        toast.appendChild(flexDiv);
        container.appendChild(toast);

        // Show toast
        const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: duration });
        bsToast.show();

        // Remove from DOM after hiding
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    };

    /**
     * Copy text to clipboard
     * @param {string} text - Text to copy
     * @returns {Promise<boolean>} Success status
     */
    eolUtils.copyToClipboard = async function(text) {
        if (!text) {
            console.warn('copyToClipboard: No text provided');
            return false;
        }
        
        try {
            await navigator.clipboard.writeText(text);
            eolUtils.showToast('Copied to clipboard!', 'success');
            return true;
        } catch (err) {
            console.warn('Clipboard API failed, using fallback:', err);
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-9999px';
            document.body.appendChild(textArea);
            textArea.select();
            try {
                const success = document.execCommand('copy');
                if (success) {
                    eolUtils.showToast('Copied to clipboard!', 'success');
                    return true;
                } else {
                    throw new Error('execCommand failed');
                }
            } catch (fallbackErr) {
                console.error('Fallback copy failed:', fallbackErr);
                eolUtils.showToast('Failed to copy to clipboard', 'danger');
                return false;
            } finally {
                document.body.removeChild(textArea);
            }
        }
    };

    /**
     * Calculate days until EOL
     * @param {string|Date} eolDate - EOL date string or Date object
     * @returns {number|null} Days until EOL or null if invalid
     */
    eolUtils.daysUntilEOL = function(eolDate) {
        if (!eolDate) return null;
        try {
            const eol = new Date(eolDate);
            if (isNaN(eol.getTime())) {
                console.warn('Invalid EOL date:', eolDate);
                return null;
            }
            const now = new Date();
            const diffTime = eol - now;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            return diffDays;
        } catch (e) {
            console.error('Error calculating days until EOL:', e);
            return null;
        }
    };

    /**
     * Determine risk level based on days until EOL
     * Risk levels:
     * - critical: Already EOL or <= 90 days (3 months)
     * - high: <= 365 days (1 year)
     * - medium: <= 730 days (2 years)
     * - low: > 730 days
     * - unknown: Invalid/missing data
     * @param {number|null} daysUntilEOL - Days until EOL
     * @returns {string} Risk level: critical, high, medium, low, unknown
     */
    eolUtils.getRiskLevel = function(daysUntilEOL) {
        if (daysUntilEOL === null || daysUntilEOL === undefined) {
            return 'unknown';
        }
        
        if (daysUntilEOL < 0 || daysUntilEOL <= 90) {
            return 'critical';
        } else if (daysUntilEOL <= 365) {
            return 'high';
        } else if (daysUntilEOL <= 730) {
            return 'medium';
        } else {
            return 'low';
        }
    };

    /**
     * Get badge class based on risk level
     * @param {string} riskLevel - Risk level
     * @returns {string} Bootstrap badge class
     */
    eolUtils.getRiskBadgeClass = function(riskLevel) {
        const riskClasses = {
            'critical': 'bg-danger',
            'high': 'bg-warning text-dark',
            'medium': 'bg-info text-dark',
            'low': 'bg-success',
            'unknown': 'bg-secondary'
        };
        return riskClasses[riskLevel] || 'bg-secondary';
    };

    // ==============================================
    // HTML Component Generators
    // ==============================================

    /**
     * Create a Bootstrap spinner element
     * @param {object} options - Configuration options
     * @param {string} options.size - Size: 'sm' or default
     * @param {string} options.color - Bootstrap color class (e.g., 'primary', 'success')
     * @param {string} options.className - Additional CSS classes
     * @param {string} options.text - Screen reader text
     * @returns {HTMLElement} Spinner element
     */
    eolUtils.createSpinner = function(options = {}) {
        const {
            size = '',
            color = 'primary',
            className = '',
            text = 'Loading...'
        } = options;

        const spinner = document.createElement('div');
        spinner.className = `spinner-border text-${color} ${size ? 'spinner-border-' + size : ''} ${className}`.trim();
        spinner.setAttribute('role', 'status');
        
        const srText = document.createElement('span');
        srText.className = 'visually-hidden';
        srText.textContent = text;
        spinner.appendChild(srText);
        
        return spinner;
    };

    /**
     * Create a loading overlay with spinner
     * @param {string} message - Loading message
     * @returns {HTMLElement} Loading overlay element
     */
    eolUtils.createLoadingOverlay = function(message = 'Loading...') {
        const overlay = document.createElement('div');
        overlay.className = 'position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center bg-white bg-opacity-75';
        overlay.style.zIndex = '1050';
        
        const content = document.createElement('div');
        content.className = 'text-center';
        
        content.appendChild(eolUtils.createSpinner({ color: 'primary', className: 'mb-2' }));
        
        const text = document.createElement('div');
        text.className = 'text-muted';
        text.textContent = message;
        content.appendChild(text);
        
        overlay.appendChild(content);
        return overlay;
    };

    /**
     * Create a Bootstrap modal programmatically
     * @param {object} options - Modal configuration
     * @param {string} options.id - Modal ID
     * @param {string} options.title - Modal title
     * @param {string|HTMLElement} options.body - Modal body content
     * @param {string} options.size - Modal size: 'sm', 'lg', 'xl', or default
     * @param {Array} options.buttons - Array of button configs: { text, className, onClick }
     * @returns {HTMLElement} Modal element
     */
    eolUtils.createModal = function(options = {}) {
        const {
            id = 'dynamicModal',
            title = 'Modal',
            body = '',
            size = '',
            buttons = [{ text: 'Close', className: 'btn-secondary', dismiss: true }]
        } = options;

        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = id;
        modal.setAttribute('tabindex', '-1');
        
        const dialog = document.createElement('div');
        dialog.className = `modal-dialog ${size ? 'modal-' + size : ''}`.trim();
        
        const content = document.createElement('div');
        content.className = 'modal-content';
        
        // Header
        const header = document.createElement('div');
        header.className = 'modal-header';
        const titleEl = document.createElement('h5');
        titleEl.className = 'modal-title';
        titleEl.textContent = title;
        header.appendChild(titleEl);
        
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'modal');
        header.appendChild(closeBtn);
        
        // Body
        const bodyEl = document.createElement('div');
        bodyEl.className = 'modal-body';
        if (typeof body === 'string') {
            // For string content, use textContent for safety unless explicitly HTML
            // If HTML is needed, caller should pass HTMLElement instead
            bodyEl.textContent = body;
        } else if (body instanceof HTMLElement) {
            bodyEl.appendChild(body);
        } else {
            console.warn('createModal: body must be string or HTMLElement');
            bodyEl.textContent = String(body);
        }
        
        // Footer
        const footer = document.createElement('div');
        footer.className = 'modal-footer';
        buttons.forEach(btn => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `btn ${btn.className || 'btn-secondary'}`;
            button.textContent = btn.text;
            if (btn.dismiss) {
                button.setAttribute('data-bs-dismiss', 'modal');
            }
            if (btn.onClick) {
                button.addEventListener('click', btn.onClick);
            }
            footer.appendChild(button);
        });
        
        content.appendChild(header);
        content.appendChild(bodyEl);
        content.appendChild(footer);
        dialog.appendChild(content);
        modal.appendChild(dialog);
        
        return modal;
    };

    /**
     * Show an error alert
     * NOTE: This function should NOT be called directly from page scripts.
     * Each page should define its own showAlert with appropriate signature.
     * @param {string} message - Error message
     * @param {HTMLElement} container - Container to prepend alert to (NOT a string!)
     * @param {boolean} dismissible - Whether alert is dismissible
     */
    eolUtils.showAlert = function(message, container, dismissible = true) {
        // Debug logging to catch misuse
        console.warn('⚠️ eolUtils.showAlert called - pages should use their own showAlert');
        console.warn('Parameters:', { 
            message: typeof message, 
            container: typeof container, 
            containerTag: container?.tagName,
            dismissible 
        });
        
        // Strict validation with detailed error messages
        if (!container) {
            console.error('❌ showAlert: container is null/undefined');
            return;
        }
        
        if (typeof container === 'string') {
            console.error('❌ showAlert: container is a STRING ("' + container + '"). Expected HTMLElement.');
            console.error('💡 Hint: You probably called showAlert(message, type) but eolUtils.showAlert expects (message, element, dismissible)');
            return;
        }
        
        if (!container.insertBefore || typeof container.insertBefore !== 'function') {
            console.error('❌ showAlert: container missing insertBefore method. Got:', container);
            return;
        }
        
        const alert = document.createElement('div');
        alert.className = `alert alert-danger ${dismissible ? 'alert-dismissible fade show' : ''}`;
        alert.setAttribute('role', 'alert');
        alert.textContent = message;
        
        if (dismissible) {
            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'btn-close';
            closeBtn.setAttribute('data-bs-dismiss', 'alert');
            alert.appendChild(closeBtn);
        }
        
        // Always use insertBefore for compatibility (avoid prepend issues)
        try {
            container.insertBefore(alert, container.firstChild);
        } catch (err) {
            console.error('❌ showAlert: Failed to insert alert:', err);
        }
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            try {
                alert.remove();
            } catch (err) {
                // Silent fail on removal
            }
        }, 5000);
    };

    // ==============================================
    // Performance Optimization Utilities
    // ==============================================

    /**
     * Lazy load content when element becomes visible
     * Uses Intersection Observer API for efficient lazy loading
     * @param {string|HTMLElement} target - Target element or selector
     * @param {Function} loadCallback - Function to call when element is visible
     * @param {Object} options - Intersection Observer options
     * @param {HTMLElement|null} options.root - Root element for intersection
     * @param {string} options.rootMargin - Margin around root
     * @param {number} options.threshold - Intersection threshold
     */
    eolUtils.lazyLoad = function(target, loadCallback, options = {}) {
        if (!loadCallback || typeof loadCallback !== 'function') {
            console.error('lazyLoad: loadCallback must be a function');
            return;
        }
        
        const defaultOptions = {
            root: null,
            rootMargin: '50px',
            threshold: 0.01
        };
        
        const observerOptions = { ...defaultOptions, ...options };
        
        const element = typeof target === 'string' ? document.querySelector(target) : target;
        if (!element) {
            console.warn('Lazy load target not found:', target);
            return;
        }
        
        // Mark as loading to prevent duplicate loads
        if (element.dataset.lazyLoading === 'true') {
            console.debug('Element already loading:', element);
            return;
        }
        
        const observer = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    element.dataset.lazyLoading = 'true';
                    
                    // Call the load callback
                    try {
                        loadCallback(element);
                    } catch (err) {
                        console.error('Error in lazy load callback:', err);
                        element.dataset.lazyLoadError = 'true';
                    }
                    
                    // Stop observing after loading
                    obs.unobserve(entry.target);
                    element.dataset.lazyLoaded = 'true';
                    delete element.dataset.lazyLoading;
                }
            });
        }, observerOptions);
        
        observer.observe(element);
    };

    /**
     * Defer execution of non-critical code until page is idle
     * @param {Function} callback - Function to execute when idle
     * @param {number} timeout - Timeout in milliseconds (default: 2000)
     */
    eolUtils.deferUntilIdle = function(callback, timeout = 2000) {
        if ('requestIdleCallback' in window) {
            requestIdleCallback(callback, { timeout });
        } else {
            // Fallback for browsers without requestIdleCallback
            setTimeout(callback, timeout);
        }
    };

    /**
     * Preload a resource (image, script, style)
     * @param {string} url - URL of the resource
     * @param {string} as - Resource type: 'image', 'script', 'style', 'fetch'
     */
    eolUtils.preload = function(url, as = 'fetch') {
        const link = document.createElement('link');
        link.rel = 'preload';
        link.as = as;
        link.href = url;
        
        if (as === 'script') {
            link.crossOrigin = 'anonymous';
        }
        
        document.head.appendChild(link);
    };

    // Expose to global scope for backward compatibility
    window.eolUtils = eolUtils;
    window.cleanSoftwareName = eolUtils.cleanSoftwareName;
    window.parseVersionFromName = eolUtils.parseVersionFromName;
    window.calculateSearchConfidence = eolUtils.calculateSearchConfidence;
    window.getSelectedAgents = eolUtils.getSelectedAgents;
    window.formatDate = eolUtils.formatDate;
    window.formatRelativeTime = eolUtils.formatRelativeTime;
    window.escapeHtml = eolUtils.escapeHtml;
    window.debounce = eolUtils.debounce;
    window.showToast = eolUtils.showToast;
    window.copyToClipboard = eolUtils.copyToClipboard;
    window.createSpinner = eolUtils.createSpinner;
    window.createLoadingOverlay = eolUtils.createLoadingOverlay;
    window.createModal = eolUtils.createModal;
    // Note: showAlert is NOT exposed globally because different pages use different signatures
    // Use eolUtils.showAlert directly if you need the utility function
    window.lazyLoad = eolUtils.lazyLoad;
    window.deferUntilIdle = eolUtils.deferUntilIdle;
    window.preload = eolUtils.preload;

    /**
     * ============================================================
     * DARK MODE THEME UTILITIES
     * ============================================================
     */

    /**
     * Check if dark mode is currently active
     * @returns {boolean} True if dark mode is enabled
     */
    eolUtils.isDarkMode = function() {
        return document.documentElement.classList.contains('dark-mode') ||
               document.documentElement.getAttribute('data-theme') === 'dark';
    };

    /**
     * Get CSS variable value from design tokens
     * @param {string} variableName - CSS variable name (e.g., '--text-primary')
     * @param {string} fallback - Fallback value if variable not found
     * @returns {string} CSS variable value
     */
    eolUtils.getCSSVariable = function(variableName, fallback = '') {
        const value = getComputedStyle(document.documentElement)
            .getPropertyValue(variableName)
            .trim();
        return value || fallback;
    };

    /**
     * Get themed color based on current mode
     * @param {string} lightColor - Color to use in light mode
     * @param {string} darkColor - Color to use in dark mode
     * @returns {string} Appropriate color for current theme
     */
    eolUtils.getThemedColor = function(lightColor, darkColor) {
        return eolUtils.isDarkMode() ? darkColor : lightColor;
    };

    /**
     * Get themed chart colors for Chart.js configurations
     * @returns {Object} Chart color configuration for current theme
     */
    eolUtils.getThemedChartColors = function() {
        const isDark = eolUtils.isDarkMode();
        return {
            // Grid and axes
            grid: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.06)',
            text: eolUtils.getCSSVariable('--text-secondary', isDark ? '#d1d5db' : '#6c757d'),

            // Tooltips (inverted for contrast)
            tooltipBg: isDark ? 'rgba(255, 255, 255, 0.95)' : 'rgba(17, 24, 39, 0.95)',
            tooltipText: isDark ? '#111827' : '#ffffff',
            tooltipBorder: eolUtils.getCSSVariable('--border-primary'),

            // Legend
            legendText: eolUtils.getCSSVariable('--text-primary'),

            // Data series (maintain visibility in both modes)
            primary: eolUtils.getCSSVariable('--color-primary', '#0078d4'),
            success: isDark ? '#86efac' : '#198754',
            warning: isDark ? '#fdba74' : '#ffc107',
            error: isDark ? '#fca5a5' : '#dc3545',
            info: isDark ? '#93c5fd' : '#0891b2',

            // Status indicators
            healthy: eolUtils.getCSSVariable('--color-success'),
            degraded: eolUtils.getCSSVariable('--color-warning'),
            unhealthy: eolUtils.getCSSVariable('--color-error'),
        };
    };

    /**
     * Get themed flow diagram colors
     * @returns {Object} Flow node color configuration for current theme
     */
    eolUtils.getFlowDiagramColors = function() {
        const isDark = eolUtils.isDarkMode();
        return {
            user: isDark ? '#1e3a5f' : '#e3f2fd',
            orchestrator: isDark ? '#3a2a4f' : '#f3e5f5',
            microsoft: isDark ? '#2a4f2a' : '#e8f5e8',
            eol: isDark ? '#4f3e2a' : '#fff3e0',
            generic: isDark ? '#4f2a3e' : '#fce4ec',
            completion: isDark ? '#2a5f3a' : '#c8e6c9',
        };
    };

    /**
     * Create a MutationObserver to watch for theme changes
     * Emits 'theme-changed' custom event when theme switches
     */
    eolUtils.initThemeObserver = function() {
        // Prevent multiple observers
        if (window.eolThemeObserver) return;

        const observer = new MutationObserver(() => {
            const isDark = eolUtils.isDarkMode();
            document.dispatchEvent(new CustomEvent('theme-changed', {
                detail: { isDark, theme: isDark ? 'dark' : 'light' }
            }));
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['class', 'data-theme']
        });

        window.eolThemeObserver = observer;
    };

    /**
     * Listen for theme changes and execute callback
     * @param {Function} callback - Function to call when theme changes
     * @returns {Function} Cleanup function to remove listener
     */
    eolUtils.onThemeChange = function(callback) {
        const handler = (event) => callback(event.detail);
        document.addEventListener('theme-changed', handler);

        // Return cleanup function
        return () => document.removeEventListener('theme-changed', handler);
    };

    // Expose theme utilities globally
    window.isDarkMode = eolUtils.isDarkMode;
    window.getCSSVariable = eolUtils.getCSSVariable;
    window.getThemedColor = eolUtils.getThemedColor;
    window.getThemedChartColors = eolUtils.getThemedChartColors;
    window.getFlowDiagramColors = eolUtils.getFlowDiagramColors;

    // Auto-initialize theme observer
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => eolUtils.initThemeObserver());
    } else {
        eolUtils.initThemeObserver();
    }

    console.log('✅ EOL Utilities loaded successfully (with dark mode support)');
})();
