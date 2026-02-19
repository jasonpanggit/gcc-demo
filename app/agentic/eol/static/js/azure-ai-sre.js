/**
 * Azure AI SRE Agent Client
 * Handles SSE streaming communication with gccsreagent
 */

let eventSource = null;
let currentThreadId = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    refreshStatus();
    loadCapabilities();
});

/**
 * Refresh agent status
 */
async function refreshStatus() {
    const statusContainer = document.getElementById('status-container');
    statusContainer.innerHTML = '<p class="text-muted"><i class="fas fa-spinner fa-spin me-2"></i>Loading status...</p>';

    try {
        const response = await fetch('/api/sre-orchestrator/health');
        const data = await response.json();

        if (data.success && data.data) {
            const registry = data.data.registry || {};
            const status = data.data.status || 'unknown';
            const statusClass = status === 'healthy' ? 'success' : 'warning';
            const statusIcon = status === 'healthy' ? 'check-circle' : 'exclamation-triangle';

            statusContainer.innerHTML = `
                <div class="alert alert-${statusClass}">
                    <h6><i class="fas fa-${statusIcon} me-2"></i>${status.toUpperCase()}</h6>
                    <p class="mb-2"><strong>Total Agents:</strong> ${registry.total_agents || 0}</p>
                    <p class="mb-2"><strong>Healthy Agents:</strong> ${registry.healthy_agents || 0}</p>
                    <p class="mb-2"><strong>Total Tools:</strong> ${registry.total_tools || 0}</p>
                    <p class="mb-0"><em>SRE Orchestrator with 8 specialist agents ready</em></p>
                </div>
            `;
        } else {
            statusContainer.innerHTML = '<div class="alert alert-danger">Failed to load agent status</div>';
        }
    } catch (error) {
        console.error('Error loading status:', error);
        statusContainer.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
    }
}

/**
 * Load SRE capabilities
 */
async function loadCapabilities() {
    try {
        const response = await fetch('/api/sre-orchestrator/capabilities');
        const data = await response.json();

        if (data.success && data.data) {
            renderCapabilities(data.data);
        } else {
            console.warn('Capabilities data not available:', data);
            showCapabilitiesError('No capabilities data available');
        }
    } catch (error) {
        console.error('Error loading capabilities:', error);
        showCapabilitiesError(error.message);
    }
}

/**
 * Show capabilities error message
 */
function showCapabilitiesError(message) {
    const container = document.getElementById('capabilities-container');
    container.innerHTML = `<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2"></i>${message}</div>`;
}

/**
 * Render capabilities by category
 */
function renderCapabilities(data) {
    const container = document.getElementById('capabilities-container');
    
    // Validate data structure
    if (!data || typeof data !== 'object') {
        console.error('Invalid capabilities data structure:', data);
        showCapabilitiesError('Invalid capabilities data format');
        return;
    }

    const categories = data.categories || data;
    
    // Check if categories is an object
    if (typeof categories !== 'object' || categories === null) {
        console.error('Categories is not an object:', categories);
        showCapabilitiesError('Invalid categories format');
        return;
    }

    let html = '';

    for (const [category, capabilities] of Object.entries(categories)) {
        const categoryTitle = category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        // Ensure capabilities is an array
        const capabilitiesArray = Array.isArray(capabilities) ? capabilities : [];
        
        if (capabilitiesArray.length === 0) {
            continue; // Skip empty categories
        }

        html += `
            <div class="capability-category">
                <h6><i class="fas fa-folder-open me-2"></i>${categoryTitle}</h6>
                ${capabilitiesArray.map(cap => `
                    <div class="capability-item">
                        <strong>${cap.name || 'Unknown'}</strong><br>
                        <small>${cap.description || 'No description available'}</small>
                    </div>
                `).join('')}
            </div>
        `;
    }

    if (html) {
        container.innerHTML = html;
    } else {
        container.innerHTML = '<p class="text-muted">No capabilities available</p>';
    }
}

/**
 * Toggle capabilities section
 */
function toggleCapabilities() {
    const section = document.getElementById('capabilities-section');
    const btn = document.getElementById('toggle-capabilities-btn');
    const icon = btn.querySelector('i');

    if (section.style.display === 'none') {
        section.style.display = 'block';
        icon.className = 'fas fa-chevron-up me-1';
        btn.innerHTML = '<i class="fas fa-chevron-up me-1"></i>Collapse';
    } else {
        section.style.display = 'none';
        icon.className = 'fas fa-chevron-down me-1';
        btn.innerHTML = '<i class="fas fa-chevron-down me-1"></i>Expand';
    }
}

