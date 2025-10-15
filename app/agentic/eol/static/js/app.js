// Main JavaScript functionality for EOL Agentic App

// Global state management
window.eolApp = {
    currentUser: null,
    config: {
        apiBaseUrl: '',
        defaultTimeout: 30000,
        maxRetries: 3
    },
    cache: new Map(),
    eventListeners: new Map()
};

// Utility functions
const utils = {
    // Debounce function for search inputs
    debounce: function (func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Format dates consistently
    formatDate: function (dateString) {
        if (!dateString) return 'N/A';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    },

    // Format relative time
    formatRelativeTime: function (dateString) {
        if (!dateString) return 'Unknown';
        const date = new Date(dateString);
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);

        if (diffInSeconds < 60) return 'Just now';
        if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
        if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
        if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;

        return utils.formatDate(dateString);
    },

    // Escape HTML to prevent XSS
    escapeHtml: function (text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // Show toast notifications
    showToast: function (message, type = 'info', duration = 3000) {
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
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${utils.escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        container.appendChild(toast);

        // Show toast
        const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: duration });
        bsToast.show();

        // Remove from DOM after hiding
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    },

    // Copy text to clipboard
    copyToClipboard: async function (text) {
        try {
            await navigator.clipboard.writeText(text);
            utils.showToast('Copied to clipboard!', 'success');
            return true;
        } catch (err) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            try {
                document.execCommand('copy');
                utils.showToast('Copied to clipboard!', 'success');
                return true;
            } catch (fallbackErr) {
                utils.showToast('Failed to copy to clipboard', 'danger');
                return false;
            } finally {
                document.body.removeChild(textArea);
            }
        }
    },

    // Generate unique ID
    generateId: function () {
        return 'id_' + Math.random().toString(36).substr(2, 9);
    },

    // Validate email
    isValidEmail: function (email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },

    // Get URL parameters
    getUrlParams: function () {
        return new URLSearchParams(window.location.search);
    },

    // Update URL without page reload
    updateUrl: function (params) {
        const url = new URL(window.location);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.set(key, params[key]);
            } else {
                url.searchParams.delete(key);
            }
        });
        window.history.replaceState({}, '', url);
    }
};

// API helper functions
const api = {
    // Unwrap StandardResponse format to get actual data
    // StandardResponse: { success: bool, data: [], count: int, cached: bool, metadata: {} }
    // Returns: First item from data array, or full data array if multiple items
    unwrapResponse: function (responseData) {
        // If it's already unwrapped or not a StandardResponse, return as-is
        if (!responseData || typeof responseData !== 'object') {
            return responseData;
        }

        // Check if this is a StandardResponse format
        if (responseData.hasOwnProperty('success') && responseData.hasOwnProperty('data') && Array.isArray(responseData.data)) {
            // If data array has exactly one item, unwrap it for convenience
            // This maintains backward compatibility with code expecting single objects
            if (responseData.data.length === 1) {
                return responseData.data[0];
            }
            // Return the full data array for multiple items
            return responseData.data;
        }

        // Not a StandardResponse, return as-is
        return responseData;
    },

    // Generic API call wrapper
    call: async function (endpoint, options = {}) {
        const {
            method = 'GET',
            body = null,
            headers = {},
            timeout = window.eolApp.config.defaultTimeout,
            retries = window.eolApp.config.maxRetries,
            unwrap = true  // New option: automatically unwrap StandardResponse
        } = options;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        const requestOptions = {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...headers
            },
            signal: controller.signal
        };

        if (body && method !== 'GET') {
            requestOptions.body = typeof body === 'string' ? body : JSON.stringify(body);
        }

        let lastError;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const response = await fetch(endpoint, requestOptions);
                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                
                // Automatically unwrap StandardResponse if requested
                const finalData = unwrap ? api.unwrapResponse(data) : data;
                
                return { success: true, data: finalData };
            } catch (error) {
                lastError = error;
                if (attempt < retries && !controller.signal.aborted) {
                    await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1))); // Exponential backoff
                }
            }
        }

        clearTimeout(timeoutId);
        return { success: false, error: lastError.message };
    },

    // Get software inventory
    getInventory: async function (limit = 25) {
        return await api.call(`/inventory?limit=${limit}`);
    },

    // Check EOL status
    checkEOL: async function (product, version = '') {
        const params = new URLSearchParams({ product });
        if (version) params.append('version', version);
        return await api.call(`/eol?${params}`);
    },

    // Send chat message
    sendChatMessage: async function (message) {
        return await api.call('/chat', {
            method: 'POST',
            body: { message }
        });
    }
};

// Internal Map used by the cache implementation. Kept separate from the
// exported `window.eolApp.cache` object to avoid confusing the interface with
// the underlying storage implementation.
const cacheStore = new Map();

// Cache management
const cache = {
    set: function (key, value, ttl = 300000) { // Default 5 minutes
        const item = {
            value,
            expiry: Date.now() + ttl
        };
        // Use internal store to avoid conflicts with the exported interface
        cacheStore.set(key, item);
    },

    get: function (key) {
        const item = cacheStore.get(key);
        if (!item) return null;

        if (Date.now() > item.expiry) {
            cacheStore.delete(key);
            return null;
        }

        return item.value;
    },

    clear: function () {
        cacheStore.clear();
    },

    cleanup: function () {
        const now = Date.now();
        for (const [key, item] of cacheStore.entries()) {
            if (now > item.expiry) {
                cacheStore.delete(key);
            }
        }
    }
};

// ...existing code...

// Event management
const events = {
    on: function (event, callback) {
        if (!window.eolApp.eventListeners.has(event)) {
            window.eolApp.eventListeners.set(event, []);
        }
        window.eolApp.eventListeners.get(event).push(callback);
    },

    off: function (event, callback) {
        const listeners = window.eolApp.eventListeners.get(event);
        if (listeners) {
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    },

    emit: function (event, data) {
        const listeners = window.eolApp.eventListeners.get(event);
        if (listeners) {
            listeners.forEach(callback => callback(data));
        }
    }
};

// Initialize application
function initializeApp() {
    // Setup cache cleanup
    setInterval(() => cache.cleanup(), 60000); // Cleanup every minute

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Emit app ready event
    events.emit('app-ready');

    // EOL Agentic App initialized successfully
}

// Global helper for unwrapping API responses in HTML templates
// Usage: const data = unwrapApiResponse(await response.json());
window.unwrapApiResponse = api.unwrapResponse;

// Export to global scope
window.eolApp.utils = utils;
window.eolApp.api = api;
window.eolApp.cache = cache;
window.eolApp.events = events;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}
