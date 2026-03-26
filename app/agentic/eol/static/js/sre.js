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
 * Re-execute any <script> tags inside an element.
 * innerHTML assignment does not run scripts; this helper clones and
 * re-appends each script so Chart.js (and any other inline JS) fires.
 */
function executeScripts(element) {
    const scripts = element.querySelectorAll('script');
    scripts.forEach(function (oldScript) {
        const newScript = document.createElement('script');
        // Copy all attributes (src, type, …)
        Array.from(oldScript.attributes).forEach(function (attr) {
            newScript.setAttribute(attr.name, attr.value);
        });
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
}

function sanitizeHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = html;

    const forbiddenTags = ['style', 'iframe', 'object', 'embed'];
    forbiddenTags.forEach(tag => {
        template.content.querySelectorAll(tag).forEach(node => node.remove());
    });

    template.content.querySelectorAll('*').forEach(node => {
        [...node.attributes].forEach(attr => {
            const name = attr.name.toLowerCase();
            if (name.startsWith('on') || name === 'formaction' || name === 'srcdoc') {
                node.removeAttribute(attr.name);
            }

            if (node.tagName.toLowerCase() === 'script' && name === 'src') {
                node.removeAttribute(attr.name);
            }
        });
    });

    return template.innerHTML;
}

function buildStructuredHtml(text) {
    const container = document.createElement('div');
    const lines = text.split('\n');
    let index = 0;
    let hasRichContent = false;

    const isListLine = (line) => {
        const trimmed = line.trim();
        return /^[-*+]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed);
    };

    const parseCodeBlock = (startIndex) => {
        let idx = startIndex + 1;
        const codeLines = [];
        while (idx < lines.length && !lines[idx].trim().startsWith('```')) {
            codeLines.push(lines[idx]);
            idx++;
        }
        if (idx < lines.length && lines[idx].trim().startsWith('```')) {
            idx++;
        }
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        code.textContent = codeLines.join('\n');
        pre.appendChild(code);
        return { node: pre, nextIndex: idx, hasRichContent: true };
    };

    const parseListBlock = (startIndex) => {
        const firstLine = lines[startIndex];
        if (!firstLine || !isListLine(firstLine)) {
            return null;
        }

        const isOrdered = /^\d+\.\s+/.test(firstLine.trim());
        const list = document.createElement(isOrdered ? 'ol' : 'ul');
        let idx = startIndex;

        while (idx < lines.length) {
            const line = lines[idx];
            if (!line.trim() || !isListLine(line)) {
                break;
            }
            const trimmed = line.trim();
            const itemText = isOrdered
                ? trimmed.replace(/^\d+\.\s+/, '')
                : trimmed.replace(/^[-*+]\s+/, '');
            const li = document.createElement('li');
            li.textContent = itemText;
            list.appendChild(li);
            idx++;
        }

        return list.children.length ? { node: list, nextIndex: idx, hasRichContent: true } : null;
    };

    const parseParagraphBlock = (startIndex) => {
        let idx = startIndex;
        const collectedLines = [];

        while (idx < lines.length) {
            const line = lines[idx];
            if (!line.trim()) {
                break;
            }
            if (idx !== startIndex && (line.trim().startsWith('```') || isListLine(line))) {
                break;
            }
            collectedLines.push(line);
            idx++;
        }

        if (!collectedLines.length) {
            return { node: document.createTextNode(''), nextIndex: idx, hasRichContent: false };
        }

        const paragraph = document.createElement('p');
        collectedLines.forEach((line, lineIndex) => {
            if (lineIndex > 0) {
                paragraph.appendChild(document.createElement('br'));
            }
            paragraph.appendChild(document.createTextNode(line.trim()));
        });
        return { node: paragraph, nextIndex: idx, hasRichContent: false };
    };

    while (index < lines.length) {
        if (!lines[index].trim()) {
            index++;
            continue;
        }

        if (lines[index].trim().startsWith('```')) {
            const block = parseCodeBlock(index);
            container.appendChild(block.node);
            index = block.nextIndex;
            hasRichContent = true;
            continue;
        }

        const listBlock = parseListBlock(index);
        if (listBlock) {
            container.appendChild(listBlock.node);
            index = listBlock.nextIndex;
            hasRichContent = true;
            continue;
        }

        const paragraphBlock = parseParagraphBlock(index);
        container.appendChild(paragraphBlock.node);
        index = paragraphBlock.nextIndex;
        if (paragraphBlock.hasRichContent) {
            hasRichContent = true;
        }
    }

    return { html: container.innerHTML, hasRichContent };
}

