// Centralized Agent Configuration
// This file contains shared agent configuration that can be used across multiple templates

// Agent display name mapping - standardized agent names to user-friendly display names
// This should match the AGENT_DISPLAY_MAPPING in agent_config.py
const AGENT_DISPLAY_MAPPING = {
    "apache": "Apache",
    "endoflife": "End of Life",
    "inventory": "Inventory",
    "python": "Python",
    "nodejs": "NodeJS",
    "redhat": "RedHat", 
    "oracle": "Oracle",
    "software_inventory": "Software Inventory",
    "ubuntu": "Ubuntu",
    "php": "PHP",
    "vmware": "VMware",
    "openai": "OpenAI",
    "os_inventory": "OS Inventory",
    "azure_ai": "Azure AI", 
    "postgresql": "PostgreSQL",
    "microsoft": "Microsoft",
    "orchestrator": "Orchestrator",
    "websurfer": "WebSurfer"
};

// Function to get display name for an agent
function getAgentDisplayName(standardizedName) {
    return AGENT_DISPLAY_MAPPING[standardizedName] || standardizedName;
}

// Function to get standardized name from display name (reverse lookup)
function getStandardizedAgentName(displayName) {
    for (const [standardized, display] of Object.entries(AGENT_DISPLAY_MAPPING)) {
        if (display === displayName) {
            return standardized;
        }
    }
    return displayName.toLowerCase().replace(/\s+/g, '_');
}

// Function to convert agent stats for display (used in cache management)
function convertAgentStatsForDisplay(agentStats) {
    const displayStats = {};
    for (const [agentName, stats] of Object.entries(agentStats)) {
        const displayName = getAgentDisplayName(agentName);
        displayStats[displayName] = stats;
    }
    return displayStats;
}

// Export for use in other modules (if using ES6 modules)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AGENT_DISPLAY_MAPPING,
        getAgentDisplayName,
        getStandardizedAgentName,
        convertAgentStatsForDisplay
    };
}
