/**
 * Inventory Filtering and Sorting Module
 * Handles search, filtering, and table sorting functionality
 */

import { state, setCurrentInventory, updateCurrentPage, updateSortState } from './inventory-state.js';

/**
 * Initialize sorting event listeners on table headers
 */
export function initializeSorting() {
    document.querySelectorAll('.sortable').forEach(header => {
        header.addEventListener('click', function () {
            const sortColumn = this.getAttribute('data-sort');
            sortTable(sortColumn);
        });
    });
}

/**
 * Sort table by column
 * @param {string} column - Column name to sort by
 * @param {Function} filterCallback - Callback to re-filter after sorting
 */
export function sortTable(column, filterCallback) {
    // Determine sort direction
    let direction = 'asc';
    if (state.currentSortColumn === column) {
        if (state.currentSortDirection === 'asc') {
            direction = 'desc';
        } else if (state.currentSortDirection === 'desc') {
            direction = 'none';
        } else {
            direction = 'asc';
        }
    }

    // Update sort state
    updateSortState(column, direction);

    // Update UI indicators
    updateSortIndicators(column, direction);

    // Sort the data if not "none"
    if (direction !== 'none') {
        state.currentInventory.sort((a, b) => {
            let valueA = getSortValue(a, column);
            let valueB = getSortValue(b, column);

            // Handle special cases
            if (column === 'eol_status') {
                return compareEOLStatus(valueA, valueB, direction);
            }

            // Convert to strings for comparison if not numbers
            if (typeof valueA !== 'number' && typeof valueB !== 'number') {
                valueA = String(valueA).toLowerCase();
                valueB = String(valueB).toLowerCase();
            }

            if (valueA < valueB) {
                return direction === 'asc' ? -1 : 1;
            }
            if (valueA > valueB) {
                return direction === 'asc' ? 1 : -1;
            }
            return 0;
        });
    }

    // Re-render the filtered results
    if (filterCallback) {
        filterCallback();
    }
}

/**
 * Get sort value for an item by column
 * @param {Object} item - Inventory item
 * @param {string} column - Column name
 * @returns {*} Sort value
 */
function getSortValue(item, column) {
    switch (column) {
        case 'computer':
            return item.computer || 'Unknown';
        case 'computer_type':
            return item.computer_type || 'Unknown';
        case 'name':
            return item.name || 'Unknown';
        case 'version':
            return item.version || '';
        case 'publisher':
            return item.publisher || 'Unknown';
        case 'software_type':
            return item.software_type || 'Application';
        case 'eol_status':
            // Get EOL status from the DOM element if available
            const statusElement = document.getElementById(`eol-status-${item.id}`);
            if (statusElement) {
                const statusText = statusElement.textContent.trim();
                return getEOLSortPriority(statusText);
            }
            return 999; // Default for unknown status
        default:
            return '';
    }
}

/**
 * Get sort priority for EOL status text
 * @param {string} statusText - EOL status text
 * @returns {number} Priority value (lower = higher priority)
 */
function getEOLSortPriority(statusText) {
    // Define priority order for EOL statuses
    if (statusText.includes('End of Life') || statusText.includes('EOL')) return 1;
    if (statusText.includes('Soon') || statusText.includes('Warning')) return 2;
    if (statusText.includes('Supported') || statusText.includes('Active')) return 3;
    if (statusText.includes('Checking') || statusText.includes('Loading')) return 4;
    if (statusText.includes('N/A')) return 5;
    if (statusText.includes('Unknown')) return 6;
    return 7; // Default
}

/**
 * Compare EOL status values for sorting
 * @param {number} valueA - First value
 * @param {number} valueB - Second value
 * @param {string} direction - Sort direction ('asc' or 'desc')
 * @returns {number} Comparison result
 */
function compareEOLStatus(valueA, valueB, direction) {
    if (direction === 'asc') {
        return valueA - valueB;
    } else {
        return valueB - valueA;
    }
}

/**
 * Update sort indicator icons in table headers
 * @param {string} activeColumn - Currently active sort column
 * @param {string} direction - Sort direction ('asc', 'desc', or 'none')
 */
function updateSortIndicators(activeColumn, direction) {
    // Reset all sort indicators
    document.querySelectorAll('.sort-icon').forEach(icon => {
        icon.setAttribute('data-sort-direction', 'none');
        icon.className = 'fas fa-sort sort-icon ms-1';
    });

    // Update active column indicator
    if (direction !== 'none') {
        const activeHeader = document.querySelector(`[data-sort="${activeColumn}"] .sort-icon`);
        if (activeHeader) {
            activeHeader.setAttribute('data-sort-direction', direction);
            activeHeader.className = `fas fa-sort-${direction === 'asc' ? 'up' : 'down'} sort-icon ms-1`;
        }
    }

    // Show/hide reset sort button
    const resetBtn = document.getElementById('reset-sort-btn');
    if (resetBtn) {
        if (direction !== 'none') {
            resetBtn.style.display = 'inline-block';
        } else {
            resetBtn.style.display = 'none';
        }
    }
}

