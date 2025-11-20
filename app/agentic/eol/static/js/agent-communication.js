// Enhanced Agent Communication Handler - inspired by the earlier multi-agent pattern
// Guard declaration so loading this script multiple times doesn't redeclare the class
// Define the class in an IIFE and attach it to window to avoid temporal-dead-zone
if (typeof window.AgentCommunicationHandler === 'undefined') {
    (function () {
        class AgentCommunicationHandler {
            // options: { containerId: 'communicationsStream', showFlow: true, titles: { interactions, flow } }
            constructor(options = {}) {
                this.interactions = [];
                this.agentFlow = [];
                this.tokenUsage = { prompt: 0, completion: 0 };
                this.taskStartTime = null;
                this.taskCompleted = false;

                this.containerId = options.containerId || 'communicationsStream';
                this.showFlow = typeof options.showFlow === 'boolean' ? options.showFlow : true;
                // Control automatic expansion and scrolling behavior per-handler
                this.autoExpand = typeof options.autoExpand === 'boolean' ? options.autoExpand : true;
                this.autoScroll = typeof options.autoScroll === 'boolean' ? options.autoScroll : true;
                this.titles = Object.assign({
                    interactions: '🤖 Agent Interactions',
                    flow: '🔄 Agent Flow'
                }, options.titles || {});
                // Track which interaction ids are expanded by user/logic so state survives re-renders
                this.expandedIds = new Set();
                // Initialization guard to prevent repeated expensive setup when initialize() is called multiple times
                this._initialized = false;
            }

            // Initialize or reset the communication stream
            initialize() {
                // try {
                //     console.info('AgentComm: handler.initialize() called for', this.containerId, 'at', new Date().toISOString());
                // } catch (e) { /* ignore logging errors */ }

                if (this._initialized) {
                    try { console.info('AgentComm: initialize() skipped (already initialized) for', this.containerId); } catch (e) { }
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

            // Add a new agent interaction
            addInteraction(agent, content, type = 'text', metadata = {}) {
                // If content contains <pre class="json-display"> blocks, try to extract them
                // and attach to metadata.input/output when metadata doesn't already include them.
                try {
                    if ((!metadata || metadata.input === undefined || metadata.output === undefined) && content && typeof content === 'string') {
                        const temp = document.createElement('div');
                        temp.innerHTML = content;
                        const pres = temp.querySelectorAll('pre.json-display');
                        if (pres && pres.length > 0) {
                            try {
                                const txt0 = pres[0].textContent || pres[0].innerText || pres[0].innerHTML;
                                const parser = (typeof parseMaybeJson === 'function') ? parseMaybeJson : (window.parseMaybeJson || null);
                                const parsed0 = parser ? parser(txt0) : (function () { try { return JSON.parse(txt0); } catch (e) { return txt0.trim(); } })();
                                if (metadata.input === undefined) metadata.input = parsed0;
                            } catch (e) {
                                // ignore parse errors
                            }
                        }
                        if (pres && pres.length > 1) {
                            try {
                                const txt1 = pres[1].textContent || pres[1].innerText || pres[1].innerHTML;
                                const parser = (typeof parseMaybeJson === 'function') ? parseMaybeJson : (window.parseMaybeJson || null);
                                const parsed1 = parser ? parser(txt1) : (function () { try { return JSON.parse(txt1); } catch (e) { return txt1.trim(); } })();
                                if (metadata.output === undefined) metadata.output = parsed1;
                            } catch (e) {
                                // ignore parse errors
                            }
                        }
                    }
                } catch (e) {
                    // Safety: don't block adding the interaction if extraction fails
                    console.error('Error extracting json-display blocks for metadata:', e);
                }

                const interaction = {
                    agent: this.formatAgentDisplay(agent),
                    timestamp: new Date().toLocaleTimeString(),
                    type: type,
                    content: content,
                    metadata: metadata,
                    id: `interaction_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
                };

                console.log(`🎯 addInteraction: Adding interaction for agent "${agent}", type "${type}", content length: ${content.length}`);
                this.interactions.push(interaction);
                console.log(`🎯 addInteraction: Total interactions now: ${this.interactions.length}`);
                
                this.updateAgentFlow(agent);
                this.displayInteractions();

                return interaction.id;
            }

            // Add task completion message
            addCompletionMessage(elapsedTime) {
                this.taskCompleted = true;
                this.addInteraction(
                    '✅ System',
                    `Task completed in ${(elapsedTime / 1000).toFixed(2)} seconds`,
                    'completion'
                );
            }

            // Add token usage summary
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

            // Update agent flow for visualization
            updateAgentFlow(agent) {
                const cleanAgent = this.cleanAgentName(agent);

                // Skip system nodes and avoid duplicates
                if (!cleanAgent.includes('System') &&
                    (!this.agentFlow.length || this.agentFlow[this.agentFlow.length - 1] !== cleanAgent)) {
                    this.agentFlow.push(cleanAgent);
                }
            }

            // Clean agent name for display
            cleanAgentName(agent) {
                return agent
                    // Remove all emoji icons used in agent display
                    .replace(/🤖|🌐|📁|💻|👤|✅|📊|🎯|👨‍💼|⚙️|🔐|📅|🪟|🐧|🟠|🎩|🔴|🌀|🔵|🦎|🔶|🍎|🐳|☸️|☁️|🟢|🐍|☕|🔷|🐘|💎|🐹|🦀|🐬|🍃|🔍|🔒|📈|⚠️|🔌|🔗|🪝|🔄|📝|🔔|💬|📧|💾|🗃️|🛡️|⚖️/g, '')
                    // Remove common agent suffixes
                    .replace(/\s*Agent$/i, '')
                    .replace(/\s*Bot$/i, '')
                    .trim();
            }

            // Format agent display with emojis
            formatAgentDisplay(source) {
                const sourceMapping = {
                    // User/Human agents
                    'user': '👤 User',
                    'you': '👤 You', 
                    'me': '👤 You',
                    'self': '👤 You',
                    'human': '👤 Human',
                    
                    // System and orchestration
                    'orchestrator': '🎯 Orchestrator Agent',
                    'coordinator': '🎯 Coordinator',
                    'manager': '👨‍💼 Manager Agent',
                    'system': '⚙️ System',
                    'admin': '🔐 Admin',
                    
                    // EOL specific agents
                    'microsofteol': '🪟 Microsoft EOL Agent',
                    'endoflife': '� EndOfLife Agent',
                    'eol': '📅 EOL Agent',
                    'microsoft': '🪟 Microsoft Agent',
                    'ms': '🪟 Microsoft',
                    
                    // Platform/OS specific agents
                    'windows': '🪟 Windows Agent',
                    'linux': '🐧 Linux Agent',
                    'ubuntu': '🟠 Ubuntu Agent',
                    'redhat': '🎩 Red Hat Agent',
                    'centos': '🔴 CentOS Agent',
                    'debian': '🌀 Debian Agent',
                    'fedora': '🔵 Fedora Agent',
                    'suse': '🦎 SUSE Agent',
                    'oracle': '� Oracle Agent',
                    'macos': '🍎 macOS Agent',
                    'apple': '🍎 Apple Agent',
                    
                    // Technology specific agents
                    'docker': '🐳 Docker Agent',
                    'kubernetes': '☸️ Kubernetes Agent',
                    'aws': '☁️ AWS Agent',
                    'azure': '☁️ Azure Agent',
                    'gcp': '☁️ GCP Agent',
                    'cloud': '☁️ Cloud Agent',
                    
                    // Development tools
                    'nodejs': '🟢 Node.js Agent',
                    'python': '🐍 Python Agent',
                    'java': '☕ Java Agent',
                    'dotnet': '🔷 .NET Agent',
                    'php': '🐘 PHP Agent',
                    'ruby': '💎 Ruby Agent',
                    'go': '🐹 Go Agent',
                    'rust': '🦀 Rust Agent',
                    
                    // Database agents
                    'mysql': '🐬 MySQL Agent',
                    'postgresql': '🐘 PostgreSQL Agent',
                    'mongodb': '🍃 MongoDB Agent',
                    'redis': '🔴 Redis Agent',
                    'elasticsearch': '🔍 Elasticsearch Agent',
                    
                    // Security and monitoring
                    'security': '🔒 Security Agent',
                    'monitoring': '📊 Monitoring Agent',
                    'analytics': '📈 Analytics Agent',
                    'audit': '🔍 Audit Agent',
                    'scanner': '🔍 Scanner Agent',
                    'vulnerability': '⚠️ Vulnerability Agent',
                    
                    // Web and API agents
                    'web': '🌐 Web Agent',
                    'api': '🔌 API Agent',
                    'rest': '🔌 REST Agent',
                    'graphql': '🔗 GraphQL Agent',
                    'webhook': '🪝 Webhook Agent',
                    
                    // Data and processing
                    'data': '📊 Data Agent',
                    'etl': '🔄 ETL Agent',
                    'transform': '🔄 Transform Agent',
                    'processor': '⚙️ Processor Agent',
                    'parser': '📝 Parser Agent',
                    'validator': '✅ Validator Agent',
                    
                    // Communication and messaging
                    'mail': '📧 Mail Agent',
                    'notification': '🔔 Notification Agent',
                    'messenger': '💬 Messenger Agent',
                    'chat': '💬 Chat Agent',
                    'slack': '💬 Slack Agent',
                    'teams': '💬 Teams Agent',
                    
                    // File and storage
                    'file': '📁 File Agent',
                    'storage': '💾 Storage Agent',
                    'backup': '💾 Backup Agent',
                    'archive': '🗃️ Archive Agent',
                    'sync': '🔄 Sync Agent',
                    
                    // Network and connectivity
                    'network': '🌐 Network Agent',
                    'proxy': '🛡️ Proxy Agent',
                    'loadbalancer': '⚖️ Load Balancer Agent',
                    'dns': '🌐 DNS Agent',
                    'vpn': '🔒 VPN Agent',
                    
                    // Generic fallbacks
                    'generic': '💻 Generic Agent',
                    'worker': '⚙️ Worker Agent',
                    'service': '⚙️ Service Agent',
                    'bot': '🤖 Bot',
                    'agent': '🤖 Agent'
                };

                const normalized = source.toLowerCase();
                
                // First try exact matches
                if (sourceMapping[normalized]) {
                    return sourceMapping[normalized];
                }
                
                // Then try substring matches (order matters - more specific first)
                for (const [key, value] of Object.entries(sourceMapping)) {
                    if (normalized.includes(key)) {
                        return value;
                    }
                }

                // Default fallback with robot icon
                return `🤖 ${source}`;
            }

            // Get just the icon for an agent (without the name)
            getAgentIcon(source) {
                const fullDisplay = this.formatAgentDisplay(source);
                // Extract just the emoji part (first character or emoji sequence)
                const iconMatch = fullDisplay.match(/^[\u{1F000}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]+/u);
                return iconMatch ? iconMatch[0] : '🤖';
            }

            // Utility: check whether a container is scrolled near the bottom
            isNearBottom(elem, threshold = 150) {
                if (!elem) return true;
                try {
                    const distance = elem.scrollHeight - elem.scrollTop - elem.clientHeight;
                    return distance <= threshold;
                } catch (e) {
                    return true;
                }
            }

            // Display all interactions in enhanced layout
            displayInteractions() {
                const container = document.getElementById(this.containerId);
                if (!container) {
                    console.error(`🚨 displayInteractions: Container ${this.containerId} not found`);
                    return;
                }

                // console.log(`🎯 displayInteractions: Starting with ${this.interactions.length} interactions, containerId: ${this.containerId}`);
                // console.log(`🎯 displayInteractions: showFlow: ${this.showFlow}, autoExpand: ${this.autoExpand}`);
                // console.log(`🎯 displayInteractions: Full interactions array:`, this.interactions);

                if (this.interactions.length === 0) {
                    console.log(`🚨 displayInteractions: No interactions to display, showing empty state`);
                    container.innerHTML = '<div class="no-interactions">No agent interactions yet.</div>';
                    return;
                }

                console.log(`🎯 displayInteractions: Rendering ${this.interactions.length} interactions...`);

                // Two-column layout or compact single-column (chat-style)
                if (this.showFlow) {
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

                    this.renderInteractions();
                    this.renderAgentFlow();
                } else {
                    // Chat-style single column
                    container.innerHTML = `
                <div class="agent-communications-chat">
                    <div id="${this.containerId}_interactionsContent" class="chat-interactions-content"></div>
                </div>
            `;

                    this.renderInteractions();
                }
            }

            // Render individual interactions
            renderInteractions() {
                const content = document.getElementById(`${this.containerId}_interactionsContent`);
                if (!content) {
                    console.error(`🚨 renderInteractions: Interactions content element not found: ${this.containerId}_interactionsContent`);
                    return;
                }
                
                // console.log(`🎯 renderInteractions: Starting with ${this.interactions.length} interactions`);
                // console.log(`🎯 renderInteractions: Content element found, current innerHTML length: ${content.innerHTML.length}`);
                
                // Preserve whether the user was near the bottom before rendering
                const wasNearBottom = this.isNearBottom(content);
                // Use handler's persisted expanded state (survives re-renders) instead of reading DOM
                const existingExpanded = this.expandedIds || new Set();

                // console.log(`🎯 renderInteractions: Clearing content and building HTML...`);
                content.innerHTML = '';

                this.interactions.forEach((interaction, index) => {
                    // console.log(`🎯 renderInteractions: Processing interaction ${index}:`, {
                    //     agent: interaction.agent,
                    //     type: interaction.type,
                    //     timestamp: interaction.timestamp
                    // });
                    
                    const interactionElement = document.createElement('div');
                    interactionElement.className = `interaction-card ${interaction.type}`;

                    // If chat-style (no flow), render a simplified card without toggle
                    if (!this.showFlow) {
                        const contentHtml = this.formatInteractionContent(interaction);
                        // console.log(`[AgentComm] Chat-style interaction ${index}: ${interaction.agent}, content length: ${contentHtml.length}`);
                        
                        interactionElement.innerHTML = `
                    <div class="chat-agent-info">
                        <strong>${interaction.agent}</strong>
                        <span class="timestamp">${interaction.timestamp}</span>
                    </div>
                    <div class="chat-content" id="content_${interaction.id}">
                        ${contentHtml}
                    </div>
                `;
                    } else {
                        // Auto-expand interaction if it contains structured input/output to surface JSON by default
                        const hasMetaInput = interaction.metadata && (window.hasContent ? window.hasContent(interaction.metadata.input) : hasContent(interaction.metadata.input));
                        const hasMetaOutput = interaction.metadata && (window.hasContent ? window.hasContent(interaction.metadata.output) : hasContent(interaction.metadata.output));
                        // Respect per-handler autoExpand option; if disabled, never auto-expand even if metadata present
                        const defaultShouldExpand = (this.autoExpand !== false) && (hasMetaInput || hasMetaOutput);
                        // Restore user-opened state if present, otherwise fall back to default
                        const restoredExpand = existingExpanded.has(interaction.id);
                        const shouldExpand = restoredExpand || defaultShouldExpand;
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

                // Auto-expand the latest interaction for flow-layout only
                if (this.showFlow && this.interactions.length > 0) {
                    const latestId = this.interactions[this.interactions.length - 1].id;
                    // Force-expanding instead of toggling avoids collapsing if already open
                    setTimeout(() => this.expandInteraction(latestId, true), 100);
                }

                // Smart autoscroll: only scroll to bottom if the user was already near the bottom
                const container = document.getElementById(this.containerId);
                if (container && wasNearBottom && this.autoScroll !== false) {
                    // Debounce scroll to next animation frame to avoid layout thrash/flicker
                    try {
                        const doScroll = () => {
                            try { container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' }); }
                            catch (e) { container.scrollTop = container.scrollHeight; }
                        };
                        if (typeof window.requestAnimationFrame === 'function') {
                            window.requestAnimationFrame(doScroll);
                        } else {
                            setTimeout(doScroll, 16);
                        }
                    } catch (e) {
                        // fallback
                        try { container.scrollTop = container.scrollHeight; } catch (err) { /* ignore */ }
                    }
                }
                
                // Final debug check
                // console.log(`🎯 renderInteractions: COMPLETED! Final content innerHTML length: ${content.innerHTML.length}`);
                // console.log(`🎯 renderInteractions: Final content children count: ${content.children.length}`);
                // console.log(`🎯 renderInteractions: Content element ID: ${content.id}`);
                // if (content.children.length > 0) {
                //     console.log(`🎯 renderInteractions: First child class: ${content.children[0].className}`);
                // } else {
                //     console.log(`🚨 renderInteractions: NO CHILDREN FOUND IN CONTENT!`);
                // }
            }

            // Format interaction content based on type
            formatInteractionContent(interaction) {
                switch (interaction.type) {
                    case 'image':
                        return `<img src="${interaction.content}" class="interaction-image" alt="Agent Generated Image">`;

                    case 'analytics':
                        return interaction.content;

                    case 'completion':
                        return `<div class="completion-message">${interaction.content}</div>`;

                    case 'error':
                        return `<div class="error-message">${interaction.content}</div>`;

                    default:
                        // If metadata contains structured input/output, render them clearly
                        const meta = interaction.metadata || {};
                        const action = meta.action || '';
                        const input = meta.input !== undefined ? meta.input : null;
                        const output = meta.output !== undefined ? meta.output : null;

                        let parts = '';
                        
                        // Render the main content. If it already contains HTML markup (eg. <pre>, <div>, <img>),
                        // insert it as-is to avoid double-escaping or mangling. Otherwise, treat as plain text
                        // and run through the lightweight formatter.
                        if (interaction.content && String(interaction.content).trim()) {
                            const raw = String(interaction.content);
                            const looksHtml = /<\/?(pre|div|img|span|code|table|ul|ol|li|strong|em)[\s>]/i.test(raw);
                            
                            // Check if content already contains action to avoid duplication
                            const hasAction = /<strong>Action:<\/strong>/i.test(raw);
                            
                            if (looksHtml) {
                                parts += `<div class="text-content mt-2">${raw}</div>`;
                                
                                // Only add Action if NOT already present in content
                                if (!hasAction && action) {
                                    parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
                                }
                            } else {
                                // Plain text content - add metadata normally
                                if (action) {
                                    parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
                                }
                                parts += `<div class="text-content mt-2">${this.formatTextContent(raw)}</div>`;
                            }
                        } else {
                            // No content - render action only from metadata
                            if (action) {
                                parts += `<div class="comm-action"><strong>Action:</strong> ${this.escapeHtml(action)}</div>`;
                            }
                        }

                        // If nothing rendered, fall back to original content formatting
                        return parts || `<div class="text-content">${this.formatTextContent(interaction.content)}</div>`;
                }
            }

            // Try parsing a string as JSON and pretty-printing it, otherwise return original string
            tryPrettyJson(str) {
                if (!str) return '';
                try {
                    const parsed = JSON.parse(str);
                    return JSON.stringify(parsed, null, 2);
                } catch (e) {
                    return str;
                }
            }

            // Escape HTML entities to safely insert into pre/code blocks
            escapeHtml(unsafe) {
                if (unsafe === undefined || unsafe === null) return '';
                return String(unsafe)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
            }

            // Format text content with markdown-like styling
            formatTextContent(content) {
                return content
                    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em>$1</em>')
                    .replace(/`(.*?)`/g, '<code>$1</code>')
                    .replace(/\n/g, '<br>');
            }

            // Render agent flow visualization
            renderAgentFlow() {
                const flowContent = document.getElementById(`${this.containerId}_agentFlowContent`);
                if (!flowContent) return;

                if (this.agentFlow.length === 0) {
                    flowContent.innerHTML = '<div class="no-flow">No agents active yet. Start a task to see the flow!</div>';
                    return;
                }

                // Create a visual flow diagram
                const flowHtml = this.createFlowDiagram();
                flowContent.innerHTML = flowHtml;
            }

            // Create visual flow diagram
            createFlowDiagram() {
                const agentColors = {
                    'User': '#e3f2fd',
                    'Orchestrator': '#f3e5f5',
                    'Microsoft EOL': '#e8f5e8',
                    'EndOfLife': '#fff3e0',
                    'Generic': '#fce4ec'
                };

                let flowHtml = '<div class="flow-diagram">';

                // Add User node if not present
                if (!this.agentFlow.includes('User')) {
                    this.agentFlow.unshift('User');
                }

                this.agentFlow.forEach((agent, index) => {
                    const color = agentColors[agent] || '#f5f5f5';
                    const isLast = index === this.agentFlow.length - 1;

                    flowHtml += `
                <div class="flow-node" style="background-color: ${color}">
                    <div class="node-content">
                        ${agent}
                    </div>
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

            // Expand a specific interaction
            // force === true => expand, false => collapse, undefined => toggle (legacy)
            expandInteraction(interactionId, force) {
                const content = document.getElementById(`content_${interactionId}`);
                const toggle = document.getElementById(`toggle_${interactionId}`);

                if (!content) return;

                try {
                    // Determine target state
                    const currentlyHidden = content.style.display === 'none' || getComputedStyle(content).display === 'none';
                    let shouldShow;
                    if (typeof force === 'boolean') {
                        shouldShow = force;
                    } else {
                        shouldShow = currentlyHidden;
                    }

                    content.style.display = shouldShow ? 'block' : 'none';
                    if (toggle) {
                        toggle.className = shouldShow ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
                    }

                    // Persist state so future re-renders restore the user's choice
                    try {
                        if (!this.expandedIds) this.expandedIds = new Set();
                        if (shouldShow) this.expandedIds.add(interactionId);
                        else this.expandedIds.delete(interactionId);
                    } catch (e) { /* ignore persistence errors */ }
                } catch (e) {
                    // ignore DOM errors
                }
            }

            // Clear the display
            clearDisplay() {
                const container = document.getElementById(this.containerId);
                if (container) {
                    container.innerHTML = '<div class="no-interactions">No agent interactions yet.</div>';
                }
            }

            // Get current interactions
            getInteractions() {
                return [...this.interactions];
            }

            // Clear all interactions
            clearInteractions() {
                this.interactions = [];
                this.agentFlow = [];
                this.taskCompleted = false;
                this.clearDisplay();
            }

            // Comprehensive function to clear all interactions and agent flow data
            clearAllCommunications() {
                // Clearing all agent communications and flow data...
                
                // Clear all data arrays
                this.interactions = [];
                this.agentFlow = [];
                this.expandedIds = new Set();
                
                // Reset state flags
                this.taskCompleted = false;
                this.taskStartTime = Date.now();
                
                // Reset token usage
                this.tokenUsage = { prompt: 0, completion: 0 };
                
                // Clear the display
                this.clearDisplay();
                
                // Mark as uninitialized so next use will re-initialize
                this._initialized = false;
                
                // Agent communications and flow data cleared successfully
            }

            // Clear all communications and reset to fresh state (alias for convenience)
            reset() {
                this.clearAllCommunications();
            }
        }
        // Attach the local class to the window object so subsequent code can use it
        window.AgentCommunicationHandler = AgentCommunicationHandler;
    })();
}
// Ensure AgentCommunicationHandler is available on window (either we just defined it above or it was present)
if (typeof window.AgentCommunicationHandler === 'undefined') {
    // Defensive no-op fallback to avoid runtime crashes in unexpected load orders
    window.AgentCommunicationHandler = function () { throw new Error('AgentCommunicationHandler not initialized'); };
}

// Handlers registry so multiple pages/containers can use the same script
window.agentCommHandlers = window.agentCommHandlers || {};
// Global defaults (can be overridden per-handler or per-call)
window.agentCommDefaultOptions = window.agentCommDefaultOptions || { showFlow: true };

// Lightweight noop handler factory to avoid runtime errors during load-order races.
function makeNoopHandler(containerId) {
    return {
        __isAgentCommNoop: true,
        containerId: containerId || 'communicationsStream',
        taskStartTime: Date.now(),
        initialize() { this.taskStartTime = Date.now(); },
        addInteraction() { },
        clearDisplay() { },
        getInteractions() { return []; },
        addCompletionMessage() { },
        addTokenSummary() { },
        expandInteraction() { },
        clearInteractions() { },
        clearAllCommunications() { },
        reset() { },
    };
}

function createAgentCommHandler(containerId, opts = {}) {
    const key = containerId || 'communicationsStream';
    // Ensure registry exists (defensive against load-order races)
    window.agentCommHandlers = window.agentCommHandlers || {};
    // Merge with global defaults so pages can set a site-wide default layout
    const mergedOpts = Object.assign({}, window.agentCommDefaultOptions || {}, opts || {});

    // Heuristic: treat any container whose id contains "chat" as a chat-style page.
    // For chat-style UI we prefer a single-column chat view and disable aggressive autoExpand
    // to reduce flicker during rapid message updates while testing.
    try {
        const lowerKey = String(key || '').toLowerCase();
        if (lowerKey.includes('chat')) {
            mergedOpts.showFlow = false;
            mergedOpts.autoExpand = false;
            console.info('AgentComm: configured chat-style handler for', key);
        }
    } catch (e) {
        // ignore
    }

    // If a handler already exists and is not a noop placeholder, return it immediately
    if (window.agentCommHandlers[key] && !window.agentCommHandlers[key].__isAgentCommNoop) {
        return window.agentCommHandlers[key];
    }

    if (!window.agentCommHandlers[key]) {
        // If the class isn't available yet, return a safe no-op handler placeholder
        if (typeof window.AgentCommunicationHandler !== 'function') {
            console.warn('AgentCommunicationHandler not ready; returning noop handler for', key);
            const noop = makeNoopHandler(key);
            window.agentCommHandlers[key] = noop;
            return noop;
        }

        try {
            const HandlerClass = window.AgentCommunicationHandler;
            const handler = new HandlerClass(Object.assign({}, mergedOpts, { containerId: key }));
            window.agentCommHandlers[key] = handler;
            // Log handler creation for debugging and load-order verification
            // If there were pending communications queued while a noop placeholder was active,
            // replay them now into the freshly-created handler (only for the default communicationsStream key).
            try {
                if (window._pendingAgentComms && window._pendingAgentComms.length > 0 && key === 'communicationsStream') {
                    if (typeof window.AgentComm !== 'undefined' && typeof window.AgentComm.display === 'function') {
                        window.AgentComm.display(window._pendingAgentComms);
                    } else if (typeof displayAgentCommunications === 'function') {
                        displayAgentCommunications(window._pendingAgentComms);
                    }
                    window._pendingAgentComms = [];
                }
            } catch (replayErr) {
                console.warn('AgentComm: failed to replay pending communications', replayErr);
            }
        } catch (err) {
            console.error('Failed to create AgentCommunicationHandler for', key, err);
            const fallback = makeNoopHandler(key);
            window.agentCommHandlers[key] = fallback;
        }
    }

    return window.agentCommHandlers[key];
}

// Default global handler for legacy templates
const agentCommHandler = createAgentCommHandler('communicationsStream');
window.agentCommHandler = agentCommHandler;
window.createAgentCommHandler = createAgentCommHandler;
// Replay any pending communications that were queued while a noop placeholder existed
try {
    if (window._pendingAgentComms && window._pendingAgentComms.length > 0) {
        if (typeof window.AgentComm !== 'undefined' && typeof window.AgentComm.display === 'function') {
            window.AgentComm.display(window._pendingAgentComms);
        } else if (typeof displayAgentCommunications === 'function') {
            displayAgentCommunications(window._pendingAgentComms);
        }
        window._pendingAgentComms = [];
    }
} catch (replayErr) {
    console.warn('AgentComm: error replaying pending communications on global handler init', replayErr);
}

// Helper function for interaction toggling
function toggleInteraction(interactionId) {
    // Try to expand interaction on all registered handlers (works for multi-container pages)
    Object.values(window.agentCommHandlers || {}).forEach(h => {
        try {
            if (typeof h.expandInteraction === 'function') {
                h.expandInteraction(interactionId);
            }
        } catch (e) {
            // ignore
        }
    });
}

// Expose helper function globally
window.toggleInteraction = toggleInteraction;

// Enhanced display function using the new handler
function displayAgentCommunications(communications, options = {}) {
    // options: { containerId, showFlow }
    const containerId = options.containerId || 'communicationsStream';
    const showFlow = typeof options.showFlow === 'boolean' ? options.showFlow : true;

    console.log('displayAgentCommunications called with', communications.length, 'communications:', communications);

    // Get or create handler for the target container
    const handler = createAgentCommHandler(containerId, { showFlow: showFlow });
    handler.initialize();

    // Process communications using the new pattern
    if (!communications || communications.length === 0) {
        console.log('🚨 No communications provided, clearing display');
        handler.clearDisplay();
        return;
    }

    console.log('🔍 Starting to filter communications...');
    // Filter and process communications
    const filteredCommunications = communications.filter(comm => {
        const agentName = comm.agent_name || comm.agentName || comm.agent || comm.name || '';
        const action = comm.action || '';

        console.log(`🔍 Filtering: Agent="${agentName}", Action="${action}"`);

        // Keep all actual agent communications - only filter out truly internal system messages
        if (agentName.toLowerCase().includes('orchestrator')) {
            // Keep orchestrator messages that show actual work being done
            const isInternalSystemMessage = action.includes('_internal_init') || action.includes('_bootstrap') || action.includes('_startup');
            const shouldKeep = !isInternalSystemMessage;
            console.log(`🔍 Orchestrator message: isInternal=${isInternalSystemMessage}, keeping=${shouldKeep}`);
            return shouldKeep;
        }

        // Keep all non-orchestrator agent communications (these are the actual agents doing work)
        console.log(`🔍 Non-orchestrator message: keeping=true`);
        return true;
    });

    console.log('🔍 After filtering:', filteredCommunications.length, 'communications remaining:', filteredCommunications);

    // If no communications remain after filtering, show that
    if (filteredCommunications.length === 0) {
        console.log('🚨 No communications remain after filtering, clearing display');
        handler.clearDisplay();
        return;
    }

    console.log('🎯 Adding header summary...');
    // Add header summary
    handler.addInteraction(
        '📋 System',
        `Agent Framework Task Results (${filteredCommunications.length} entries)`,
        'summary'
    );

    console.log('🎯 Starting to process each communication...');
    console.log('🎯 About to enter forEach loop with', filteredCommunications.length, 'communications');
    
    // Process each communication
    filteredCommunications.forEach((comm, index) => {
        try {
            console.log(`🎯 LOOP ITERATION ${index + 1}: Starting processing communication:`, comm);
            console.log(`🎯 LOOP ITERATION ${index + 1}: Communication structure:`, {
                agent_name: comm.agent_name,
                action: comm.action,
                timestamp: comm.timestamp,
                hasInput: !!comm.input,
                hasOutput: !!comm.output
            });
            
            // Normalize and enrich the communication
            normalizeCommPayload(comm);

            const agentName = comm.agent_name || comm.agentName || comm.agent || comm.name || `Agent ${index + 1}`;
            console.log(`🎯 Agent: ${agentName}, Action: ${comm.action}`);

            // Determine status using normalized fields
            let actualStatus = 'general';
            const hasOutput = hasContent(comm._output);
            if (hasOutput && !comm.error) {
                actualStatus = 'completed';
            } else if (comm.error) {
                actualStatus = 'failed';
            } else if (comm.action || hasContent(comm._input) || hasContent(comm._output)) {
                actualStatus = 'in_progress';
            }

            // Build content using normalized _input and _output
            let content = '';
            const inputData = comm._input || {};
            const outputData = comm._output || {};

            // Special-case EOL responses when action suggests an EOL lookup
            // const actionLower = (comm.action || '').toString().toLowerCase();
            // if ((comm.action === 'get_eol_data' || actionLower.includes('eol') || actionLower.includes('endoflife')) && hasContent(outputData)) {
            //     const responseData = outputData;
            //     const eolInfo = responseData.eol_info || responseData;

            //     content = `
            //         <div class="eol-response">
            //             <div class="response-details">
            //                 ${inputData?.software_name ? `<div><strong>Software:</strong> ${inputData.software_name}</div>` : ''}
            //                 ${inputData?.version ? `<div><strong>Version:</strong> ${inputData.version}</div>` : ''}
            //                 ${eolInfo && eolInfo.eol ? `<div><strong>EOL Date:</strong> <span class="eol-date">${eolInfo.eol}</span></div>` : ''}
            //                 ${eolInfo && eolInfo.support ? `<div><strong>Support End:</strong> <span class="support-date">${eolInfo.support}</span></div>` : ''}
            //                 ${eolInfo && eolInfo.latest ? `<div><strong>Latest Version:</strong> ${eolInfo.latest}</div>` : ''}
            //                 <div><strong>Status:</strong> <span class="status-${actualStatus}">${formatStatus(actualStatus)}</span></div>
            //             </div>
            //         </div>
            //     `;
            // } else {
                // Generic communication display for non-EOL actions
                const inputHasContent = hasContent(inputData);
                const outputHasContent = hasContent(outputData);
                
                // Debug logging for completed status
                // if (actualStatus === 'completed') {
                //     console.log(`[DEBUG] Completed interaction for ${agentName}:`);
                //     console.log(`[DEBUG] - Output data:`, outputData);
                //     console.log(`[DEBUG] - Output has content: ${outputHasContent}`);
                //     console.log(`[DEBUG] - Output is null/undefined: ${outputData === null || outputData === undefined}`);
                //     console.log(`[DEBUG] - Should show output: ${outputHasContent || (actualStatus === 'completed' && (outputData !== null && outputData !== undefined))}`);
                // }
                
                // For completed status, always show output even if hasContent check fails
                const shouldShowOutput = outputHasContent || (actualStatus === 'completed' && (outputData !== null && outputData !== undefined));

                content = `
                    <div class="generic-response">
                        ${comm.action ? `<div class="comm-action"><strong>Action:</strong> ${formatActionDescription(comm.action)}</div>` : ''}
                        ${inputHasContent ?
                        `<div class="input-section">
                                <strong>Input:</strong>
                                <pre class="json-display">${typeof inputData === 'string' ? inputData : JSON.stringify(inputData, null, 2)}</pre>
                            </div>` : ''}
                        ${shouldShowOutput ?
                        `<div class="output-section">
                                <strong>Output:</strong>
                                <pre class="json-display">${typeof outputData === 'string' ? outputData : JSON.stringify(outputData, null, 2)}</pre>
                            </div>` : ''}
                        <div><strong>Status:</strong> <span class="status-${actualStatus}">${formatStatus(actualStatus)}</span></div>
                    </div>
                `;
            // }

            // Add the interaction, include structured input/output in metadata so the handler can render JSON
            console.log(`🎯 LOOP ITERATION ${index + 1}: About to call addInteraction for agent: ${agentName}`);
            console.log(`🎯 LOOP ITERATION ${index + 1}: Content length: ${content.length}, Status: ${actualStatus}`);
            
            handler.addInteraction(agentName, content, 'text', {
                action: comm.action,
                status: actualStatus,
                timestamp: comm.timestamp,
                input: inputData,
                output: outputData
            });
            
            console.log(`🎯 LOOP ITERATION ${index + 1}: addInteraction completed for agent: ${agentName}`);

        } catch (error) {
            console.error(`🚨 LOOP ITERATION ${index + 1}: Error processing communication:`, error);
            console.error(`🚨 LOOP ITERATION ${index + 1}: Error details:`, error.message, error.stack);
            console.error(`🚨 LOOP ITERATION ${index + 1}: Failed communication:`, comm);
            handler.addInteraction(
                '🚨 Error Handler',
                `Error processing communication: ${error.message}`,
                'error'
            );
        }
    });
    
    console.log('🎯 forEach loop completed. Processing', filteredCommunications.length, 'communications finished');
    console.log('🎯 Current handler interaction count:', handler.interactions.length);

    // Add completion message if task is done
    if (filteredCommunications.length > 0) {
        const elapsedTime = Date.now() - handler.taskStartTime;
        handler.addCompletionMessage(elapsedTime);
    }
}

// Helper Functions
function formatStatus(status) {
    if (!status) return 'Unknown';

    // Handle specific statuses
    const stat = status.toLowerCase();
    if (stat.includes('in_progress') || stat.includes('running') || stat.includes('active')) return 'Request';
    if (stat.includes('completed') || stat.includes('success') || stat.includes('done')) return 'Completed';
    if (stat.includes('failed') || stat.includes('error')) return 'Failed';
    if (stat.includes('starting') || stat.includes('initializing')) return 'Starting';
    if (stat.includes('queued') || stat.includes('pending')) return 'Queued';

    // Default formatting
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatActionDescription(action) {
    if (!action) return 'No description available';

    // Action mappings for better descriptions
    const actionMappings = {
        'get_eol_data': 'EOL Data Lookup',
        'search': 'Search Operation',
        'message_sent': 'Message Transmission',
        'tool_call': 'Tool Execution',
        'function_call': 'Function Call',
        'api_request': 'API Request',
        'data_processing': 'Data Processing',
        'cache_check': 'Cache Verification',
        'validate_input': 'Input Validation',
        'format_output': 'Output Formatting'
    };

    // Check for exact match first
    if (actionMappings[action]) {
        return actionMappings[action];
    }

    // Basic formatting and markdown support
    let formatted = action
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase())
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>');

    return formatted;
}

// Expose helper functions globally
window.formatStatus = formatStatus;
window.formatActionDescription = formatActionDescription;

// Robust helpers for normalizing communication payloads
function parseMaybeJson(value) {
    if (value === undefined || value === null) return value;
    if (typeof value === 'object') return value;
    if (typeof value !== 'string') return value;
    const trimmed = value.trim();
    if (trimmed === '') return null;
    // Try JSON parse for objects/arrays
    try {
        return JSON.parse(trimmed);
    } catch (e) {
        // Not JSON — return original string
        return trimmed;
    }
}

function hasContent(v) {
    if (v === undefined || v === null) return false;
    if (typeof v === 'string') return v.trim().length > 0;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === 'object') return Object.keys(v).length > 0;
    // numbers, booleans, etc. considered content
    return true;
}

function normalizeCommPayload(comm) {
    // Normalize agent name aliases
    if (!comm.agent_name) comm.agent_name = comm.agent || comm.agentName || comm.name || '';
    // Normalize action aliases
    if (!comm.action) comm.action = comm.type || comm.task || '';

    // Attempt to pull input-like fields from many possible locations
    let inputCandidate = comm.input || comm.inputs || comm.request || null;
    if (!inputCandidate && comm.data && typeof comm.data === 'object' && (comm.data.input || comm.data.inputs)) {
        inputCandidate = comm.data.input || comm.data.inputs;
    }
    if (!inputCandidate && comm.payload && (comm.payload.input || comm.payload.inputs)) {
        inputCandidate = comm.payload.input || comm.payload.inputs;
    }

    // Attempt to pull output-like fields
    let outputCandidate = comm.output || comm.result || comm.payload || null;
    if (!outputCandidate && comm.data && (comm.data.output || comm.data.result)) {
        outputCandidate = comm.data.output || comm.data.result;
    }

    // If both input/output are still null but message contains JSON, try parse it
    if (!inputCandidate && !outputCandidate && comm.message && typeof comm.message === 'string') {
        const m = comm.message.trim();
        // try parse full message as JSON
        const maybe = parseMaybeJson(m);
        if (maybe && typeof maybe === 'object') {
            // pick common keys
            if (maybe.input || maybe.inputs) inputCandidate = maybe.input || maybe.inputs;
            if (maybe.output || maybe.result || maybe.data) outputCandidate = maybe.output || maybe.result || maybe.data;
        }
    }

    // If input/output are strings that contain JSON, parse them
    comm._input = parseMaybeJson(inputCandidate === undefined ? null : inputCandidate);
    comm._output = parseMaybeJson(outputCandidate === undefined ? null : outputCandidate);

    // Fallback: if data is an object and looks like payload, use it as output
    if (!hasContent(comm._output) && comm.data && typeof comm.data === 'object') {
        // exclude cases where data looks like metadata only (small keys)
        comm._output = comm.data;
    }

    // Ensure action is a string
    if (comm.action && typeof comm.action !== 'string') comm.action = String(comm.action);

    return comm;
}

// Tidy namespace to reduce global surface area while keeping backwards compatibility
window.AgentComm = window.AgentComm || {
    createHandler: createAgentCommHandler,
    display: displayAgentCommunications,
    toggle: toggleInteraction,
    handlers: window.agentCommHandlers,
    defaults: window.agentCommDefaultOptions,
    formatStatus: formatStatus,
    formatActionDescription: formatActionDescription,
    
    // Clear interactions on a specific handler or the default handler
    clearInteractions: function(containerId = 'communicationsStream') {
        try {
            const handler = window.agentCommHandlers && window.agentCommHandlers[containerId];
            if (handler && typeof handler.clearInteractions === 'function') {
                handler.clearInteractions();
                // Cleared interactions for container
                return true;
            } else {
                console.warn(`No handler found for ${containerId} or clearInteractions method not available`);
                return false;
            }
        } catch (error) {
            console.error('Error clearing interactions:', error);
            return false;
        }
    },
    
    // Clear all communications and reset to fresh state
    clearAllCommunications: function(containerId = 'communicationsStream') {
        try {
            const handler = window.agentCommHandlers && window.agentCommHandlers[containerId];
            if (handler && typeof handler.clearAllCommunications === 'function') {
                handler.clearAllCommunications();
                // Cleared all communications for container
                return true;
            } else if (handler && typeof handler.clearInteractions === 'function') {
                // Fallback to clearInteractions if clearAllCommunications is not available
                handler.clearInteractions();
                // Cleared interactions (fallback) for container
                return true;
            } else {
                console.warn(`No handler found for ${containerId}`);
                return false;
            }
        } catch (error) {
            console.error('Error clearing all communications:', error);
            return false;
        }
    },
    
    // Clear all handlers (for complete reset)
    clearAll: function() {
        try {
            let cleared = 0;
            Object.keys(window.agentCommHandlers || {}).forEach(containerId => {
                if (this.clearAllCommunications(containerId)) {
                    cleared++;
                }
            });
            // Communication handlers cleared
            return cleared > 0;
        } catch (error) {
            console.error('Error clearing all handlers:', error);
            return false;
        }
    },
    
    // Get formatted agent display name with icon
    getAgentDisplay: function(agentName) {
        try {
            // Create a temporary handler instance to access the formatting method
            const tempHandler = new window.AgentCommunicationHandler();
            return tempHandler.formatAgentDisplay(agentName);
        } catch (error) {
            console.error('Error getting agent display:', error);
            return `🤖 ${agentName}`;
        }
    },
    
    // Get just the icon for an agent
    getAgentIcon: function(agentName) {
        try {
            const tempHandler = new window.AgentCommunicationHandler();
            return tempHandler.getAgentIcon(agentName);
        } catch (error) {
            console.error('Error getting agent icon:', error);
            return '🤖';
        }
    },
    
    // Get clean agent name (without icon and suffixes)
    getCleanAgentName: function(agentName) {
        try {
            const tempHandler = new window.AgentCommunicationHandler();
            return tempHandler.cleanAgentName(agentName);
        } catch (error) {
            console.error('Error getting clean agent name:', error);
            return String(agentName || '').replace(/🤖|Agent/g, '').trim();
        }
    }
};
