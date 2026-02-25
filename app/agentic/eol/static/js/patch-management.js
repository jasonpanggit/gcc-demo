/**
 * Patch Management UI Client
 * Handles patch assessment, compliance, and installation via MCP orchestrator
 */

class PatchManagementUI {
    constructor() {
        this.orchestratorUrl = '/api/mcp-orchestrator/execute';
        this.streamUrl = '/api/mcp-orchestrator/execute-stream';
        this.eventSource = null;
        this.currentSubscription = null;
        this.vmList = [];
    }

    /**
     * Initialize UI on page load
     */
    init() {
        this.loadSubscriptions();
        this.setupEventListeners();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const assessBtn = document.getElementById('btn-assess-patches');
        if (assessBtn) {
            assessBtn.addEventListener('click', () => this.assessPatches());
        }

        const installBtn = document.getElementById('btn-install-selected');
        if (installBtn) {
            installBtn.addEventListener('click', () => this.installSelected());
        }

        const refreshBtn = document.getElementById('btn-refresh-vms');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshVMs());
        }
    }

    /**
     * Load available subscriptions
     */
    async loadSubscriptions() {
        try {
            const response = await fetch('/api/mcp-orchestrator/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: 'List my Azure subscriptions',
                })
            });

            const result = await response.json();
            if (result.success && result.response) {
                this.renderSubscriptions(result.response);
            }
        } catch (error) {
            console.error('Error loading subscriptions:', error);
            this.showError('Failed to load subscriptions');
        }
    }

    /**
     * Render subscriptions dropdown
     */
    renderSubscriptions(responseText) {
        // Parse subscription info from response
        // This is a simplified version - could be enhanced with structured data
        const select = document.getElementById('subscription-select');
        if (select) {
            // For now, use config default
            select.innerHTML = '<option value="default">Default Subscription</option>';
            this.currentSubscription = 'default';
        }
    }

    /**
     * Assess patches across all VMs
     */
    async assessPatches() {
        const statusEl = document.getElementById('patch-status');
        const agentCommsEl = document.getElementById('agent-comms-content');

        if (statusEl) {
            statusEl.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Assessing patches...';
        }

        const query = this.currentSubscription
            ? `Check patch compliance for all VMs in subscription ${this.currentSubscription}. Show summary with compliance percentage and list VMs needing critical patches.`
            : 'Check patch compliance for all VMs. Show summary with compliance percentage.';

        this.startStreamingRequest(query, (finalResult) => {
            this.renderAssessmentResults(finalResult);
        });
    }

    /**
     * Refresh VM list
     */
    async refreshVMs() {
        const query = 'List all Azure VMs and Arc-enabled servers with their current patch status';
        this.startStreamingRequest(query, (result) => {
            this.renderVMList(result);
        });
    }

    /**
     * Install selected patches
     */
    async installSelected() {
        const selectedVMs = this.getSelectedVMs();
        if (selectedVMs.length === 0) {
            this.showError('No VMs selected');
            return;
        }

        const vmNames = selectedVMs.map(vm => vm.name).join(', ');
        const query = `Install Critical and Security patches on these VMs: ${vmNames}. Show installation progress and results.`;

        if (!confirm(`Install patches on ${selectedVMs.length} VM(s)?\n\nThis will install Critical and Security patches and may cause reboots.`)) {
            return;
        }

        this.startStreamingRequest(query, (result) => {
            this.renderInstallResults(result);
        });
    }

    /**
     * Get selected VMs from UI
     */
    getSelectedVMs() {
        const checkboxes = document.querySelectorAll('.vm-checkbox:checked');
        return Array.from(checkboxes).map(cb => ({
            name: cb.dataset.vmName,
            resourceGroup: cb.dataset.resourceGroup
        }));
    }

    /**
     * Start SSE streaming request to orchestrator
     */
    startStreamingRequest(query, onComplete) {
        // Close existing connection
        if (this.eventSource) {
            this.eventSource.close();
        }

        const agentCommsEl = document.getElementById('agent-comms-content');
        if (agentCommsEl) {
            agentCommsEl.innerHTML = '';
        }

        // Build SSE URL with query parameter
        const url = new URL(this.streamUrl, window.location.origin);
        url.searchParams.append('query', query);
        if (this.currentSubscription) {
            url.searchParams.append('subscription_id', this.currentSubscription);
        }

        this.eventSource = new EventSource(url.toString());

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamEvent(data, onComplete);
            } catch (error) {
                console.error('Error parsing SSE event:', error);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);
            this.eventSource.close();
            this.eventSource = null;
            this.showError('Connection to server lost');
        };
    }

    /**
     * Handle individual SSE events
     */
    handleStreamEvent(data, onComplete) {
        const agentCommsEl = document.getElementById('agent-comms-content');

        switch (data.event) {
            case 'status':
                this.updateStatus(data.message);
                break;

            case 'tool_progress':
                if (agentCommsEl) {
                    const progressHtml = `
                        <div class="agent-msg tool-call">
                            <i class="fas fa-tools me-2"></i>
                            <strong>${data.tool}</strong>: ${data.status}
                        </div>`;
                    agentCommsEl.innerHTML += progressHtml;
                    agentCommsEl.scrollTop = agentCommsEl.scrollHeight;
                }
                break;

            case 'agent_response':
                if (agentCommsEl) {
                    const responseHtml = `
                        <div class="agent-msg response">
                            ${this.formatMarkdown(data.content)}
                        </div>`;
                    agentCommsEl.innerHTML += responseHtml;
                    agentCommsEl.scrollTop = agentCommsEl.scrollHeight;
                }
                break;

            case 'result':
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                if (onComplete) {
                    onComplete(data);
                }
                break;

            case 'done':
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                break;

            case 'error':
                this.showError(data.message || 'An error occurred');
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                break;
        }
    }

    /**
     * Update status message
     */
    updateStatus(message) {
        const statusEl = document.getElementById('patch-status');
        if (statusEl) {
            statusEl.innerHTML = `<i class="fas fa-info-circle me-2"></i>${this.escapeHtml(message)}`;
        }
    }

    /**
     * Render patch assessment results
     */
    renderAssessmentResults(data) {
        const summaryEl = document.getElementById('patch-summary');
        const statusEl = document.getElementById('patch-status');

        if (statusEl) {
            statusEl.innerHTML = '<i class="fas fa-check-circle me-2 text-success"></i>Assessment complete';
        }

        // Parse response text to extract structured data
        // This is simplified - in production would use structured response from agent
        const response = data.response || '';

        if (summaryEl) {
            summaryEl.innerHTML = `
                <div class="alert alert-info">
                    <h6><i class="fas fa-clipboard-check me-2"></i>Patch Assessment Results</h6>
                    <div class="mt-2">${this.formatMarkdown(response)}</div>
                </div>`;
        }
    }

    /**
     * Render VM list
     */
    renderVMList(data) {
        const tableBody = document.getElementById('vm-table-body');
        if (!tableBody) return;

        // Parse VM data from response
        // Simplified version - would need structured data from agent
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-muted py-4">
                    ${this.formatMarkdown(data.response || 'No VMs found')}
                </td>
            </tr>`;
    }

    /**
     * Render installation results
     */
    renderInstallResults(data) {
        const statusEl = document.getElementById('patch-status');
        const resultsEl = document.getElementById('install-results');

        if (statusEl) {
            statusEl.innerHTML = '<i class="fas fa-check-circle me-2 text-success"></i>Installation complete';
        }

        if (resultsEl) {
            resultsEl.innerHTML = `
                <div class="alert alert-success mt-3">
                    <h6><i class="fas fa-download me-2"></i>Installation Results</h6>
                    <div class="mt-2">${this.formatMarkdown(data.response || '')}</div>
                </div>`;
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        const statusEl = document.getElementById('patch-status');
        if (statusEl) {
            statusEl.innerHTML = `<i class="fas fa-exclamation-triangle me-2 text-danger"></i>${this.escapeHtml(message)}`;
        }
    }

    /**
     * Format markdown-like text to HTML
     */
    formatMarkdown(text) {
        if (!text) return '';

        let html = this.escapeHtml(text);

        // Convert **bold** to <strong>
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // Convert `code` to <code>
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');

        // Convert line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on page load
let patchUI;
document.addEventListener('DOMContentLoaded', () => {
    patchUI = new PatchManagementUI();
    patchUI.init();
});