/**
 * Reset sort to original order
 * @param {Function} reloadCallback - Callback to reload inventory
 */
export function resetSort(reloadCallback) {
    updateSortState(null, 'none');
    updateSortIndicators('', 'none');

    // Reload inventory to restore original order
    if (reloadCallback) {
        reloadCallback();
    }
}

/**
 * Filter inventory by search term
 * @param {Function} displayCallback - Callback to display filtered results
 * @param {Function} updateSummaryCallback - Callback to update summary
 */
export function filterInventory(displayCallback, updateSummaryCallback) {
    const searchInput = document.getElementById('search-input');
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    let filtered = [...state.currentInventory];

    if (searchTerm) {
        filtered = filtered.filter(item =>
            (item.name || '').toLowerCase().includes(searchTerm) ||
            (item.publisher || '').toLowerCase().includes(searchTerm) ||
            (item.version || '').toLowerCase().includes(searchTerm) ||
            (item.software_type || '').toLowerCase().includes(searchTerm) ||
            (item.computer_type || '').toLowerCase().includes(searchTerm) ||
            (item.computer || '').toLowerCase().includes(searchTerm)
        );
    }

    // Reset to first page
    updateCurrentPage(1);

    // Display filtered results
    if (displayCallback) {
        displayCallback(filtered);
    }
    
    // Update summary if callback provided
    if (updateSummaryCallback) {
        updateSummaryCallback(filtered.length, state.currentInventory.length, searchTerm, []);
    }
}

/**
 * Apply multiple filters (search, type, status)
 * @param {Function} displayCallback - Callback to display filtered results
 * @param {Function} updateSummaryCallback - Callback to update summary
 */
export function applyFilters(displayCallback, updateSummaryCallback) {
    const searchInput = document.getElementById('search-input');
    const typeFilterEl = document.getElementById('type-filter');
    const statusFilterEl = document.getElementById('status-filter');

    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const typeFilter = typeFilterEl ? typeFilterEl.value : '';
    const statusFilter = statusFilterEl ? statusFilterEl.value : '';

    const filtered = state.currentInventory.filter(item => {
        // Search filter
        const searchMatch = !searchTerm ||
            (item.name && item.name.toLowerCase().includes(searchTerm)) ||
            (item.computer && item.computer.toLowerCase().includes(searchTerm)) ||
            (item.publisher && item.publisher.toLowerCase().includes(searchTerm)) ||
            (item.version && item.version.toLowerCase().includes(searchTerm));

        // Type filter
        const typeMatch = !typeFilter ||
            (typeFilter === 'Software' && item.software_type !== 'Operating System') ||
            (typeFilter === 'OS' && item.software_type === 'Operating System');

        // Status filter
        const statusMatch = !statusFilter ||
            (item.eol_status && item.eol_status === statusFilter);

        return searchMatch && typeMatch && statusMatch;
    });

    // Reset to first page when filters change
    updateCurrentPage(1);
    
    // Display filtered results
    if (displayCallback) {
        displayCallback(filtered);
    }
    
    // Update summary if callback provided
    if (updateSummaryCallback) {
        updateSummaryCallback(filtered.length, state.currentInventory.length, searchTerm);
    }
}

/**
 * Clear all filter inputs and show all data
 * @param {Function} applyFiltersCallback - Callback to reapply filters
 */
export function clearAllFilters(applyFiltersCallback) {
    // Clear all filter inputs
    const searchInput = document.getElementById('search-input');
    const typeFilter = document.getElementById('type-filter');
    const statusFilter = document.getElementById('status-filter');

    if (searchInput) searchInput.value = '';
    if (typeFilter) typeFilter.value = '';
    if (statusFilter) statusFilter.value = '';

    // Reapply filters (which will show all data since inputs are cleared)
    if (applyFiltersCallback) {
        applyFiltersCallback();
    }
}

/**
 * Change page size and reset to first page
 * @param {string} selectId - ID of page size select element
 * @param {Function} displayCallback - Callback to redisplay inventory
 * @param {Function} updateSummaryCallback - Callback to update summary
 */
export function changePageSize(selectId, displayCallback, updateSummaryCallback) {
    const pageSizeSelect = document.getElementById(selectId);
    if (pageSizeSelect) {
        state.pageSize = parseInt(pageSizeSelect.value) || 25;
    }

    // Sync other page size selectors
    syncPageSizeSelectors(state.pageSize);

    // Reset to first page when changing page size
    updateCurrentPage(1);

    // Re-display with current data
    if (displayCallback) {
        displayCallback(state.filteredInventory);
    }
    
    // Update summary if callback provided
    if (updateSummaryCallback) {
        updateSummaryCallback(state.filteredInventory.length, state.currentInventory.length, null);
    }
}

/**
 * Sync all page size selectors to the same value
 * @param {number} pageSize - Page size value
 */
function syncPageSizeSelectors(pageSize) {
    const selectors = [
        'page-size-select',
        'page-size-select-top',
        'page-size'
    ];

    selectors.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.value = pageSize;
        }
    });
}
