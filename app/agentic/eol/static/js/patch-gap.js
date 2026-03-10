/**
 * Patch Gap Analysis Page
 *
 * Loads fleet-level patch gap data from GET /api/cve/patch-gaps and renders
 * three tab views: By KB/Advisory, By CVE, and By VM.
 *
 * Install flow:
 *   - Windows: POST /api/patch-management/install with kb_numbers_to_include
 *   - Linux:   POST /api/patch-management/install with package_names_to_include
 *   - Status:  GET  /api/patch-management/install-status (polled every 3s)
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    raw: null,      // full API response data
    filtered: null, // { by_kb, by_cve, by_vm } after current filters
    activeTab: 'by-kb',
    filters: {
        search: '',
        severity: '',
        osType: '',
    },
};

// ---------------------------------------------------------------------------
// Bootstrap entry point
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', init);

async function init() {
    wireDomHandlers();
    await loadData();
}

// ---------------------------------------------------------------------------
// DOM wiring
// ---------------------------------------------------------------------------

function wireDomHandlers() {
    // Refresh / export
    document.getElementById('refresh-btn')?.addEventListener('click', () => loadData());
    document.getElementById('export-csv-btn')?.addEventListener('click', exportCsv);
    document.getElementById('retry-btn')?.addEventListener('click', () => loadData());

    // Filters
    document.getElementById('filter-search')?.addEventListener('input', (e) => {
        state.filters.search = e.target.value.trim().toLowerCase();
        applyFilters();
        renderAll();
    });
    document.getElementById('filter-severity')?.addEventListener('change', (e) => {
        state.filters.severity = e.target.value;
        applyFilters();
        renderAll();
    });
    document.getElementById('filter-os-type')?.addEventListener('change', (e) => {
        state.filters.osType = e.target.value;
        applyFilters();
        renderAll();
    });
    document.getElementById('clear-filters-btn')?.addEventListener('click', clearFilters);

    // Track active tab
    document.querySelectorAll('#patch-gap-tabs button[data-bs-toggle="tab"]').forEach((btn) => {
        btn.addEventListener('shown.bs.tab', (e) => {
            const target = e.target.getAttribute('data-bs-target');
            if (target === '#pane-by-kb') state.activeTab = 'by-kb';
            else if (target === '#pane-by-cve') state.activeTab = 'by-cve';
            else if (target === '#pane-by-vm') state.activeTab = 'by-vm';
        });
    });

    // Install modal confirm
    document.getElementById('install-modal-confirm-btn')?.addEventListener('click', onInstallConfirm);
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadData() {
    showLoading();
    try {
        const result = await fetchJson('/api/cve/patch-gaps');
        state.raw = result?.data || null;

        if (!state.raw) {
            throw new Error('No data returned from server');
        }

        applyFilters();
        hideLoading();
        showContent();
        renderAll();

        // Show stale notice when no scan has run yet
        const staleEl = document.getElementById('stale-notice');
        if (staleEl) {
            const isStale = result?.metadata?.stale === true;
            staleEl.classList.toggle('d-none', !isStale);
        }
    } catch (err) {
        console.error('Patch gap load error:', err);
        showError(err.message || 'Failed to load patch gap data');
    }
}

// ---------------------------------------------------------------------------
// Filtering
// ---------------------------------------------------------------------------

function applyFilters() {
    if (!state.raw) {
        state.filtered = { by_kb: [], by_cve: [], by_vm: [] };
        return;
    }

    const { search, severity, osType } = state.filters;

    let byKb = state.raw.by_kb || [];
    let byCve = state.raw.by_cve || [];
    let byVm = state.raw.by_vm || [];

    if (severity) {
        byKb = byKb.filter((kb) => kb.severity === severity);
        byCve = byCve.filter((cve) => cve.severity === severity);
        // VMs: keep if any KB matches severity — approximation
        byVm = byVm.filter((vm) => !severity || vm.os_type); // pass-through (severity is per-KB)
    }

    if (osType) {
        byKb = byKb.filter((kb) => (kb.os_family || '').toLowerCase().includes(osType.toLowerCase()));
        byVm = byVm.filter((vm) => (vm.os_type || '').toLowerCase() === osType.toLowerCase());
    }

    if (search) {
        byKb = byKb.filter((kb) =>
            (kb.kb_number || '').toLowerCase().includes(search) ||
            (kb.advisory_id || '').toLowerCase().includes(search) ||
            (kb.cve_ids || []).some((c) => c.toLowerCase().includes(search))
        );
        byCve = byCve.filter((cve) =>
            (cve.cve_id || '').toLowerCase().includes(search) ||
            (cve.available_advisory_ids || []).some((a) => a.toLowerCase().includes(search))
        );
        byVm = byVm.filter((vm) =>
            (vm.vm_name || '').toLowerCase().includes(search) ||
            (vm.location || '').toLowerCase().includes(search)
        );
    }

    state.filtered = { by_kb: byKb, by_cve: byCve, by_vm: byVm };
}

function clearFilters() {
    state.filters = { search: '', severity: '', osType: '' };
    const searchEl = document.getElementById('filter-search');
    const severityEl = document.getElementById('filter-severity');
    const osTypeEl = document.getElementById('filter-os-type');
    if (searchEl) searchEl.value = '';
    if (severityEl) severityEl.value = '';
    if (osTypeEl) osTypeEl.value = '';
    applyFilters();
    renderAll();
}

// ---------------------------------------------------------------------------
// Rendering orchestration
// ---------------------------------------------------------------------------

function renderAll() {
    renderSummaryCards();
    renderKBTable();
    renderCVETable();
    renderVMTable();
    updateTabBadges();
}

function renderSummaryCards() {
    const summary = state.raw?.summary || {};
    const filtered = state.filtered || { by_kb: [], by_cve: [], by_vm: [] };

    setEl('metric-outstanding-kbs', filtered.by_kb.length);
    setEl('metric-unpatched-cves', filtered.by_cve.length);
    setEl('metric-vms-with-gaps', filtered.by_vm.length);

    // Most critical: first KB by severity order
    const critical = filtered.by_kb.find((kb) => kb.severity === 'Critical') ||
                     filtered.by_kb[0];
    setEl('metric-most-critical', critical ? (critical.advisory_id || critical.kb_number || '—') : '—');
}

function updateTabBadges() {
    const f = state.filtered || { by_kb: [], by_cve: [], by_vm: [] };
    setEl('badge-by-kb', f.by_kb.length);
    setEl('badge-by-cve', f.by_cve.length);
    setEl('badge-by-vm', f.by_vm.length);
}

// ---------------------------------------------------------------------------
// KB / Advisory table
// ---------------------------------------------------------------------------

function renderKBTable() {
    const tbody = document.getElementById('kb-table-body');
    const emptyEl = document.getElementById('kb-empty');
    const tableEl = document.getElementById('kb-table');
    if (!tbody) return;

    tbody.innerHTML = '';
    const rows = state.filtered?.by_kb || [];

    if (rows.length === 0) {
        tableEl?.classList.add('d-none');
        emptyEl?.classList.remove('d-none');
        return;
    }

    tableEl?.classList.remove('d-none');
    emptyEl?.classList.add('d-none');

    rows.forEach((kb) => {
        const tr = document.createElement('tr');

        // KB/Advisory badge
        const osFam = (kb.os_family || '').toLowerCase();
        const badgeClass = osFam.includes('ubuntu') ? 'text-bg-warning'
                         : osFam.includes('rhel') || osFam.includes('red hat') || osFam.includes('centos') ? 'text-bg-danger'
                         : 'text-bg-primary'; // Windows = blue

        const advisoryId = kb.advisory_id || kb.kb_number || '—';
        const kbDisplay = kb.kb_number && kb.advisory_id && kb.kb_number !== kb.advisory_id
            ? `${kb.advisory_id} <span class="text-muted small">(${kb.kb_number})</span>`
            : escapeHtml(advisoryId);

        tr.innerHTML = `
            <td>
                <span class="badge ${badgeClass} me-1">${escapeHtml(osFam || 'Win')}</span>
                ${kbDisplay}
            </td>
            <td><span class="text-muted small">${escapeHtml(kb.os_family || '—')}</span></td>
            <td>${severityBadge(kb.severity)}</td>
            <td class="text-end fw-semibold">${kb.cve_count || (kb.cve_ids || []).length}</td>
            <td class="text-end">${kb.vm_count || 0}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary"
                        data-kb-number="${escapeHtml(kb.kb_number || '')}"
                        data-advisory-id="${escapeHtml(kb.advisory_id || '')}"
                        data-os-family="${escapeHtml(kb.os_family || '')}"
                        data-cve-ids="${escapeHtml(JSON.stringify(kb.cve_ids || []))}"
                        data-packages="${escapeHtml(JSON.stringify(kb.package_names || []))}"
                        onclick="openInstallModal(this)">
                    <i class="fas fa-download me-1"></i>Install
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ---------------------------------------------------------------------------
// CVE table
// ---------------------------------------------------------------------------

function renderCVETable() {
    const tbody = document.getElementById('cve-table-body');
    const emptyEl = document.getElementById('cve-empty');
    const tableEl = document.getElementById('cve-table');
    if (!tbody) return;

    tbody.innerHTML = '';
    const rows = state.filtered?.by_cve || [];

    if (rows.length === 0) {
        tableEl?.classList.add('d-none');
        emptyEl?.classList.remove('d-none');
        return;
    }

    tableEl?.classList.remove('d-none');
    emptyEl?.classList.add('d-none');

    rows.forEach((cve) => {
        const tr = document.createElement('tr');
        const fixes = (cve.available_advisory_ids || []).slice(0, 3).join(', ');
        const fixOverflow = (cve.available_advisory_ids || []).length > 3
            ? ` <span class="text-muted small">+${(cve.available_advisory_ids || []).length - 3} more</span>` : '';

        tr.innerHTML = `
            <td>
                <a href="/cve-detail/${escapeHtml(cve.cve_id)}" class="fw-semibold text-decoration-none" target="_blank" rel="noopener">
                    ${escapeHtml(cve.cve_id)}
                </a>
            </td>
            <td>${severityBadge(cve.severity)}</td>
            <td class="text-end">
                ${cve.cvss_score != null ? `<span class="badge bg-secondary">${Number(cve.cvss_score).toFixed(1)}</span>` : '—'}
            </td>
            <td class="text-end fw-semibold">${cve.vm_count || 0}</td>
            <td class="small text-muted">${escapeHtml(fixes)}${fixOverflow}</td>
            <td>
                <a href="/vm-vulnerability" class="btn btn-sm btn-outline-secondary">
                    <i class="fas fa-server me-1"></i>View VMs
                </a>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ---------------------------------------------------------------------------
// VM table
// ---------------------------------------------------------------------------

function renderVMTable() {
    const tbody = document.getElementById('vm-table-body');
    const emptyEl = document.getElementById('vm-empty');
    const tableEl = document.getElementById('vm-table');
    if (!tbody) return;

    tbody.innerHTML = '';
    const rows = state.filtered?.by_vm || [];

    if (rows.length === 0) {
        tableEl?.classList.add('d-none');
        emptyEl?.classList.remove('d-none');
        return;
    }

    tableEl?.classList.remove('d-none');
    emptyEl?.classList.add('d-none');

    rows.forEach((vm) => {
        const tr = document.createElement('tr');
        const osType = vm.os_type || '';
        const osBadgeClass = osType.toLowerCase() === 'linux' ? 'text-bg-warning' : 'text-bg-info';

        const vmId = vm.vm_id ? encodeURIComponent(vm.vm_id) : '';
        const detailHref = vmId ? `/vm-vulnerability?vm_id=${vmId}` : '/vm-vulnerability';

        tr.innerHTML = `
            <td class="fw-semibold">${escapeHtml(vm.vm_name || vm.vm_id || '—')}</td>
            <td><span class="badge ${osBadgeClass}">${escapeHtml(osType || '—')}</span></td>
            <td class="small text-muted">${escapeHtml(vm.location || '—')}</td>
            <td class="text-end text-danger fw-semibold">${vm.unpatched_with_fix ?? 0}</td>
            <td class="text-end fw-semibold">${vm.total_unpatched ?? 0}</td>
            <td>
                <a href="${detailHref}" class="btn btn-sm btn-outline-secondary">
                    <i class="fas fa-arrow-right me-1"></i>Details
                </a>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ---------------------------------------------------------------------------
// Install flow
// ---------------------------------------------------------------------------

// Per-KB install context stored when modal opens
let _installContext = null;

function openInstallModal(btn) {
    const kbNumber = btn.dataset.kbNumber || '';
    const advisoryId = btn.dataset.advisoryId || kbNumber;
    const osFamily = (btn.dataset.osFamily || '').toLowerCase();

    let cveIds = [];
    let packages = [];
    try { cveIds = JSON.parse(btn.dataset.cveIds || '[]'); } catch (_) { /* ignore */ }
    try { packages = JSON.parse(btn.dataset.packages || '[]'); } catch (_) { /* ignore */ }

    const isLinux = osFamily.includes('ubuntu') || osFamily.includes('rhel') ||
                    osFamily.includes('red hat') || osFamily.includes('centos') ||
                    osFamily.includes('linux');

    // Collect VMs affected by this KB from the by_vm list
    const affectedVms = (state.filtered?.by_vm || []).filter((vm) => {
        const vmOsIsLinux = (vm.os_type || '').toLowerCase() === 'linux';
        return isLinux ? vmOsIsLinux : !vmOsIsLinux;
    });

    _installContext = {
        kbNumber,
        advisoryId,
        isLinux,
        kbNumbers: kbNumber ? [kbNumber] : [],
        packageNames: packages.length ? packages : (kbNumber ? [kbNumber] : []),
        affectedVms,
    };

    setEl('install-modal-kb-id', advisoryId || kbNumber);
    renderInstallVmRows(affectedVms);

    // Reset confirm button
    const confirmBtn = document.getElementById('install-modal-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fas fa-play me-1"></i>Start Installation';
    }
    const cancelBtn = document.getElementById('install-modal-cancel-btn');
    if (cancelBtn) cancelBtn.disabled = false;

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('installModal'));
    modal.show();
}