function formatContent(text) {
    if (!text) {
        return { html: '', hasRichContent: false };
    }

    const trimmed = String(text).trim();
    if (!trimmed) {
        return { html: '', hasRichContent: false };
    }

    const containsHtml = /<\/?[a-z][\s\S]*>/i.test(trimmed);
    const isTrustedHtml = /<table|class=["']mcp-meta|<pre|<ul|<ol|<p[\s>]|<strong|<em|<h[1-6][\s>]|<a\s|<canvas|<script|<div[\s>]/.test(trimmed);

    if (containsHtml && isTrustedHtml) {
        return {
            html: sanitizeHtml(trimmed),
            hasRichContent: true
        };
    }

    const { html, hasRichContent } = buildStructuredHtml(trimmed);
    return {
        html: sanitizeHtml(html || `<p>${escapeHtml(trimmed)}</p>`),
        hasRichContent
    };
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

    const iconByType = {
        user: 'fa-user',
        agent: 'fa-robot',
        error: 'fa-exclamation-triangle',
        status: 'fa-circle-info'
    };

    const labelByType = {
        user: 'You',
        agent: 'Assistant',
        error: 'Assistant',
        status: 'Assistant'
    };

    const iconClass = iconByType[type] || 'fa-robot';
    const label = labelByType[type] || 'Assistant';
    const timestamp = new Date().toLocaleTimeString();

    const isUser = type === 'user';
    const formatted = isUser ? { html: `<p>${escapeHtml(String(content))}</p>`, hasRichContent: false } : formatContent(content);
    const rendered = formatted.html;
    const contentClass = formatted.hasRichContent ? 'chat-html-content' : 'chat-text-content';

    messageDiv.innerHTML = `
        <div class="chat-message-header">
            <span class="chat-message-label"><i class="fas ${iconClass}"></i>${label}</span>
            <span class="chat-message-time">${timestamp}</span>
        </div>
        <div class="chat-message-content ${contentClass}">${rendered}</div>
    `;

    chatHistory.appendChild(messageDiv);
    // Execute any <script> tags injected via innerHTML (e.g. Chart.js charts)
    executeScripts(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

/**
 * Ensure the Agent Communication section is visible.
 */
function showAgentCommsSection() {
    const section = document.getElementById('agent-comms-section');
    const btn = document.getElementById('toggle-comms-btn');

    if (section && section.style.display === 'none') {
        section.style.display = 'block';
    }

    if (btn) {
        btn.innerHTML = '<i class="fas fa-eye-slash me-1"></i>Hide';
    }
}

/**
 * Normalize agent communications from different response shapes.
 */
function extractAgentCommunications(payload) {
    if (!payload || typeof payload !== 'object') {
        return [];
    }

    const directCandidates = [
        payload.agent_communications,
        payload.communications,
        payload.communication_history,
        payload.interactions,
        payload.trace,
        payload.execution_trace,
        payload.raw_results && payload.raw_results.agent_communications,
        payload.raw_results && payload.raw_results.communications,
        payload.results && payload.results.agent_communications,
        payload.results && payload.results.communications,
        payload.results && payload.results.communication_history,
    ];

    for (const candidate of directCandidates) {
        if (Array.isArray(candidate) && candidate.length > 0) {
            return candidate;
        }
    }

    const toolResults = Array.isArray(payload.results)
        ? payload.results
        : (Array.isArray(payload.raw_results) ? payload.raw_results : []);

    if (toolResults.length > 0) {
        return toolResults.map((entry, index) => ({
            agent_name: entry.agent || entry.agent_name || 'sre-orchestrator',
            action: entry.action || entry.tool || `tool_step_${index + 1}`,
            tool: entry.tool || entry.tool_name || entry.toolName || entry.command || null,
            input: entry.input || entry.request || entry.parameters || null,
            output: entry.output || entry.result || entry.response || null,
            error: entry.error || null,
            status: entry.status || null,
            timestamp: entry.timestamp || new Date().toISOString(),
        }));
    }

    return [];
}

/**
 * Render agent communications in the shared communications panel.
 */
function renderAgentCommunications(payload) {
    const communications = extractAgentCommunications(payload);
    if (!communications.length) {
        return;
    }

    showAgentCommsSection();

    if (window.AgentComm && typeof window.AgentComm.display === 'function') {
        window.AgentComm.display(communications, {
            containerId: 'communicationsStream',
            showFlow: true,
            autoExpand: false,
            autoScroll: true,
        });
        return;
    }

    if (typeof displayAgentCommunications === 'function') {
        displayAgentCommunications(communications, {
            containerId: 'communicationsStream',
            showFlow: true,
            autoExpand: false,
            autoScroll: true,
        });
    }
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
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    // Add user message
    addMessage(query, 'user');

    // Clear input
    input.value = '';
    input.style.height = 'auto';

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
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
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
            renderAgentCommunications(data.data || {});
        } else {
            addMessage(`<i class="fas fa-exclamation-circle me-2"></i>${data.error || 'Request failed'}`, 'error');
        }
    }).catch(error => {
        console.error('Fetch error:', error);
        addMessage(`<i class="fas fa-exclamation-circle me-2"></i>Connection error: ${error.message}`, 'error');

        // Re-enable input
        input.disabled = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
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
                html += `<div class="mt-2">${renderToolResult(result.result)}</div>`;
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
 * Render a tool result object as structured HTML instead of raw JSON.
 * Handles double-serialized content strings (with literal \n) gracefully.
 */
function renderToolResult(raw) {
    // Unwrap MCP text-content wrapper: {success, content: [{type:"text", text:"..."}]}
    let data = raw;
    if (data && Array.isArray(data.content)) {
        const textItem = data.content.find(c => c.type === 'text' && c.text);
        if (textItem) {
            try { data = JSON.parse(textItem.text); } catch (_) { /* keep raw */ }
        }
    }
    // If data.parsed exists prefer that (already decoded)
    if (data && data.parsed && typeof data.parsed === 'object') {
        data = data.parsed;
    }
    // If it's still a string (double-serialized), try to parse it
    if (typeof data === 'string') {
        try { data = JSON.parse(data); } catch (_) { /* keep as string */ }
    }
    if (typeof data === 'string') {
        return `<pre class="p-2 bg-light rounded small" style="max-height:260px;overflow-y:auto;white-space:pre-wrap;">${escapeHtml(data)}</pre>`;
    }

    // Key display config: field → {label, icon, formatter}
    const FIELD_CONFIG = {
        health_status:       { label: 'Health',          icon: 'fa-heartbeat',        fmt: v => statusBadge(v) },
        container_app_name:  { label: 'Container App',   icon: 'fa-box',              fmt: null },
        resource_group:      { label: 'Resource Group',  icon: 'fa-folder',           fmt: null },
        total_logs:          { label: 'Total Logs',      icon: 'fa-list',             fmt: null },
        error_count:         { label: 'Errors',          icon: 'fa-times-circle',     fmt: v => `<span class="${v>0?'text-danger':'text-success'}">${v}</span>` },
        warning_count:       { label: 'Warnings',        icon: 'fa-exclamation-triangle', fmt: v => `<span class="${v>0?'text-warning':'text-success'}">${v}</span>` },
        table_used:          { label: 'Log Source',      icon: 'fa-database',         fmt: null },
        recent_errors:       { label: 'Recent Errors',   icon: 'fa-bug',              fmt: v => Array.isArray(v) && v.length===0 ? '<span class="text-success">None</span>' : null },
        recommendations:     { label: 'Recommendations', icon: 'fa-lightbulb',        fmt: null },
        timestamp:           { label: 'Checked At',      icon: 'fa-clock',            fmt: v => v ? new Date(v).toLocaleString() : null },
        note:                { label: 'Note',            icon: 'fa-info-circle',      fmt: null },
    };

    const SKIP_KEYS = new Set(['success', 'tool_name', 'resource_id', 'log_sample']);

    let rows = '';
    for (const [key, cfg] of Object.entries(FIELD_CONFIG)) {
        if (!(key in data)) continue;
        const val = data[key];
        let rendered;
        if (cfg.fmt) {
            rendered = cfg.fmt(val);
            if (rendered === null) rendered = escapeHtml(String(val));
        } else if (Array.isArray(val)) {
            if (val.length === 0) {
                rendered = '<span class="text-muted">None</span>';
            } else {
                rendered = '<ul class="mb-0 ps-3">' + val.map(item =>
                    `<li class="small">${escapeHtml(typeof item === 'object' ? JSON.stringify(item) : String(item))}</li>`
                ).join('') + '</ul>';
            }
        } else if (typeof val === 'object' && val !== null) {
            rendered = `<pre class="mb-0 small p-1 bg-light rounded" style="max-height:120px;overflow-y:auto;">${escapeHtml(JSON.stringify(val, null, 2))}</pre>`;
        } else {
            rendered = `<span class="small">${escapeHtml(String(val))}</span>`;
        }
        rows += `<tr>
            <td class="text-muted small pe-3 text-nowrap" style="width:1%"><i class="fas ${cfg.icon} me-1"></i>${cfg.label}</td>
            <td>${rendered}</td>
        </tr>`;
    }

    // Any remaining keys not in FIELD_CONFIG and not skipped
    for (const [key, val] of Object.entries(data)) {
        if (key in FIELD_CONFIG || SKIP_KEYS.has(key)) continue;
        let rendered;
        if (typeof val === 'object' && val !== null) {
            rendered = `<pre class="mb-0 small p-1 bg-light rounded" style="max-height:120px;overflow-y:auto;">${escapeHtml(JSON.stringify(val, null, 2))}</pre>`;
        } else {
            rendered = `<span class="small">${escapeHtml(String(val))}</span>`;
        }
        const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        rows += `<tr>
            <td class="text-muted small pe-3 text-nowrap" style="width:1%">${label}</td>
            <td>${rendered}</td>
        </tr>`;
    }

    if (!rows) {
        return `<pre class="p-2 bg-light rounded small" style="max-height:260px;overflow-y:auto;">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    }

    return `<table class="table table-sm table-borderless mb-0" style="font-size:0.85rem;">${rows}</table>`;
}

function statusBadge(v) {
    const s = String(v).toLowerCase();
    const cls = s === 'healthy' || s === 'running' || s === 'succeeded' ? 'success'
               : s === 'degraded' || s === 'warning' ? 'warning'
               : s === 'unhealthy' || s === 'failed' || s === 'error' ? 'danger'
               : 'secondary';
    return `<span class="badge bg-${cls}">${escapeHtml(String(v))}</span>`;
}

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
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


