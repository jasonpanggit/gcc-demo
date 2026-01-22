/**
 * Inventory Display Module
 * Handles rendering inventory table, pagination controls, and page navigation
 */

import { state, updateCurrentPage, updatePaginationTotals, setFilteredInventory } from './inventory-state.js';
import { getAzurePortalLink, getComputerTypeBadge, escapeHtml } from './azure-helpers.js';

// Track timeout for automatic EOL checks
let autoEOLCheckTimeout = null;

// Track manually checked items to avoid duplicate automatic checks
const manuallyCheckedItems = new Set();

/**
 * Display inventory with pagination (handles both array and dict formats)
 * @param {Array|Object} inventoryData - Inventory data (array or {success: bool, data: array})
 */
export function displayInventoryWithPagination(
    inventoryData,
    checkEOLCallback = null,
    updateSummaryCallback = null
) {
    // Handle both old array format and new dict format
    let inventory;
    if (Array.isArray(inventoryData)) {
        // Legacy format - just an array
        inventory = inventoryData;
    } else if (inventoryData && inventoryData.success) {
        // New Dict format with metadata
        inventory = inventoryData.data || [];
    } else {
        // Fallback
        inventory = [];
    }

    // Get the current page size from the dropdown (try top first, then bottom)
    const pageSizeSelectTop = document.getElementById('page-size-select-top');
    const pageSizeSelect = document.getElementById('page-size-select');

    if (pageSizeSelectTop) {
        state.pageSize = parseInt(pageSizeSelectTop.value) || 50;
    } else if (pageSizeSelect) {
        state.pageSize = parseInt(pageSizeSelect.value) || 50;
    }

    // Use the existing display function
    displayInventory(inventory, checkEOLCallback, updateSummaryCallback);
}

/**
 * Display inventory data in table with pagination
 * @param {Array} inventory - Array of inventory items
 * @param {Function} checkEOLCallback - Callback function for EOL checking
 * @param {Function} updateSummaryCallback - Callback function for updating summary
 */
