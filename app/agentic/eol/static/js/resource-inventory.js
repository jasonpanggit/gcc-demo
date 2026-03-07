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
let currentPage = { page: 1, offset: 0, limit: 50, total: 0, totalPages: 1, hasMore: false };
let activeFilters = { sub: '', rtype: '', loc: '', rg: '' };

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
            { targets: -2, orderable: false, searchable: false },   // CVE badge col
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
    activeFilters = {
        sub: document.getElementById('filter-subscription').value,
        rtype: document.getElementById('filter-resource-type').value,
        loc: document.getElementById('filter-location').value.trim(),
        rg: document.getElementById('filter-resource-group').value.trim(),
    };

    currentPage.page = 1;
    currentPage.offset = 0;
    await loadResourcesPage();
}

async function loadResourcesPage() {
    const { sub, rtype, loc, rg } = activeFilters;

    setStatus(rtype ? 'Searching selected resource type...' : 'Searching all cached resource types...', 'info');
    document.getElementById('btn-search').disabled = true;
    const pageSizeEl = document.getElementById('page-size-select');
    currentPage.limit = pageSizeEl ? parseInt(pageSizeEl.value, 10) || 50 : currentPage.limit;
    currentPage.offset = (currentPage.page - 1) * currentPage.limit;

    const params = new URLSearchParams();
    if (sub) params.set('subscription_id', sub);
    if (rtype) params.set('resource_type', rtype.toLowerCase());
    if (loc) params.set('location', loc);
    if (rg) params.set('resource_group', rg);
    params.set('offset', String(currentPage.offset));
    params.set('limit', String(currentPage.limit));

    const result = await apiFetch(`/resources?${params.toString()}`);
    document.getElementById('btn-search').disabled = false;

    if (!result.success) {
        setStatus(`Error: ${result.error}`, 'danger');
        return;
    }

    const data = result.data || {};
    currentResources = data.items || [];
    currentPage.total = data.total || 0;
    currentPage.offset = data.offset || 0;
    currentPage.limit = data.limit || currentPage.limit;
    currentPage.page = Math.floor(currentPage.offset / Math.max(1, currentPage.limit)) + 1;
    currentPage.totalPages = Math.max(1, Math.ceil(currentPage.total / Math.max(1, currentPage.limit)));
    currentPage.hasMore = !!data.has_more;

    renderTable(currentResources);
    updatePaginationControls();
    document.getElementById('badge-total').textContent = `${currentPage.total} resources`;
    document.getElementById('stat-total').textContent = currentPage.total;
    document.getElementById('stat-types').textContent = rtype ? '1' : '--';

    const dur = result.duration_ms ? ` (${result.duration_ms}ms)` : '';
    const start = currentPage.total === 0 ? 0 : currentPage.offset + 1;
    const end = Math.min(currentPage.offset + currentResources.length, currentPage.total);
    setStatus(`Found ${currentPage.total} resources${dur}. Showing ${start}-${end}.`, 'success');

    // Load CVE counts for VMs
    await onResourcesLoaded();
}

function updatePaginationControls() {
    const container = document.getElementById('pagination-container');
    if (!container) return;

    if (currentPage.total <= 0) {
        container.classList.add('d-none');
        return;
    }

    container.classList.remove('d-none');

    const info = document.getElementById('pagination-info');
    const start = currentPage.total === 0 ? 0 : currentPage.offset + 1;
    const end = Math.min(currentPage.offset + currentResources.length, currentPage.total);
    if (info) {
        info.textContent = `Showing ${start}-${end} of ${currentPage.total}`;
    }

    const controls = document.getElementById('pagination-controls');
    if (!controls) return;

    let html = '';
    html += `<li class="page-item ${currentPage.page <= 1 ? 'disabled' : ''}">`
         + `<a class="page-link" href="#" onclick="previousPage(); return false;" aria-label="Previous">&laquo;</a></li>`;

    const pages = generatePageNumbers(currentPage.page, currentPage.totalPages);
    pages.forEach((p) => {
        if (p.disabled) {
            html += `<li class="page-item disabled"><span class="page-link">${p.text}</span></li>`;
        } else {
            html += `<li class="page-item ${p.active ? 'active' : ''}">`
                 + `<a class="page-link" href="#" onclick="goToPage(${p.page}); return false;">${p.text}</a></li>`;
        }
    });

    html += `<li class="page-item ${currentPage.page >= currentPage.totalPages ? 'disabled' : ''}">`
         + `<a class="page-link" href="#" onclick="nextPage(); return false;" aria-label="Next">&raquo;</a></li>`;

    controls.innerHTML = html;
}

function generatePageNumbers(current, total) {
    const pages = [];
    const maxVisible = 5;
    const half = Math.floor(maxVisible / 2);
    let start = Math.max(1, current - half);
    let end = Math.min(total, start + maxVisible - 1);

    if ((end - start) < (maxVisible - 1)) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        pages.push({ page: 1, text: '1', active: false, disabled: false });
        if (start > 2) pages.push({ page: null, text: '...', active: false, disabled: true });
    }

    for (let p = start; p <= end; p += 1) {
        pages.push({ page: p, text: String(p), active: p === current, disabled: false });
    }

    if (end < total) {
        if (end < total - 1) pages.push({ page: null, text: '...', active: false, disabled: true });
        pages.push({ page: total, text: String(total), active: false, disabled: false });
    }

    return pages;
}