/**
 * Send example query
 */
function sendExample(query) {
    document.getElementById('chat-input').value = query;
    sendMessage();
}

/**
 * Clear chat history
 */
function clearChat() {
    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML = `
        <div class="text-center text-muted py-5">
            <i class="fas fa-robot fa-3x mb-3"></i>
            <p>Ask me about Azure resource health, incidents, or performance issues!</p>
        </div>
    `;
    currentThreadId = null;
}

/**
 * Add message to chat
 */
function addMessage(content, type = 'agent') {
    const chatHistory = document.getElementById('chat-history');

    // Remove placeholder if it exists
    const placeholder = chatHistory.querySelector('.text-center');
    if (placeholder) {
        placeholder.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type}`;
    messageDiv.innerHTML = content;

    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

/**
 * Send message to SRE agent
 */
function sendMessage() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const query = input.value.trim();

    if (!query) return;

    // Disable input while processing
    input.disabled = true;
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Sending...';

    // Add user message
    addMessage(query, 'user');

    // Clear input
    input.value = '';

    // Create request to orchestrator
    const url = '/api/sre-orchestrator/execute';

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            query: query
        })
    }).then(response => response.json())
    .then(data => {
        // Re-enable input
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>Send';
        input.focus();

        if (data.success) {
            // Format and display the response
            let responseContent = '';

            // Check if formatted HTML is available (preferred)
            if (data.data && data.data.formatted_html) {
                responseContent = data.data.formatted_html;
            }
            // Check for user interaction required
            else if (data.data && data.data.interaction_required) {
                responseContent = `<div class="alert alert-warning">
                    <i class="fas fa-question-circle me-2"></i>${data.data.message || 'User interaction required'}
                </div>`;
                // Could add interaction handling here
            }
            // Check for raw results to format
            else if (data.data && (data.data.raw_results || data.data.results)) {
                responseContent = formatSREResponse({
                    results: data.data.raw_results || data.data.results,
                    summary: data.data.summary || {},
                    intent: data.data.intent
                });
            }
            // Fallback: check for response field
            else if (data.data && data.data.response) {
                responseContent = data.data.response;
            }
            // Last resort: stringify the data
            else {
                responseContent = `<pre class="bg-light p-3 rounded">${JSON.stringify(data.data, null, 2)}</pre>`;
            }

            addMessage(responseContent, 'agent');
        } else {
            addMessage(`<i class="fas fa-exclamation-circle me-2"></i>${data.error || 'Request failed'}`, 'error');
        }
    }).catch(error => {
        console.error('Fetch error:', error);
        addMessage(`<i class="fas fa-exclamation-circle me-2"></i>Connection error: ${error.message}`, 'error');

        // Re-enable input
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>Send';
    });
}

/**
 * Format SRE response for display
 */
function formatSREResponse(data) {
    let html = '';
    
    // Handle both structures:
    // 1. Old: data.results = { summary: {}, results: [], ... }
    // 2. New: data = { results: [], summary: {}, ... }
    const results = Array.isArray(data.results) ? data.results : (data.results?.results || []);
    const summary = data.summary || data.results?.summary || {};
    const intent = data.intent || summary.intent || 'unknown';
    const message = data.message || data.results?.message;
    
    // Show intent and execution summary
    if (summary.total_tools > 0 || summary.successful > 0) {
        const intentIcon = getIntentIcon(intent);
        html += `<div class="alert alert-info mb-3">
            <strong><i class="${intentIcon} me-2"></i>Intent: ${intent.toUpperCase()}</strong><br>
            <small>Tools executed: ${summary.total_tools || 0} | 
            Success: ${summary.successful || 0} | 
            Failed: ${summary.failed || 0}${summary.skipped ? ` | Skipped: ${summary.skipped}` : ''}</small>
        </div>`;
    }
    
    // Show helpful message if present
    if (message) {
        html += `<div class="alert alert-warning mb-3">
            <i class="fas fa-info-circle me-2"></i>${message}
        </div>`;
    }
    
    // Show successful results
    if (results && results.length > 0) {
        html += '<div class="mb-3"><strong><i class="fas fa-check-circle me-2 text-success"></i>Results:</strong>';
        results.forEach(result => {
            const tool = result.tool || 'unknown';
            const status = result.status || 'success';
            const statusClass = status === 'success' ? 'success' : (status === 'error' ? 'danger' : 'warning');
            
            html += `<div class="ms-3 mb-2 p-2 border-start border-${statusClass}" style="border-width: 3px !important;">
                <strong>${tool}</strong> <span class="badge bg-${statusClass}">${status}</span><br>
                <small class="text-muted">Agent: ${result.agent || 'unknown'}</small>`;
            
            if (result.result) {
                html += `<pre class="mt-2 p-2 bg-light rounded" style="font-size: 0.85rem; max-height: 300px; overflow-y: auto;">${JSON.stringify(result.result, null, 2)}</pre>`;
            }
            html += `</div>`;
        });
        html += '</div>';
    }
    
    // Show skipped tools
    const skipped = data.skipped || data.results?.skipped || [];
    if (skipped && skipped.length > 0) {
        html += '<div class="mb-3"><strong><i class="fas fa-forward me-2 text-warning"></i>Skipped Tools:</strong>';
        html += '<div class="ms-3"><small class="text-muted">These tools were not executed because required parameters were not provided.</small></div>';
        skipped.forEach(result => {
            const tool = result.tool || 'unknown';
            html += `<div class="ms-3 mb-2 p-2 border-start border-warning" style="border-width: 3px !important;">
                <strong>${tool}</strong> <span class="badge bg-warning text-dark">skipped</span><br>
                <small class="text-muted">${result.result?.message || 'Parameters required'}</small>
            </div>`;
        });
        html += '</div>';
    }
    
    // Show errors
    const errors = data.errors || data.results?.errors || [];
    if (errors && errors.length > 0) {
        html += '<div class="mb-3"><strong><i class="fas fa-exclamation-triangle me-2 text-danger"></i>Errors:</strong>';
        errors.forEach(error => {
            const tool = error.tool || 'unknown';
            html += `<div class="ms-3 mb-2 p-2 border-start border-danger" style="border-width: 3px !important;">
                <strong>${tool}</strong> <span class="badge bg-danger">error</span><br>
                <small class="text-danger">${error.error || 'Unknown error'}</small>
            </div>`;
        });
        html += '</div>';
    }
    
    // Show category-specific summaries
    const health_summary = data.health_summary || data.results?.health_summary;
    if (health_summary) {
        const hs = health_summary;
        html += `<div class="alert alert-light mb-3">
            <strong><i class="fas fa-heartbeat me-2"></i>Health Summary:</strong><br>
            <div class="row mt-2">
                <div class="col-4 text-center">
                    <div class="text-success" style="font-size: 1.5rem;">${hs.healthy_resources || 0}</div>
                    <small class="text-muted">Healthy</small>
                </div>
                <div class="col-4 text-center">
                    <div class="text-danger" style="font-size: 1.5rem;">${hs.unhealthy_resources || 0}</div>
                    <small class="text-muted">Unhealthy</small>
                </div>
                <div class="col-4 text-center">
                    <div class="text-primary" style="font-size: 1.5rem;">${hs.total_checked || 0}</div>
                    <small class="text-muted">Total Checked</small>
                </div>
            </div>
        </div>`;
    }
    
    const cost_summary = data.cost_summary || data.results?.cost_summary;
    if (cost_summary) {
        html += `<div class="alert alert-light mb-3">
            <strong><i class="fas fa-dollar-sign me-2"></i>Cost Summary:</strong><br>
            <pre class="mt-2">${JSON.stringify(cost_summary, null, 2)}</pre>
        </div>`;
    }
    
    const performance_summary = data.performance_summary || data.results?.performance_summary;
    if (performance_summary) {
        html += `<div class="alert alert-light mb-3">
            <strong><i class="fas fa-chart-line me-2"></i>Performance Summary:</strong><br>
            <pre class="mt-2">${JSON.stringify(performance_summary, null, 2)}</pre>
        </div>`;
    }
    
    return html || '<div class="text-muted">Request completed successfully</div>';
}

/**
 * Get icon for intent category
 */
function getIntentIcon(intent) {
    const icons = {
        'health': 'fas fa-heartbeat',
        'incident': 'fas fa-exclamation-triangle',
        'performance': 'fas fa-chart-line',
        'cost': 'fas fa-dollar-sign',
        'slo': 'fas fa-chart-bar',
        'security': 'fas fa-shield-alt',
        'remediation': 'fas fa-wrench',
        'config': 'fas fa-cog',
        'general': 'fas fa-info-circle'
    };
    return icons[intent] || 'fas fa-info-circle';
}


