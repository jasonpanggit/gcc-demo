/**
 * Agent Communication Handler - ES Module
 * Handles agent interactions and communication flow visualization
 * Optimized for performance and bundle size
 */

/**
 * AgentCommunicationHandler class for managing agent interactions
 * @class
 */
export class AgentCommunicationHandler {
    constructor(options = {}) {
        this.interactions = [];
        this.agentFlow = [];
        this.tokenUsage = { prompt: 0, completion: 0 };
        this.taskStartTime = null;
        this.taskCompleted = false;

        this.containerId = options.containerId || 'communicationsStream';
        this.showFlow = options.showFlow ?? true;
        this.autoExpand = options.autoExpand ?? true;
        this.autoScroll = options.autoScroll ?? true;
        this.titles = {
            interactions: '🤖 Agent Interactions',
            flow: '🔄 Agent Flow',
            ...options.titles
        };

        this.expandedIds = new Set();
        this._initialized = false;
    }

    /**
     * Initialize or reset the communication stream
     */
    initialize() {
        if (this._initialized) {
            console.info('AgentComm: initialize() skipped (already initialized) for', this.containerId);
            return;
        }

        this.interactions = [];
        this.agentFlow = [];
        this.tokenUsage = { prompt: 0, completion: 0 };
        this.taskStartTime = Date.now();
        this.taskCompleted = false;
        this.expandedIds = new Set();
        this.clearDisplay();

        this._initialized = true;
    }

