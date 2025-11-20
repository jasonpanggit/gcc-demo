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
    "playwright": "Playwright (Bing Search)"
};

// Extended agent display mapping with icons - used for UI display
// Consolidated from agent-communication.js to eliminate duplication
const AGENT_DISPLAY_WITH_ICONS = {
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
    'endoflife': '📅 EndOfLife Agent',
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
    'oracle': '🔴 Oracle Agent',
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

// Function to get display name for an agent (without icon)
function getAgentDisplayName(standardizedName) {
    return AGENT_DISPLAY_MAPPING[standardizedName] || standardizedName;
}

// Function to get display name with icon for an agent
function getAgentDisplayWithIcon(source) {
    const normalized = String(source).toLowerCase();
    
    // First try exact matches
    if (AGENT_DISPLAY_WITH_ICONS[normalized]) {
        return AGENT_DISPLAY_WITH_ICONS[normalized];
    }
    
    // Then try substring matches (order matters - more specific first)
    for (const [key, value] of Object.entries(AGENT_DISPLAY_WITH_ICONS)) {
        if (normalized.includes(key)) {
            return value;
        }
    }
    
    // Default fallback with robot icon
    return `🤖 ${source}`;
}

// Function to get just the icon for an agent (without the name)
function getAgentIcon(source) {
    const fullDisplay = getAgentDisplayWithIcon(source);
    const match = fullDisplay.match(/^([\u{1F300}-\u{1F9FF}])/u);
    return match ? match[1] : '🤖';
}

// Function to get clean agent name (remove emojis and extra spaces)
function getCleanAgentName(agentName) {
    if (!agentName) return '';
    return String(agentName)
        .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')  // Remove emojis
        .replace(/\s+/g, ' ')                     // Normalize spaces
        .trim();
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

// Expose to global scope for easy access
window.AgentConfig = {
    AGENT_DISPLAY_MAPPING,
    AGENT_DISPLAY_WITH_ICONS,
    getAgentDisplayName,
    getAgentDisplayWithIcon,
    getAgentIcon,
    getCleanAgentName,
    getStandardizedAgentName,
    convertAgentStatsForDisplay
};

// Export for use in other modules (if using ES6 modules)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AGENT_DISPLAY_MAPPING,
        AGENT_DISPLAY_WITH_ICONS,
        getAgentDisplayName,
        getAgentDisplayWithIcon,
        getAgentIcon,
        getCleanAgentName,
        getStandardizedAgentName,
        convertAgentStatsForDisplay
    };
}

console.log('✅ Agent configuration loaded successfully');