function renderInstallVmRows(vms) {
    const container = document.getElementById('install-vm-rows');
    if (!container) return;

    if (!vms.length) {
        container.innerHTML = '<p class="text-muted">No VMs identified for this patch.</p>';
        return;
    }

    container.innerHTML = vms.map((vm, idx) => `
        <div class="d-flex align-items-center gap-3 py-2 border-bottom" id="install-vm-row-${idx}">
            <div class="flex-grow-1">
                <div class="fw-semibold">${escapeHtml(vm.vm_name || vm.vm_id || '—')}</div>
                <div class="small text-muted">${escapeHtml(vm.os_type || '')} · ${escapeHtml(vm.location || '')}</div>
            </div>
            <div id="install-vm-status-${idx}">
                <span class="badge text-bg-secondary">Pending</span>
            </div>
        </div>
    `).join('');
}

async function onInstallConfirm() {
    if (!_installContext) return;

    const confirmBtn = document.getElementById('install-modal-confirm-btn');
    const cancelBtn = document.getElementById('install-modal-cancel-btn');
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Installing...'; }
    if (cancelBtn) cancelBtn.disabled = true;

    const { isLinux, kbNumbers, packageNames, affectedVms } = _installContext;

    for (let idx = 0; idx < affectedVms.length; idx++) {
        const vm = affectedVms[idx];
        setVmInstallStatus(idx, 'info', 'Installing...');
        try {
            await installOnVM(vm.vm_id, isLinux ? 'Linux' : 'Windows', kbNumbers, packageNames, idx);
            setVmInstallStatus(idx, 'success', 'Installed');
        } catch (err) {
            setVmInstallStatus(idx, 'danger', `Failed: ${err.message}`);
        }
    }

    if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.innerHTML = '<i class="fas fa-check me-1"></i>Done'; }
    if (cancelBtn) cancelBtn.disabled = false;
}