async function goToPage(page) {
    if (page < 1 || page > currentPage.totalPages || page === currentPage.page) {
        return;
    }
    currentPage.page = page;
    await loadResourcesPage();
}

async function previousPage() {
    await goToPage(currentPage.page - 1);
}

async function nextPage() {
    await goToPage(currentPage.page + 1);
}

async function changePageSize() {
    currentPage.page = 1;
    currentPage.offset = 0;
    await loadResourcesPage();
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

        // CVE badge (only for VMs)
        const isVM = (r.resource_type || '').toLowerCase() === 'microsoft.compute/virtualmachines';
        const cveBadge = isVM
            ? `<span class="badge bg-secondary" id="cve-count-${r.resource_id}"><i class="fas fa-spinner fa-spin"></i></span>`
            : '<span class="text-muted">-</span>';

        // Actions (show vulnerability button only for VMs)
        let actions = `<button class="btn btn-sm btn-outline-primary py-0 px-1" onclick="showDetails(${idx})" title="Details">` +
                      `<i class="bi bi-chevron-right"></i></button>`;
        if (isVM) {
            actions += ` <a href="/vm-vulnerability?vm_id=${encodeURIComponent(r.resource_id)}" ` +
                       `class="btn btn-sm btn-outline-primary py-0 px-1" title="View CVE vulnerabilities">` +
                       `<i class="fas fa-shield-alt"></i></a>`;
        }

        dataTable.row.add([name, typeCell, rg, loc, tags, discovered, cveBadge, actions]);
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
        searchResources();
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
// CVE Count Loading (for VMs)
// ---------------------------------------------------------------------------

/**
 * Load CVE counts for displayed VMs
 * @param {Array} vmIds - Array of VM resource IDs to check
 */
async function loadCVECounts(vmIds) {
    if (!vmIds || vmIds.length === 0) return;

    try {
        // Get latest scan result
        const response = await fetch('/api/cve/scan/recent?limit=1');
        if (!response.ok) {
            console.warn('Failed to load CVE scan data');
            updateCVEBadgesError(vmIds);
            return;
        }

        const result = await response.json();
        if (!result.success || !result.data || result.data.length === 0) {
            console.warn('No scan data available');
            updateCVEBadgesError(vmIds);
            return;
        }

        const latestScan = result.data[0];
        if (latestScan.status !== 'completed') {
            console.warn('Latest scan not completed');
            updateCVEBadgesError(vmIds);
            return;
        }

        // Count CVEs per VM and track severity
        const vmCVEData = {};
        latestScan.matches.forEach(match => {
            if (!vmCVEData[match.vm_id]) {
                vmCVEData[match.vm_id] = {
                    count: 0,
                    hasCritical: false,
                    hasHigh: false,
                };
            }
            vmCVEData[match.vm_id].count++;
            if (match.severity === 'CRITICAL') {
                vmCVEData[match.vm_id].hasCritical = true;
            } else if (match.severity === 'HIGH') {
                vmCVEData[match.vm_id].hasHigh = true;
            }
        });

        // Update badges with counts and colors
        vmIds.forEach(vmId => {
            const badge = document.getElementById(`cve-count-${vmId}`);
            if (!badge) return;

            const data = vmCVEData[vmId];
            const count = data ? data.count : 0;
            badge.textContent = count;

            // Color-code by severity
            if (count > 0 && data) {
                if (data.hasCritical) {
                    badge.className = 'badge bg-danger';
                } else if (data.hasHigh) {
                    badge.className = 'badge bg-warning';
                } else {
                    badge.className = 'badge bg-info';
                }
            } else {
                badge.className = 'badge bg-success';
            }
        });

    } catch (error) {
        console.error('Error loading CVE counts:', error);
        updateCVEBadgesError(vmIds);
    }
}

/**
 * Update CVE badges to show error state
 * @param {Array} vmIds - Array of VM resource IDs
 */
function updateCVEBadgesError(vmIds) {
    vmIds.forEach(vmId => {
        const badge = document.getElementById(`cve-count-${vmId}`);
        if (badge) {
            badge.textContent = '-';
            badge.className = 'badge bg-secondary';
        }
    });
}

/**
 * Extract VM IDs from current resource display
 * @returns {Array} Array of VM resource IDs
 */
function getDisplayedVMIds() {
    return currentResources
        .filter(r => (r.resource_type || '').toLowerCase() === 'microsoft.compute/virtualmachines')
        .map(r => r.resource_id)
        .filter(id => id);  // Remove any null/undefined IDs
}

/**
 * Called after resources are loaded and rendered
 */
async function onResourcesLoaded() {
    const vmIds = getDisplayedVMIds();
    if (vmIds.length > 0) {
        await loadCVECounts(vmIds);
    }
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

window.goToPage = goToPage;
window.previousPage = previousPage;
window.nextPage = nextPage;
window.changePageSize = changePageSize;
