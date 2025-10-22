/**
 * Inventory State Management Module
 * Handles all state variables and localStorage operations for the inventory page
 */

// State variables
export const state = {
    currentInventory: [],
    filteredInventory: [],
    currentSortColumn: null,
    currentSortDirection: 'none',
    
    // Pagination
    currentPage: 1,
    pageSize: 50, // Match the HTML default selection
    totalPages: 1,
    totalEntries: 0
};

/**
 * Save current view state to localStorage
 */
export function saveViewState() {
    try {
        const daysSelect = document.getElementById('days-select');
        const limitInput = document.getElementById('limit-input');
        const pageSizeSelect = document.getElementById('page-size-select');

        const viewState = {
            timestamp: Date.now(),
            daysSelect: daysSelect ? daysSelect.value : '90',
            limitInput: limitInput ? limitInput.value : '5000',
            pageSize: pageSizeSelect ? pageSizeSelect.value : '50'
        };

        localStorage.setItem('eol_inventory_state', JSON.stringify(viewState));
    } catch (error) {
        console.warn('Error saving view state:', error);
    }
}

/**
 * Try to restore last view state from localStorage
 */
export function tryRestoreViewState() {
    try {
        const savedState = localStorage.getItem('eol_inventory_state');
        if (savedState) {
            const viewState = JSON.parse(savedState);
            if (viewState.timestamp && (Date.now() - viewState.timestamp < 300000)) { // 5 minutes
                // Restore filters and view settings
                if (viewState.daysSelect) {
                    const daysSelect = document.getElementById('days-select');
                    if (daysSelect) daysSelect.value = viewState.daysSelect;
                }
                if (viewState.limitInput) {
                    const limitInput = document.getElementById('limit-input');
                    if (limitInput) limitInput.value = viewState.limitInput;
                }
                if (viewState.pageSize) {
                    const pageSizeSelect = document.getElementById('page-size-select');
                    if (pageSizeSelect) pageSizeSelect.value = viewState.pageSize;
                    state.pageSize = parseInt(viewState.pageSize, 10);
                }
            }
        }
    } catch (error) {
        console.warn('Error restoring view state:', error);
    }
}

/**
 * Update page size in state
 */
export function updatePageSize(newSize) {
    state.pageSize = newSize;
    state.currentPage = 1; // Reset to first page when page size changes
}

/**
 * Update current page in state
 */
export function updateCurrentPage(page) {
    state.currentPage = page;
}

/**
 * Update sort column and direction in state
 */
export function updateSortState(column, direction) {
    state.currentSortColumn = column;
    state.currentSortDirection = direction;
}

/**
 * Update pagination totals in state
 */
export function updatePaginationTotals(totalPages, totalEntries) {
    state.totalPages = totalPages;
    state.totalEntries = totalEntries;
}

/**
 * Set current inventory data
 */
export function setCurrentInventory(inventory) {
    state.currentInventory = inventory;
}

/**
 * Set filtered inventory data
 */
export function setFilteredInventory(inventory) {
    state.filteredInventory = inventory;
}

/**
 * Get current inventory data
 */
export function getCurrentInventory() {
    return state.currentInventory;
}

/**
 * Get filtered inventory data
 */
export function getFilteredInventory() {
    return state.filteredInventory;
}

/**
 * Reset all state to initial values
 */
export function resetState() {
    state.currentInventory = [];
    state.filteredInventory = [];
    state.currentSortColumn = null;
    state.currentSortDirection = 'none';
    state.currentPage = 1;
    state.pageSize = 50;
    state.totalPages = 1;
    state.totalEntries = 0;
}
