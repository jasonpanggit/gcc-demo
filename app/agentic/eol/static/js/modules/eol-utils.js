/**
 * EOL Utilities - ES Module
 * Common functions for software EOL analysis
 * Optimized for performance and tree-shaking
 */

// ============================================
// Software Name Processing
// ============================================

export function cleanSoftwareName(name) {
    if (!name) return name;

    return name
        .replace(/\s*\(Arc-enabled\)/gi, '')
        .replace(/\s*\(x(64|86)\)/gi, '')
        .replace(/\s*(64|32)-bit/gi, '')
        .replace(/\s+/g, ' ')
        .trim();
}

export function parseVersionFromName(name) {
    if (!name) return { name, version: null };

    const versionPatterns = [
        /^(.+?)\s+(\d{4})$/i,
        /^(.+?)\s+(v?(?:\d+\.)+\d+(?:\.\d+)*)$/i,
        /^(.+?)\s+v?(\d+)$/i,
        /^(.+?)\s+(\d+\.\d+(?:\.\d+)?)$/i,
    ];

    for (const pattern of versionPatterns) {
        const match = name.match(pattern);
        if (match) {
            const baseName = match[1].trim();
            const version = match[2].trim();

            if (!isCommonSoftwareWord(version)) {
                return { name: baseName, version };
            }
        }
    }

    return { name, version: null };
}

export function isCommonSoftwareWord(word) {
    if (!word || typeof word !== 'string') return false;

    const commonWords = [
        'server', 'client', 'pro', 'professional', 'enterprise', 'standard',
        'express', 'developer', 'runtime', 'framework', 'sdk', 'tools',
        'service', 'pack', 'update', 'hotfix', 'patch'
    ];

    return commonWords.includes(word.toLowerCase());
}

// ============================================
// Agent Selection
// ============================================

export function getSelectedAgents(softwareName) {
    if (!softwareName || typeof softwareName !== 'string') {
        return [];
    }

    const softwareNameLower = softwareName.toLowerCase();
    const selectedAgents = [];

    const agentConfigs = [
        {
            keywords: ['windows', 'microsoft', 'office', 'sql server', 'iis', '.net'],
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

    selectedAgents.push({
        name: 'EndOfLife.date Agent',
        type: 'endoflife',
        icon: 'fas fa-calendar-times',
        reason: 'General EOL database'
    });

    return selectedAgents;
}

// ============================================
// Date Formatting
// ============================================

export function formatDate(dateString) {
    if (!dateString) return 'N/A';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return 'N/A';

        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch {
        return 'N/A';
    }
}

export function formatRelativeTime(dateString) {
    if (!dateString) return 'Unknown';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return 'Unknown';

        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);

        if (diffInSeconds < 60) return 'Just now';
        if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
        if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
        if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;

        return formatDate(dateString);
    } catch {
        return 'Unknown';
    }
}

// ============================================
// EOL Risk Assessment
// ============================================

export function daysUntilEOL(eolDate) {
    if (!eolDate) return null;
    try {
        const eol = new Date(eolDate);
        if (isNaN(eol.getTime())) return null;

        const now = new Date();
        const diffTime = eol - now;
        return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    } catch {
        return null;
    }
}

export function getRiskLevel(daysUntilEOL) {
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
}

export function getRiskBadgeClass(riskLevel) {
    const riskClasses = {
        'critical': 'bg-danger',
        'high': 'bg-warning text-dark',
        'medium': 'bg-info text-dark',
        'low': 'bg-success',
        'unknown': 'bg-secondary'
    };
    return riskClasses[riskLevel] || 'bg-secondary';
}

// ============================================
// HTML/Text Utilities
// ============================================

export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============================================
// UI Components
// ============================================

export function showToast(message, type = 'info', duration = 3000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');

    const flexDiv = document.createElement('div');
    flexDiv.className = 'd-flex';

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'toast-body';
    bodyDiv.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
    closeBtn.setAttribute('data-bs-dismiss', 'toast');

    flexDiv.appendChild(bodyDiv);
    flexDiv.appendChild(closeBtn);
    toast.appendChild(flexDiv);
    container.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: duration });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

export async function copyToClipboard(text) {
    if (!text) {
        console.warn('copyToClipboard: No text provided');
        return false;
    }

    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success');
        return true;
    } catch (err) {
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
                showToast('Copied to clipboard!', 'success');
                return true;
            }
        } catch {
            showToast('Failed to copy to clipboard', 'danger');
            return false;
        } finally {
            document.body.removeChild(textArea);
        }
    }
}

export function createSpinner(options = {}) {
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
}

export function createLoadingOverlay(message = 'Loading...') {
    const overlay = document.createElement('div');
    overlay.className = 'position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center bg-white bg-opacity-75';
    overlay.style.zIndex = '1050';

    const content = document.createElement('div');
    content.className = 'text-center';

    content.appendChild(createSpinner({ color: 'primary', className: 'mb-2' }));

    const text = document.createElement('div');
    text.className = 'text-muted';
    text.textContent = message;
    content.appendChild(text);

    overlay.appendChild(content);
    return overlay;
}

export function createModal(options = {}) {
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
        bodyEl.textContent = body;
    } else if (body instanceof HTMLElement) {
        bodyEl.appendChild(body);
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
}

// ============================================
// Performance Utilities
// ============================================

export function lazyLoad(target, loadCallback, options = {}) {
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

    if (element.dataset.lazyLoading === 'true') {
        return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                element.dataset.lazyLoading = 'true';

                try {
                    loadCallback(element);
                } catch (err) {
                    console.error('Error in lazy load callback:', err);
                    element.dataset.lazyLoadError = 'true';
                }

                obs.unobserve(entry.target);
                element.dataset.lazyLoaded = 'true';
                delete element.dataset.lazyLoading;
            }
        });
    }, observerOptions);

    observer.observe(element);
}

export function deferUntilIdle(callback, timeout = 2000) {
    if ('requestIdleCallback' in window) {
        requestIdleCallback(callback, { timeout });
    } else {
        setTimeout(callback, timeout);
    }
}

export function preload(url, as = 'fetch') {
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = as;
    link.href = url;

    if (as === 'script') {
        link.crossOrigin = 'anonymous';
    }

    document.head.appendChild(link);
}

// Export all as default object for backward compatibility
export default {
    cleanSoftwareName,
    parseVersionFromName,
    isCommonSoftwareWord,
    getSelectedAgents,
    formatDate,
    formatRelativeTime,
    daysUntilEOL,
    getRiskLevel,
    getRiskBadgeClass,
    escapeHtml,
    debounce,
    showToast,
    copyToClipboard,
    createSpinner,
    createLoadingOverlay,
    createModal,
    lazyLoad,
    deferUntilIdle,
    preload
};
