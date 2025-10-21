/**
 * Azure Helper Functions Module
 * Handles Azure Portal links, computer type badges, and Arc-enabled detection
 */

import { state } from './inventory-state.js';

/**
 * Check if computer has Arc-enabled OS
 * @param {Object} item - Inventory item
 * @returns {boolean} True if computer has Arc-enabled OS
 */
export function hasArcOS(item) {
    // Check if this computer has any Arc-enabled OS
    return state.currentInventory.some(inv =>
        inv.computer === item.computer &&
        inv.name &&
        inv.name.includes('(Arc-enabled)') &&
        inv.software_type === 'operating system'
    );
}

/**
 * Generate Azure Portal link for a resource
 * @param {Object} item - Inventory item with resource information
 * @param {string} subscriptionId - Azure subscription ID (can be template variable)
 * @param {string} resourceGroup - Azure resource group (can be template variable)
 * @returns {string} Azure Portal URL
 */
export function getAzurePortalLink(item, subscriptionId = '', resourceGroup = '') {
    // Get computer type and resource information
    const computerType = item.computer_type || 'Unknown';
    const resourceId = item.resource_id || '';
    const computerName = item.computer || 'Unknown';

    // Use subscription and resource group from parameters or inventory item
    const subId = item.subscription_id || subscriptionId || 'SUBSCRIPTION_ID';
    const resGroup = item.resource_group || resourceGroup || 'RESOURCE_GROUP';

    // If we have a resource ID, use it to construct the correct portal link
    if (resourceId) {
        // Extract subscription ID and resource group from resource ID if available
        const resourceIdParts = resourceId.split('/');
        let extractedSubscriptionId = subId;
        let extractedResourceGroup = resGroup;

        if (resourceIdParts.length > 4) {
            // Resource ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/{provider}/{type}/{name}
            if (resourceIdParts[1] === 'subscriptions' && resourceIdParts[2]) {
                extractedSubscriptionId = resourceIdParts[2];
            }
            if (resourceIdParts[3] === 'resourceGroups' && resourceIdParts[4]) {
                extractedResourceGroup = resourceIdParts[4];
            }
        }

        // Direct link using the resource ID
        return `https://portal.azure.com/#@/resource${resourceId}`;
    }

    // Fallback to computer type-based logic
    if (computerType === 'Arc-enabled Server') {
        // Link to Arc-enabled servers (Connected Machines)
        return `https://portal.azure.com/#@/resource/subscriptions/${subId}/resourceGroups/${resGroup}/providers/Microsoft.HybridCompute/machines/${encodeURIComponent(computerName)}/overview`;
    } else if (computerType === 'Azure VM') {
        // Link to regular VMs
        return `https://portal.azure.com/#@/resource/subscriptions/${subId}/resourceGroups/${resGroup}/providers/Microsoft.Compute/virtualMachines/${encodeURIComponent(computerName)}/overview`;
    } else {
        // Fallback to legacy logic for backward compatibility
        const isArcEnabled = hasArcOS(item);

        if (isArcEnabled) {
            return `https://portal.azure.com/#@/resource/subscriptions/${subId}/resourceGroups/${resGroup}/providers/Microsoft.HybridCompute/machines/${encodeURIComponent(computerName)}/overview`;
        } else {
            return `https://portal.azure.com/#@/resource/subscriptions/${subId}/resourceGroups/${resGroup}/providers/Microsoft.Compute/virtualMachines/${encodeURIComponent(computerName)}/overview`;
        }
    }
}

/**
 * Generate computer type badge HTML
 * @param {Object} item - Inventory item
 * @returns {string} HTML string for badge
 */
export function getComputerTypeBadge(item) {
    const computerType = item.computer_type || 'Unknown';
    const resourceId = item.resource_id || '';
    const computerEnvironment = item.computer_environment || 'Unknown';

    switch (computerEnvironment) {
        case 'Azure':
            return `<span class="badge bg-primary text-light" title="Azure Virtual Machine">
                    <i class="fas fa-cloud me-1"></i>Azure VM
                </span>`;
        case 'Non-Azure':
            return `<span class="badge bg-success text-light" title="Arc-enabled Server">
                    <i class="fas fa-server me-1"></i>Non-Azure VM
                </span>`;
        default:
            // Fallback for unknown types
            return `<span class="badge bg-secondary text-light" title="Unknown Computer Type">
                    <i class="fas fa-question me-1"></i>Unknown
                </span>`;
    }
}

/**
 * Escape HTML entities for safe display
 * @param {string} text - Text to escape
 * @returns {string} HTML-escaped text
 */
export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
