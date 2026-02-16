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
        }
    } catch (error) {
        console.error('Error loading capabilities:', error);
    }
}

/**
 * Render capabilities by category
 */
function renderCapabilities(data) {
    const container = document.getElementById('capabilities-container');
    const categories = data.categories;

    let html = '';

    for (const [category, capabilities] of Object.entries(categories)) {
        const categoryTitle = category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        html += `
            <div class="capability-category">
                <h6><i class="fas fa-folder-open me-2"></i>${categoryTitle}</h6>
                ${capabilities.map(cap => `
                    <div class="capability-item">
                        <strong>${cap.name}</strong><br>
                        <small>${cap.description}</small>
                    </div>
                `).join('')}
            </div>
        `;
    }

    container.innerHTML = html;
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

            if (data.data && data.data.results) {
                // Format the results nicely
                responseContent = formatSREResponse(data.data);
            } else if (data.data && data.data.response) {
                responseContent = data.data.response;
            } else {
                responseContent = JSON.stringify(data.data, null, 2);
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

    if (data.summary) {
        html += `<div class="mb-3"><strong>Summary:</strong><br>${data.summary}</div>`;
    }

    if (data.results) {
        html += '<div class="mb-2"><strong>Results:</strong></div>';
        for (const [key, value] of Object.entries(data.results)) {
            html += `<div class="ms-3 mb-2">`;
            html += `<strong>${key}:</strong> `;
            if (typeof value === 'object') {
                html += `<pre class="mt-1">${JSON.stringify(value, null, 2)}</pre>`;
            } else {
                html += value;
            }
            html += `</div>`;
        }
    }

    if (data.recommendations && data.recommendations.length > 0) {
        html += '<div class="mt-3"><strong>Recommendations:</strong><ul class="mt-2">';
        data.recommendations.forEach(rec => {
            html += `<li>${rec}</li>`;
        });
        html += '</ul></div>';
    }

    return html || 'Request completed successfully';
}

        // Re-enable input
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i>Send';
    });
}