function setVmInstallStatus(idx, tone, text) {
    const el = document.getElementById(`install-vm-status-${idx}`);
    if (el) el.innerHTML = `<span class="badge text-bg-${tone}">${escapeHtml(text)}</span>`;
}

async function installOnVM(vmId, osType, kbNumbers, packageNames, vmIdx) {
    const body = {
        resource_id: vmId,
        os_type: osType,
    };

    if (osType === 'Windows') {
        body.kb_numbers_to_include = kbNumbers;
    } else {
        body.package_names_to_include = packageNames.length ? packageNames : kbNumbers;
    }

    const installResp = await fetch('/api/patch-management/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (!installResp.ok) {
        const detail = await installResp.json().catch(() => null);
        throw new Error(detail?.detail || `HTTP ${installResp.status}`);
    }

    const installData = await installResp.json();
    const operationUrl = installData?.operation_url;
    if (!operationUrl) {
        // Synchronous completion — no polling needed
        return;
    }

    // Poll for completion
    await pollInstallStatus(operationUrl, vmIdx);
}

async function pollInstallStatus(operationUrl, vmIdx) {
    const maxAttempts = 40; // 40 × 3s = 2 min cap
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        await sleep(3000);
        try {
            const statusUrl = `/api/patch-management/install-status?operation_url=${encodeURIComponent(operationUrl)}`;
            const resp = await fetch(statusUrl);
            if (!resp.ok) continue;

            const data = await resp.json();
            const isDone = data?.is_done === true || data?.data?.is_done === true;
            const status = data?.status || data?.data?.status || '';

            if (isDone) return;

            if (status === 'Failed' || status === 'Canceled') {
                throw new Error(`Install ${status.toLowerCase()}`);
            }
        } catch (pollErr) {
            if (pollErr.message.startsWith('Install ')) throw pollErr;
            // transient network error — keep polling
        }
    }
    // Timed out — treat as success (operation may still be running server-side)
}

// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------

function exportCsv() {
    const tab = state.activeTab;
    let headers = [];
    let rows = [];

    if (tab === 'by-kb') {
        headers = ['KB/Advisory', 'OS Family', 'Severity', 'CVEs Fixed', 'VMs Affected'];
        rows = (state.filtered?.by_kb || []).map((kb) => [
            kb.advisory_id || kb.kb_number,
            kb.os_family,
            kb.severity,
            kb.cve_count || (kb.cve_ids || []).length,
            kb.vm_count,
        ]);
    } else if (tab === 'by-cve') {
        headers = ['CVE ID', 'Severity', 'CVSS', 'VMs', 'Available Fixes'];
        rows = (state.filtered?.by_cve || []).map((cve) => [
            cve.cve_id,
            cve.severity,
            cve.cvss_score != null ? Number(cve.cvss_score).toFixed(1) : '',
            cve.vm_count,
            (cve.available_advisory_ids || []).join('; '),
        ]);
    } else {
        headers = ['VM Name', 'OS Type', 'Location', 'Unpatched w/ Fix', 'Total Unpatched'];
        rows = (state.filtered?.by_vm || []).map((vm) => [
            vm.vm_name || vm.vm_id,
            vm.os_type,
            vm.location,
            vm.unpatched_with_fix,
            vm.total_unpatched,
        ]);
    }

    const csv = [headers, ...rows]
        .map((row) => row.map(csvEscape).join(','))
        .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `patch-gap-${tab}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// UI helpers (mirror vm-vulnerability.js patterns)
// ---------------------------------------------------------------------------

function showLoading() {
    document.getElementById('page-loading')?.classList.remove('d-none');
    document.getElementById('page-error')?.classList.add('d-none');
    document.getElementById('patch-gap-content')?.classList.add('d-none');
}

function hideLoading() {
    document.getElementById('page-loading')?.classList.add('d-none');
}

function showContent() {
    document.getElementById('patch-gap-content')?.classList.remove('d-none');
}

function showError(message) {
    document.getElementById('page-loading')?.classList.add('d-none');
    document.getElementById('page-error')?.classList.remove('d-none');
    document.getElementById('patch-gap-content')?.classList.add('d-none');
    const msgEl = document.getElementById('error-message');
    if (msgEl) msgEl.textContent = message;
}

function setEl(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function severityBadge(severity) {
    const s = (severity || '').toUpperCase();
    const colorMap = {
        CRITICAL: 'danger',
        HIGH: 'warning',
        MEDIUM: 'info',
        LOW: 'secondary',
    };
    const color = colorMap[s] || 'secondary';
    return `<span class="badge bg-${color}">${escapeHtml(severity || 'Unknown')}</span>`;
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        let message = `API error: ${response.statusText}`;
        try {
            const body = await response.json();
            message = body?.message || body?.detail || message;
        } catch (_) { /* ignore */ }
        throw new Error(message);
    }
    return response.json();
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function csvEscape(value) {
    const text = String(value ?? '');
    return `"${text.replace(/"/g, '""')}"`;
}

function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
}