export function displayInventory(inventory, checkEOLCallback = null, updateSummaryCallback = null) {
    // Store the filtered inventory for pagination
    setFilteredInventory(inventory);
    const totalEntries = inventory.length;

    // Calculate pagination
    const totalPages = Math.ceil(totalEntries / state.pageSize);
    updatePaginationTotals(totalPages, totalEntries);

    // Ensure current page is valid
    if (state.currentPage > state.totalPages) {
        updateCurrentPage(Math.max(1, state.totalPages));
    }

    // Get items for current page
    const startIndex = (state.currentPage - 1) * state.pageSize;
    const endIndex = startIndex + state.pageSize;
    const pageItems = inventory.slice(startIndex, endIndex);

    const tbody = document.getElementById('inventory-table-body');

    if (!tbody) {
        console.error('ERROR: Table body element not found!');
        return;
    }

    if (inventory.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-4">
                    <i class="fas fa-inbox text-muted fa-2x mb-2"></i>
                    <p class="text-muted mb-0">No inventory data available</p>
                </td>
            </tr>
        `;
        // Hide both pagination containers
        togglePaginationContainers(false);
        return;
    }

    // Show both pagination containers
    togglePaginationContainers(true);
    updatePaginationNav();

    // Render table rows with DOM-safe IDs
    tbody.innerHTML = pageItems.map(item => {
        const rawId = item.id || Math.random().toString(36).substr(2, 9);
        const domSafeId = `item-${rawId.toString().replace(/[^A-Za-z0-9_-]/g, '-')}`;
        // Keep original for data/debug, but use dom-safe for rendering and callbacks
        item.original_id = rawId;
        item.id = domSafeId;
        item.dom_id = domSafeId;
        return renderInventoryRow(item, domSafeId);
    }).join('');

    // Clear any previous automatic EOL check timeout
    if (autoEOLCheckTimeout) {
        clearTimeout(autoEOLCheckTimeout);
    }

    // Start EOL checks for all items after a brief delay
    if (checkEOLCallback) {
        autoEOLCheckTimeout = setTimeout(() => {
            startAutomaticEOLChecks(inventory, checkEOLCallback);
        }, 1000);
    }

    // Initialize multi-select dropdowns after data is displayed
    initializeDropdownsAfterDisplay();
}

/**
 * Render a single inventory table row
 * @param {Object} item - Inventory item
 * @param {string} itemId - Unique item ID
 * @returns {string} HTML string for table row
 */
function renderInventoryRow(item, itemId) {
    const isSearchable = (item.software_type || '').toLowerCase() === 'application' || 
                         (item.software_type || '').toLowerCase() === 'operating system';
    const eolBadge = renderEolBadge(item);
    
    return `
        <tr>
            <td>
                <i class="fas fa-desktop text-primary me-2"></i>
                <a href="${getAzurePortalLink(item)}" 
                   target="_blank" 
                   class="text-decoration-none"
                   title="View in Azure Portal">
                    ${escapeHtml(item.computer || 'N/A')}
                    <i class="fas fa-external-link-alt ms-1 text-muted icon-sm"></i>
                </a>
            </td>
            <td>
                ${getComputerTypeBadge(item)}
            </td>
            <td>
                ${isSearchable ?
                    `<div class="software-name-clickable" 
                          onclick="handleManualEOLCheck('${escapeHtml(item.name)}', '${escapeHtml(item.version || '')}', '${itemId}')"
                          title="Click to search EOL information for ${escapeHtml(item.name)}${item.version ? ' v' + escapeHtml(item.version) : ''}"
                          style="cursor: pointer; color: #0d6efd;">
                        <strong>${escapeHtml(item.name || 'Unknown')}</strong>
                        <small class="text-muted d-block mt-1">
                            <i class="fas fa-search me-1 icon-sm"></i>
                            Click to search EOL info
                        </small>
                    </div>` :
                    `<strong>${escapeHtml(item.name || 'Unknown')}</strong>`
                }
                ${item.name && item.name.includes('(Arc-enabled)') ? '<i class="fas fa-cloud ms-1 text-success" title="Arc-enabled OS"></i>' : ''}
            </td>
            <td>
                <span class="badge bg-secondary text-light">${escapeHtml(item.version || 'N/A')}</span>
            </td>
            <td>${escapeHtml(item.publisher || 'Unknown')}</td>
            <td>
                <span class="badge bg-info text-dark">${escapeHtml(item.software_type || 'Application')}</span>
            </td>
            <td id="eol-status-${itemId}">
                ${eolBadge}
            </td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="checkEOLInPlace('${escapeHtml(item.name)}', '${escapeHtml(item.version || '')}', '${itemId}', '${escapeHtml(item.software_type || '')}')">
                    <i class="fas fa-sync me-1"></i>
                    Refresh EOL
                </button>
            </td>
        </tr>
    `;
}

function renderEolBadge(item) {
    if (!item) {
        return `
            <span class="badge bg-secondary text-light">
                <i class="fas fa-clock me-1"></i>
                Checking...
            </span>
        `;
    }

    const eolDate = item.eol_date || item.support_end_date;
    const eolStatus = (item.eol_status || '').toLowerCase();

    if (!eolDate && !eolStatus) {
        return `
            <span class="badge bg-secondary text-light">
                <i class="fas fa-clock me-1"></i>
                Checking...
            </span>
        `;
    }

    if (eolStatus && !eolDate) {
        return `
            <span class="badge bg-secondary text-light">
                <i class="fas fa-info-circle me-1"></i>
                ${escapeHtml(item.eol_status)}
            </span>
        `;
    }

    const parsed = new Date(eolDate);
    if (Number.isNaN(parsed.getTime())) {
        return `
            <span class="badge bg-secondary text-light">
                <i class="fas fa-question me-1"></i>
                Unknown
            </span>
        `;
    }

    const now = new Date();
    const daysDiff = Math.ceil((parsed - now) / (1000 * 60 * 60 * 24));
    const formattedDate = eolDate.includes('-') ? eolDate : parsed.toISOString().split('T')[0];

    if (daysDiff < 0) {
        return `
            <span class="badge bg-danger text-light">
                <i class="fas fa-times-circle me-1"></i>
                EOL (${formattedDate})
            </span>
        `;
    }
    if (daysDiff <= 90) {
        return `
            <span class="badge bg-warning text-dark">
                <i class="fas fa-exclamation-triangle me-1"></i>
                ${daysDiff}d (${formattedDate})
            </span>
        `;
    }
    if (daysDiff <= 365) {
        return `
            <span class="badge bg-info text-dark">
                <i class="fas fa-clock me-1"></i>
                ${Math.ceil(daysDiff / 30)}mo (${formattedDate})
            </span>
        `;
    }

    return `
        <span class="badge bg-success text-light">
            <i class="fas fa-check-circle me-1"></i>
            OK (${formattedDate})
        </span>
    `;
}

/**
 * Start automatic EOL checks for all inventory items
 * @param {Array} inventory - Array of inventory items
 * @param {Function} checkEOLCallback - Callback function for checking EOL
 */
function startAutomaticEOLChecks(inventory, checkEOLCallback) {
    let osCount = 0;
    let appCount = 0;
    let checkedCount = 0;
    
    inventory.forEach(item => {
        const softwareType = (item.software_type || '').toLowerCase();
        if (softwareType === 'operating system') osCount++;
        if (softwareType === 'application') appCount++;
        
        if (item.name && !item.name.includes('(Arc-enabled)')) {
            // Only check EOL for applications and operating systems
            if (softwareType === 'application' || softwareType === 'operating system') {
                // Skip automatic checking if item was manually checked
                if (!manuallyCheckedItems.has(item.id) && !manuallyCheckedItems.has(item.dom_id)) {
                    if (item.eol_date || item.eol_status) {
                        return;
                    }
                    checkedCount++;
                    const targetId = item.dom_id || item.id;
                    checkEOLCallback(item.name, item.version || '', targetId, item.software_type || '');
                }
            } else {
                // Set N/A status for other types
                setEOLStatusNA(item.id);
            }
        }
    });
}

/**
 * Set EOL status to N/A for an item
 * @param {string} itemId - Item ID
 */
function setEOLStatusNA(itemId) {
    const statusElement = document.getElementById(`eol-status-${itemId}`);
    if (statusElement) {
        statusElement.innerHTML = `
            <span class="badge bg-light text-dark">
                <i class="fas fa-minus me-1"></i>
                N/A
            </span>
        `;
    }
}

/**
 * Toggle visibility of pagination containers
 * @param {boolean} show - Whether to show or hide
 */
function togglePaginationContainers(show) {
    const paginationContainer = document.getElementById('pagination-container');
    const paginationContainerTop = document.getElementById('pagination-container-top');
    
    const display = show ? 'block' : 'none';
    
    if (paginationContainer) {
        paginationContainer.style.display = display;
    }
    if (paginationContainerTop) {
        paginationContainerTop.style.display = display;
    }
}

/**
 * Update pagination navigation controls
 */
function updatePaginationNav() {
    // Update main pagination controls (uses dynamically generated content)
    updatePaginationControls('pagination-controls');
    updatePaginationControls('pagination-controls-top');
}

/**
 * Update pagination controls HTML
 * @param {string} controlsId - ID of pagination controls element
 */
function updatePaginationControls(controlsId) {
    const paginationControls = document.getElementById(controlsId);
    if (!paginationControls) return;

    // Generate pagination HTML
    let paginationHTML = '';

    // Previous button
    paginationHTML += `
        <li class="page-item ${state.currentPage <= 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="window.inventoryPagination.previousPage(); return false;" aria-label="Previous">
                <span aria-hidden="true">&laquo;</span>
            </a>
        </li>
    `;

    // Page numbers
    const pageNumbers = generatePageNumbers();
    pageNumbers.forEach(pageInfo => {
        if (pageInfo.disabled) {
            paginationHTML += `
                <li class="page-item disabled">
                    <span class="page-link">${pageInfo.text}</span>
                </li>
            `;
        } else {
            paginationHTML += `
                <li class="page-item ${pageInfo.active ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="window.inventoryPagination.goToPage(${pageInfo.page}); return false;">${pageInfo.text}</a>
                </li>
            `;
        }
    });

    // Next button
    paginationHTML += `
        <li class="page-item ${state.currentPage >= state.totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="window.inventoryPagination.nextPage(); return false;" aria-label="Next">
                <span aria-hidden="true">&raquo;</span>
            </a>
        </li>
    `;

    paginationControls.innerHTML = paginationHTML;
}

/**
 * Generate array of page numbers for pagination display
 * @returns {Array} Array of page info objects
 */
function generatePageNumbers() {
    const pages = [];
    const maxVisiblePages = 5;
    const halfVisible = Math.floor(maxVisiblePages / 2);

    let startPage = Math.max(1, state.currentPage - halfVisible);
    let endPage = Math.min(state.totalPages, startPage + maxVisiblePages - 1);

    // Adjust start page if we're near the end
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    // Add first page and ellipsis if needed
    if (startPage > 1) {
        pages.push({ page: 1, text: '1', active: false, disabled: false });
        if (startPage > 2) {
            pages.push({ page: null, text: '...', active: false, disabled: true });
        }
    }

    // Add visible page numbers
    for (let i = startPage; i <= endPage; i++) {
        pages.push({
            page: i,
            text: i.toString(),
            active: i === state.currentPage,
            disabled: false
        });
    }

    // Add last page and ellipsis if needed
    if (endPage < state.totalPages) {
        if (endPage < state.totalPages - 1) {
            pages.push({ page: null, text: '...', active: false, disabled: true });
        }
        pages.push({ page: state.totalPages, text: state.totalPages.toString(), active: false, disabled: false });
    }

    return pages;
}

/**
 * Go to specific page
 * @param {number} page - Page number to go to
 * @param {Function} redisplayCallback - Callback to redisplay inventory
 */
export function goToPage(page, redisplayCallback) {
    if (page < 1 || page > state.totalPages || page === state.currentPage) {
        return;
    }

    updateCurrentPage(page);
    if (redisplayCallback) {
        redisplayCallback(state.filteredInventory);
    }
}

/**
 * Go to previous page
 * @param {Function} redisplayCallback - Callback to redisplay inventory
 */
export function previousPage(redisplayCallback) {
    if (state.currentPage > 1) {
        goToPage(state.currentPage - 1, redisplayCallback);
    }
}

/**
 * Go to next page
 * @param {Function} redisplayCallback - Callback to redisplay inventory
 */
export function nextPage(redisplayCallback) {
    if (state.currentPage < state.totalPages) {
        goToPage(state.currentPage + 1, redisplayCallback);
    }
}

/**
 * Initialize dropdowns after display
 */
function initializeDropdownsAfterDisplay() {
    setTimeout(() => {
        try {
            // Column filters have been removed - using main search only
            // console.log('Inventory display initialized');
        } catch (error) {
            console.warn('Initialization warning:', error);
        }
    }, 100);
}

/**
 * Mark item as manually checked (to skip automatic checking)
 * @param {string} itemId - Item ID
 */
export function markAsManuallyChecked(itemId) {
    manuallyCheckedItems.add(itemId);
}

/**
 * Clear manually checked items set
 */
export function clearManuallyCheckedItems() {
    manuallyCheckedItems.clear();
}
