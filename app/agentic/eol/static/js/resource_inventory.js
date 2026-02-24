/**
 * Resource Inventory Browser - Frontend Logic
 *
 * Consumes /api/resource-inventory/* endpoints to render
 * a searchable, filterable, paginated resource grid with
 * details panel and export functionality.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let dataTable = null;
let currentResources = [];
let currentPage = { offset: 0, limit: 50, total: 0 };

const API_BASE = '/api/resource-inventory';

// Resource type display names and icons
const RESOURCE_TYPE_META = {
    'microsoft.compute/virtualmachines':           { label: 'Virtual Machine',    icon: 'bi-pc-display', color: '#0078D4' },
    'microsoft.network/virtualnetworks':           { label: 'Virtual Network',    icon: 'bi-diagram-3',  color: '#00A36C' },
    'microsoft.storage/storageaccounts':           { label: 'Storage Account',    icon: 'bi-hdd-stack',  color: '#E97132' },
    'microsoft.web/sites':                         { label: 'App Service',        icon: 'bi-globe',      color: '#512BD4' },
    'microsoft.containerservice/managedclusters':  { label: 'AKS Cluster',        icon: 'bi-box-seam',   color: '#326CE5' },
    'microsoft.app/containerapps':                 { label: 'Container App',      icon: 'bi-boxes',      color: '#0D9748' },
    'microsoft.sql/servers':                       { label: 'SQL Server',         icon: 'bi-database',   color: '#CC2927' },
    'microsoft.keyvault/vaults':                   { label: 'Key Vault',          icon: 'bi-key',        color: '#FFB900' },
    'microsoft.network/networksecuritygroups':     { label: 'NSG',               icon: 'bi-shield-lock', color: '#005F9E' },
    'microsoft.network/loadbalancers':             { label: 'Load Balancer',      icon: 'bi-distribute-vertical', color: '#0078D4' },
    'microsoft.documentdb/databaseaccounts':       { label: 'Cosmos DB',          icon: 'bi-database-gear', color: '#0078D4' },
};

function getTypeMeta(resourceType) {
    const key = (resourceType || '').toLowerCase();
    return RESOURCE_TYPE_META[key] || { label: resourceType, icon: 'bi-cloud', color: '#6c757d' };
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    initDataTable();
    loadSubscriptions();
    loadStats();
    // Auto-load data for default selected resource type
    setTimeout(() => searchResources(), 500);
});

function initDataTable() {
    dataTable = $('#resource-table').DataTable({
        paging: false,          // We handle pagination via API
        searching: true,        // Client-side quick search
        info: false,
        ordering: true,
        order: [[0, 'asc']],
        language: {
            emptyTable: 'Select a resource type and click Search to load resources.',
            zeroRecords: 'No matching resources found.',
        },
        columnDefs: [
            { targets: -1, orderable: false, searchable: false },   // actions col
            { targets: 4, orderable: false },                       // tags col
        ],
    });
}

// ---------------------------------------------------------------------------
// API Helpers
// ---------------------------------------------------------------------------
async function apiFetch(path, options = {}) {
    try {
        const resp = await fetch(`${API_BASE}${path}`, options);
        return await resp.json();
    } catch (err) {
        console.error(`API error ${path}:`, err);
        return { success: false, error: err.message };
    }
}

// ---------------------------------------------------------------------------
// Subscriptions
// ---------------------------------------------------------------------------
async function loadSubscriptions() {
    const result = await apiFetch('/subscriptions');
    if (!result.success || !result.data) return;

    const sel = document.getElementById('filter-subscription');
    const subs = result.data.subscriptions || [];
    subs.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.subscription_id;
        opt.textContent = `${s.display_name} (${s.subscription_id.substring(0, 8)}...)`;
        sel.appendChild(opt);
    });
}

// ---------------------------------------------------------------------------
// Statistics & Health
// ---------------------------------------------------------------------------
async function loadStats() {
    const result = await apiFetch('/stats');
    if (!result.success || !result.data) return;

    const cache = result.data.cache || {};
    const hitRate = cache.hit_rate_percent || 0;
    const l1 = cache.l1_entries || 0;
    const l2Ready = cache.l2_ready ? 'Connected' : 'Offline';

    document.getElementById('badge-cache-hit').textContent = `${hitRate}% hit rate`;
    document.getElementById('badge-l2').textContent = `L2: ${l2Ready}`;

    document.getElementById('stat-hit-rate').textContent = `${hitRate}%`;
    document.getElementById('stat-l2').textContent = l2Ready;
    document.getElementById('stat-total').textContent = l1;

    setStatus('Ready. Select a resource type and search.', 'info');
}

// ---------------------------------------------------------------------------
// Search / Query
// ---------------------------------------------------------------------------
async function searchResources() {
    const sub = document.getElementById('filter-subscription').value;
    const rtype = document.getElementById('filter-resource-type').value;
    const loc = document.getElementById('filter-location').value.trim();
    const rg = document.getElementById('filter-resource-group').value.trim();

    if (!rtype) {
        setStatus('Please select a resource type.', 'warning');
        return;
    }

    setStatus('Searching...', 'info');
    document.getElementById('btn-search').disabled = true;

    const params = new URLSearchParams();
    if (sub) params.set('subscription_id', sub);
    params.set('resource_type', rtype);
    if (loc) params.set('location', loc);
    if (rg) params.set('resource_group', rg);
    params.set('offset', '0');
    params.set('limit', '500');

    const result = await apiFetch(`/resources?${params.toString()}`);
    document.getElementById('btn-search').disabled = false;

    if (!result.success) {
        setStatus(`Error: ${result.error}`, 'danger');
        return;
    }

    const data = result.data || {};
    currentResources = data.items || [];
    currentPage.total = data.total || 0;

    renderTable(currentResources);
    document.getElementById('badge-total').textContent = `${currentPage.total} resources`;
    document.getElementById('stat-total').textContent = currentPage.total;
    document.getElementById('stat-types').textContent = new Set(currentResources.map(r => r.resource_type)).size;

    const dur = result.duration_ms ? ` (${result.duration_ms}ms)` : '';
    setStatus(`Found ${currentPage.total} resources${dur}`, 'success');
}

function quickSearch(query) {
    if (dataTable) {
        dataTable.search(query).draw();
    }
}

// ---------------------------------------------------------------------------
// Render Table
// ---------------------------------------------------------------------------
function renderTable(resources) {
    dataTable.clear();

    resources.forEach((r, idx) => {
        const meta = getTypeMeta(r.resource_type);
        const name = r.resource_name || r.name || '--';
        const rg = r.resource_group || r.resourceGroup || '--';
        const loc = r.location || '--';
        const tags = r.tags ? Object.entries(r.tags).slice(0, 3).map(
            ([k, v]) => `<span class="badge bg-light text-dark border me-1">${k}=${v}</span>`
        ).join('') : '<span class="text-muted">--</span>';
        const discovered = r.discovered_at ? new Date(r.discovered_at).toLocaleString() : '--';

        const typeCell = `<span class="resource-type-badge" style="--type-color:${meta.color}">` +
                          `<i class="bi ${meta.icon} me-1"></i>${meta.label}</span>`;

        const actions = `<button class="btn btn-sm btn-outline-primary py-0 px-1" onclick="showDetails(${idx})" title="Details">` +
                        `<i class="bi bi-chevron-right"></i></button>`;

        dataTable.row.add([name, typeCell, rg, loc, tags, discovered, actions]);
    });

    dataTable.draw();
}

// ---------------------------------------------------------------------------
// Details Panel
// ---------------------------------------------------------------------------
function showDetails(idx) {
    const r = currentResources[idx];
    if (!r) return;

    const meta = getTypeMeta(r.resource_type);
    document.getElementById('details-title').innerHTML =
        `<i class="bi ${meta.icon} me-2" style="color:${meta.color}"></i>${r.resource_name || r.name}`;

    const props = r.selected_properties || {};
    const propsHtml = Object.keys(props).length > 0
        ? Object.entries(props).map(([k, v]) =>
            `<tr><td class="text-muted">${k}</td><td>${v ?? '--'}</td></tr>`
          ).join('')
        : '<tr><td colspan="2" class="text-muted">No enriched properties</td></tr>';

    const tagsHtml = r.tags && Object.keys(r.tags).length > 0
        ? Object.entries(r.tags).map(([k, v]) =>
            `<tr><td class="text-muted">${k}</td><td>${v}</td></tr>`
          ).join('')
        : '<tr><td colspan="2" class="text-muted">No tags</td></tr>';

    document.getElementById('details-body').innerHTML = `
        <div class="mb-3">
            <h6 class="border-bottom pb-1 text-muted">Identity</h6>
            <table class="table table-sm mb-0">
                <tr><td class="text-muted">Type</td><td>${meta.label}</td></tr>
                <tr><td class="text-muted">Resource Group</td><td>${r.resource_group || '--'}</td></tr>
                <tr><td class="text-muted">Location</td><td>${r.location || '--'}</td></tr>
                <tr><td class="text-muted">Subscription</td><td>${r.subscription_id || '--'}</td></tr>
                <tr><td class="text-muted">SKU</td><td>${r.sku ? JSON.stringify(r.sku) : '--'}</td></tr>
                <tr><td class="text-muted">Kind</td><td>${r.kind || '--'}</td></tr>
            </table>
        </div>
        <div class="mb-3">
            <h6 class="border-bottom pb-1 text-muted">Properties</h6>
            <table class="table table-sm mb-0">${propsHtml}</table>
        </div>
        <div class="mb-3">
            <h6 class="border-bottom pb-1 text-muted">Tags</h6>
            <table class="table table-sm mb-0">${tagsHtml}</table>
        </div>
        <div class="mb-3">
            <h6 class="border-bottom pb-1 text-muted">Metadata</h6>
            <table class="table table-sm mb-0">
                <tr><td class="text-muted">Discovered</td><td>${r.discovered_at || '--'}</td></tr>
                <tr><td class="text-muted">Last Seen</td><td>${r.last_seen || '--'}</td></tr>
                <tr><td class="text-muted">Resource ID</td><td class="text-break small">${r.resource_id || '--'}</td></tr>
            </table>
        </div>
        <div class="d-grid">
            <button class="btn btn-sm btn-outline-secondary" onclick="copyResourceJson(${idx})">
                <i class="bi bi-clipboard"></i> Copy JSON
            </button>
        </div>
    `;

    document.getElementById('details-panel').classList.add('open');
    document.getElementById('grid-container').classList.add('with-details');
}

function closeDetailsPanel() {
    document.getElementById('details-panel').classList.remove('open');
    document.getElementById('grid-container').classList.remove('with-details');
}

function copyResourceJson(idx) {
    const r = currentResources[idx];
    if (r) {
        navigator.clipboard.writeText(JSON.stringify(r, null, 2));
        setStatus('Resource JSON copied to clipboard.', 'success');
    }
}

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------
function triggerRefresh() {
    const modal = new bootstrap.Modal(document.getElementById('refreshModal'));
    modal.show();
}

async function startRefresh() {
    const mode = document.getElementById('refresh-mode').value;
    const sub = document.getElementById('filter-subscription').value || undefined;

    document.getElementById('refresh-progress').classList.remove('d-none');
    document.getElementById('btn-start-refresh').disabled = true;
    document.getElementById('refresh-status').textContent = `Running ${mode} discovery...`;

    const result = await apiFetch('/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subscription_id: sub, mode }),
    });

    document.getElementById('btn-start-refresh').disabled = false;
    document.getElementById('refresh-progress').classList.add('d-none');

    if (result.success) {
        const d = result.data || {};
        document.getElementById('refresh-status').textContent =
            `Done! ${d.resources_discovered || 0} resources discovered.`;
        setStatus(`Refresh complete: ${d.resources_discovered || 0} resources`, 'success');
        // Auto-reload current view
        const rtype = document.getElementById('filter-resource-type').value;
        if (rtype) searchResources();
        loadStats();
    } else {
        document.getElementById('refresh-status').textContent = `Error: ${result.error}`;
        setStatus(`Refresh failed: ${result.error}`, 'danger');
    }

    setTimeout(() => {
        bootstrap.Modal.getInstance(document.getElementById('refreshModal'))?.hide();
    }, 2000);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------
function exportData() {
    if (currentResources.length === 0) {
        setStatus('No data to export. Search first.', 'warning');
        return;
    }

    // CSV export
    const headers = ['Name', 'Type', 'Resource Group', 'Location', 'Subscription', 'Tags', 'Discovered'];
    const rows = currentResources.map(r => [
        r.resource_name || r.name || '',
        r.resource_type || '',
        r.resource_group || '',
        r.location || '',
        r.subscription_id || '',
        r.tags ? Object.entries(r.tags).map(([k, v]) => `${k}=${v}`).join('; ') : '',
        r.discovered_at || '',
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `resource_inventory_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    setStatus(`Exported ${currentResources.length} resources to CSV.`, 'success');
}

// ---------------------------------------------------------------------------
// Status Helpers
// ---------------------------------------------------------------------------
function setStatus(message, type) {
    const bar = document.getElementById('status-bar');
    bar.className = `alert alert-${type} d-flex align-items-center py-2`;

    const icons = { info: 'bi-info-circle', success: 'bi-check-circle', warning: 'bi-exclamation-triangle', danger: 'bi-x-circle' };
    document.getElementById('status-message').innerHTML =
        `<i class="bi ${icons[type] || icons.info} me-2"></i>${message}`;
}