    /**
     * Add a new agent interaction
     * @param {string} agent - Agent name/identifier
     * @param {string} content - Interaction content
     * @param {string} type - Interaction type
     * @param {Object} metadata - Additional metadata
     * @returns {string} Unique interaction ID
     */
    addInteraction(agent, content, type = 'text', metadata = {}) {
        // Extract JSON display blocks from content if needed
        if (!metadata.input && !metadata.output && content) {
            this._extractJsonBlocks(content, metadata);
        }

        const interaction = {
            agent: this.formatAgentDisplay(agent),
            timestamp: new Date().toLocaleTimeString(),
            type,
            content,
            metadata,
            id: `interaction_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        };

        this.interactions.push(interaction);
        this.updateAgentFlow(agent);
        this.displayInteractions();

        return interaction.id;
    }

    /**
     * Extract JSON blocks from HTML content
     * @private
     */
    _extractJsonBlocks(content, metadata) {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(content, 'text/html');
            const pres = doc.querySelectorAll('pre.json-display');

            if (pres.length > 0) {
                metadata.input = this._parseJsonSafe(pres[0].textContent);
            }
            if (pres.length > 1) {
                metadata.output = this._parseJsonSafe(pres[1].textContent);
            }
        } catch (e) {
            console.error('Error extracting json-display blocks:', e);
        }
    }

    /**
     * Safely parse JSON with fallback
     * @private
     */
    _parseJsonSafe(text) {
        try {
            return JSON.parse(text);
        } catch {
            return text.trim();
        }
    }

    /**
     * Add task completion message
     * @param {number} elapsedTime - Elapsed time in ms
     */
    addCompletionMessage(elapsedTime) {
        this.taskCompleted = true;
        this.addInteraction(
            '✅ System',
            `Task completed in ${(elapsedTime / 1000).toFixed(2)} seconds`,
            'completion'
        );
    }

    /**
     * Add token usage summary
     */
    addTokenSummary(promptTokens, completionTokens, elapsedTime) {
        if (promptTokens > 0 || completionTokens > 0) {
            const totalTokens = promptTokens + completionTokens;
            const tokenSummary = `
                <div class="token-summary">
                    <h6>📊 Token Usage Summary</h6>
                    <div class="token-stats">
                        <div class="token-stat">
                            <strong>Prompt Tokens:</strong> ${promptTokens.toLocaleString()}
                        </div>
                        <div class="token-stat">
                            <strong>Completion Tokens:</strong> ${completionTokens.toLocaleString()}
                        </div>
                        <div class="token-stat">
                            <strong>Total Tokens:</strong> ${totalTokens.toLocaleString()}
                        </div>
                        <div class="token-stat">
                            <strong>Elapsed Time:</strong> ${(elapsedTime / 1000).toFixed(2)}s
                        </div>
                    </div>
                </div>
            `;

            this.addInteraction('📊 System Analytics', tokenSummary, 'analytics');
        }
    }

    /**
     * Update agent flow visualization
     */
    updateAgentFlow(agent) {
        const cleanAgent = this.cleanAgentName(agent);

        if (!cleanAgent.includes('System') &&
            (!this.agentFlow.length || this.agentFlow[this.agentFlow.length - 1] !== cleanAgent)) {
            this.agentFlow.push(cleanAgent);
        }
    }

    /**
     * Clean agent name by removing emojis and suffixes
     */
    cleanAgentName(agent) {
        return agent
            .replace(/[\u{1F000}-\u{1F9FF}]/gu, '')
            .replace(/\s*(Agent|Bot)$/i, '')
            .trim();
    }

    /**
     * Format agent display name with emoji
     */
    formatAgentDisplay(source) {
        const sourceMapping = {
            'user': '👤 User',
            'orchestrator': '🎯 Orchestrator Agent',
            'microsoft': '🪟 Microsoft Agent',
            'redhat': '🎩 Red Hat Agent',
            'ubuntu': '🟠 Ubuntu Agent',
            'python': '🐍 Python Agent',
            'nodejs': '🟢 Node.js Agent',
            'endoflife': '📅 EndOfLife Agent',
            'system': '⚙️ System',
            'generic': '💻 Generic Agent'
        };

        const normalized = source.toLowerCase();

        // Try exact match
        if (sourceMapping[normalized]) {
            return sourceMapping[normalized];
        }

        // Try substring match
        for (const [key, value] of Object.entries(sourceMapping)) {
            if (normalized.includes(key)) {
                return value;
            }
        }

        return `🤖 ${source}`;
    }

    /**
     * Check if container is scrolled near bottom
     */
    isNearBottom(elem, threshold = 150) {
        if (!elem) return true;
        try {
            const distance = elem.scrollHeight - elem.scrollTop - elem.clientHeight;
            return distance <= threshold;
        } catch {
            return true;
        }
    }

    /**
     * Display all interactions
     */
    displayInteractions() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error(`Container ${this.containerId} not found`);
            return;
        }

        if (this.interactions.length === 0) {
            this._setEmptyState(container);
            return;
        }

        // Two-column layout or chat-style
        if (this.showFlow) {
            this._createTwoColumnLayout(container);
            this.renderInteractions();
            this.renderAgentFlow();
        } else {
            this._createChatLayout(container);
            this.renderInteractions();
        }
    }

    /**
     * Render interaction cards
     */
    renderInteractions() {
        const content = document.getElementById(`${this.containerId}_interactionsContent`);
        if (!content) return;

        const wasNearBottom = this.isNearBottom(content);

        // Clear content efficiently
        while (content.firstChild) {
            content.removeChild(content.firstChild);
        }

        this.interactions.forEach((interaction) => {
            const interactionElement = document.createElement('div');
            interactionElement.className = `interaction-card ${interaction.type}`;

            if (!this.showFlow) {
                // Chat-style simplified card
                interactionElement.innerHTML = `
                    <div class="chat-agent-info">
                        <strong>${interaction.agent}</strong>
                        <span class="timestamp">${interaction.timestamp}</span>
                    </div>
                    <div class="chat-content">${this.formatInteractionContent(interaction)}</div>
                `;
            } else {
                // Full card with toggle
                const hasMetaInput = interaction.metadata?.input;
                const hasMetaOutput = interaction.metadata?.output;
                const shouldExpand = this.autoExpand && (hasMetaInput || hasMetaOutput);
                const contentDisplay = shouldExpand ? 'block' : 'none';
                const toggleIconClass = shouldExpand ? 'fas fa-chevron-up' : 'fas fa-chevron-down';

                interactionElement.innerHTML = `
                    <div class="interaction-header" onclick="toggleInteraction('${interaction.id}')">
                        <div class="agent-info">
                            <strong>${interaction.agent}</strong>
                            <span class="timestamp">${interaction.timestamp}</span>
                        </div>
                        <div class="interaction-toggle">
                            <i class="${toggleIconClass}" id="toggle_${interaction.id}"></i>
                        </div>
                    </div>
                    <div class="interaction-content" id="content_${interaction.id}" style="display: ${contentDisplay};">
                        ${this.formatInteractionContent(interaction)}
                    </div>
                `;
            }

            content.appendChild(interactionElement);
        });

        // Smart auto-scroll
        if (wasNearBottom && this.autoScroll) {
            requestAnimationFrame(() => {
                content.scrollTo({ top: content.scrollHeight, behavior: 'smooth' });
            });
        }
    }

    /**
     * Format interaction content based on type
     */
    formatInteractionContent(interaction) {
        switch (interaction.type) {
            case 'image':
                return `<img src="${interaction.content}" class="interaction-image" alt="Agent Generated Image">`;
            case 'analytics':
            case 'completion':
                return `<div class="${interaction.type}-message">${interaction.content}</div>`;
            case 'error':
                return `<div class="error-message">${interaction.content}</div>`;
            default:
                return this._formatTextContent(interaction);
        }
    }

    /**
     * Format text content with metadata
     * @private
     */
    _formatTextContent(interaction) {
        const meta = interaction.metadata || {};
        const action = meta.action || '';
        let parts = '';

        if (interaction.content?.trim()) {
            const raw = String(interaction.content);
            const looksHtml = /<\/?(pre|div|img|span|code)[\s>]/i.test(raw);
            const hasAction = /<strong>Action:<\/strong>/i.test(raw);

            if (looksHtml) {
                parts += `<div class="text-content mt-2">${raw}</div>`;
                if (!hasAction && action) {
                    parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
                }
            } else {
                if (action) {
                    parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
                }
                parts += `<div class="text-content mt-2">${this._formatMarkdown(raw)}</div>`;
            }
        } else if (action) {
            parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
        }

        return parts || `<div class="text-content">${this._formatMarkdown(interaction.content)}</div>`;
    }

    /**
     * Format markdown-like syntax
     * @private
     */
    _formatMarkdown(content) {
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    /**
     * Escape HTML entities
     */
    escapeHtml(unsafe) {
        if (!unsafe) return '';
        return String(unsafe)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    /**
     * Render agent flow visualization
     */
    renderAgentFlow() {
        const flowContent = document.getElementById(`${this.containerId}_agentFlowContent`);
        if (!flowContent) return;

        if (this.agentFlow.length === 0) {
            flowContent.innerHTML = '<div class="no-flow">No agents active yet. Start a task to see the flow!</div>';
            return;
        }

        flowContent.innerHTML = this._createFlowDiagram();
    }

    /**
     * Create visual flow diagram
     * @private
     */
    _createFlowDiagram() {
        const agentColors = {
            'User': '#e3f2fd',
            'Orchestrator': '#f3e5f5',
            'Microsoft EOL': '#e8f5e8',
            'EndOfLife': '#fff3e0',
            'Generic': '#fce4ec'
        };

        let flowHtml = '<div class="flow-diagram">';

        if (!this.agentFlow.includes('User')) {
            this.agentFlow.unshift('User');
        }

        this.agentFlow.forEach((agent, index) => {
            const color = agentColors[agent] || '#f5f5f5';
            const isLast = index === this.agentFlow.length - 1;

            flowHtml += `
                <div class="flow-node" style="background-color: ${color}">
                    <div class="node-content">${agent}</div>
                </div>
            `;

            if (!isLast) {
                flowHtml += '<div class="flow-arrow">↓</div>';
            }
        });

        if (this.taskCompleted) {
            flowHtml += `
                <div class="flow-arrow completion">↓</div>
                <div class="flow-node completion" style="background-color: #c8e6c9">
                    <div class="node-content">✅ Completed</div>
                </div>
            `;
        }

        flowHtml += '</div>';
        return flowHtml;
    }

    /**
     * Expand/collapse interaction
     */
    expandInteraction(interactionId, force) {
        const content = document.getElementById(`content_${interactionId}`);
        const toggle = document.getElementById(`toggle_${interactionId}`);

        if (!content) return;

        const currentlyHidden = content.style.display === 'none';
        const shouldShow = typeof force === 'boolean' ? force : currentlyHidden;

        content.style.display = shouldShow ? 'block' : 'none';
        if (toggle) {
            toggle.className = shouldShow ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
        }

        if (shouldShow) {
            this.expandedIds.add(interactionId);
        } else {
            this.expandedIds.delete(interactionId);
        }
    }

    /**
     * Clear display
     */
    clearDisplay() {
        const container = document.getElementById(this.containerId);
        if (container) {
            this._setEmptyState(container);
        }
    }

    /**
     * Get interactions copy
     */
    getInteractions() {
        return [...this.interactions];
    }

    /**
     * Clear all interactions
     */
    clearInteractions() {
        this.interactions = [];
        this.agentFlow = [];
        this.taskCompleted = false;
        this.clearDisplay();
    }

    /**
     * Reset handler to fresh state
     */
    reset() {
        this.interactions = [];
        this.agentFlow = [];
        this.expandedIds = new Set();
        this.taskCompleted = false;
        this.taskStartTime = Date.now();
        this.tokenUsage = { prompt: 0, completion: 0 };
        this.clearDisplay();
        this._initialized = false;
    }

    /**
     * Set empty state
     * @private
     */
    _setEmptyState(container) {
        container.innerHTML = '<div class="no-interactions">No agent interactions yet.</div>';
    }

    /**
     * Create two-column layout
     * @private
     */
    _createTwoColumnLayout(container) {
        container.innerHTML = `
            <div class="agent-communications-container">
                <div class="interactions-column">
                    <h5 class="section-title">${this.titles.interactions}</h5>
                    <div id="${this.containerId}_interactionsContent" class="interactions-content"></div>
                </div>
                <div class="flow-column">
                    <h5 class="section-title">${this.titles.flow}</h5>
                    <div id="${this.containerId}_agentFlowContent" class="agent-flow-content"></div>
                </div>
            </div>
        `;
    }

    /**
     * Create chat-style layout
     * @private
     */
    _createChatLayout(container) {
        container.innerHTML = `
            <div class="agent-communications-chat">
                <div id="${this.containerId}_interactionsContent" class="chat-interactions-content"></div>
            </div>
        `;
    }
}

// Export helper functions
export function hasContent(v) {
    if (v === undefined || v === null) return false;
    if (typeof v === 'string') return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === 'object') return Object.keys(v).length > 0;
    return true;
}

export function parseMaybeJson(value) {
    if (value === undefined || value === null) return value;
    if (typeof value === 'object') return value;
    if (typeof value !== 'string') return value;
    const trimmed = value.trim();
    if (trimmed === '') return null;
    try {
        return JSON.parse(trimmed);
    } catch {
        return trimmed;
    }
}

export function formatStatus(status) {
    if (!status) return 'Unknown';
    const stat = status.toLowerCase();
    if (stat.includes('in_progress') || stat.includes('running')) return 'Request';
    if (stat.includes('completed') || stat.includes('success')) return 'Completed';
    if (stat.includes('failed') || stat.includes('error')) return 'Failed';
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function formatActionDescription(action) {
    if (!action) return 'No description available';

    const actionMappings = {
        'get_eol_data': 'EOL Data Lookup',
        'search': 'Search Operation',
        'message_sent': 'Message Transmission',
        'tool_call': 'Tool Execution'
    };

    if (actionMappings[action]) {
        return actionMappings[action];
    }

    return action
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase())
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}

export function normalizeCommPayload(comm) {
    comm.agent_name = comm.agent_name || comm.agent || comm.agentName || comm.name || '';
    comm.action = comm.action || comm.type || comm.task || '';

    let inputCandidate = comm.input || comm.inputs || comm.request || null;
    let outputCandidate = comm.output || comm.result || comm.payload || null;

    comm._input = parseMaybeJson(inputCandidate);
    comm._output = parseMaybeJson(outputCandidate);

    if (!hasContent(comm._output) && comm.data && typeof comm.data === 'object') {
        comm._output = comm.data;
    }

    if (comm.action && typeof comm.action !== 'string') {
        comm.action = String(comm.action);
    }

    return comm;
}
