/**
 * EOL Shared Utilities
 * Common functions used across multiple templates for software EOL analysis
 */

window.eolUtils = window.eolUtils || {};

(function() {
    'use strict';

    /**
     * Clean software name by removing noise patterns
     * Removes Arc-enabled markers, architecture info, etc.
     * @param {string} name - Software name to clean
     * @returns {string} Cleaned software name
     */
    eolUtils.cleanSoftwareName = function(name) {
        if (!name) return name;

        // Remove common noise patterns that might interfere with EOL lookup
        let cleaned = name
            .replace(/\s*\(Arc-enabled\)/gi, '')  // Remove Arc-enabled markers
            .replace(/\s*\(x64\)/gi, '')          // Remove architecture markers
            .replace(/\s*\(x86\)/gi, '')
            .replace(/\s*64-bit/gi, '')
            .replace(/\s*32-bit/gi, '')
            .replace(/\s*\([^)]*bit[^)]*\)/gi, '') // Remove any parenthetical bit references
            .replace(/\s+/g, ' ')                  // Normalize whitespace
            .trim();

        return cleaned;
    };

    /**
     * Extract version information from software name
     * @param {string} name - Software name potentially containing version
     * @returns {Object} Object with {name, version} properties
     */
    eolUtils.parseVersionFromName = function(name) {
        if (!name) return { name: name, version: null };

        // Common version patterns to extract
        const versionPatterns = [
            // Standard version patterns: "Software 2019", "Windows Server 2016"
            /^(.+?)\s+(\d{4})$/i,
            // Version with dots: "Software 1.2.3"
            /^(.+?)\s+(v?(?:\d+\.)+\d+(?:\.\d+)*)$/i,
            // Version with single number: "Software 12"
            /^(.+?)\s+v?(\d+)$/i,
            // Ubuntu-style: "Ubuntu 20.04", "RHEL 8.5"
            /^(.+?)\s+(\d+\.\d+(?:\.\d+)?)$/i,
        ];

        for (const pattern of versionPatterns) {
            const match = name.match(pattern);
            if (match) {
                const baseName = match[1].trim();
                const version = match[2].trim();

                // Validate that we're not accidentally parsing a valid part of the name
                if (!eolUtils.isCommonSoftwareWord(version)) {
                    return {
                        name: baseName,
                        version: version
                    };
                }
            }
        }

        return { name: name, version: null };
    };

    /**
     * Check if word is a common software term (not a version)
     * @param {string} word - Word to check
     * @returns {boolean} True if common software word
     */
    eolUtils.isCommonSoftwareWord = function(word) {
        if (!word || typeof word !== 'string') {
            return false;
        }
        const commonWords = [
            'server', 'client', 'pro', 'professional', 'enterprise', 'standard',
            'express', 'developer', 'runtime', 'framework', 'sdk', 'tools',
            'service', 'pack', 'update', 'hotfix', 'patch'
        ];
        return commonWords.includes(word.toLowerCase());
    };

    /**
     * Calculate confidence level for EOL search
     * @param {string} name - Software name
     * @param {string} version - Software version (optional)
     * @returns {number} Confidence level between 0 and 1
     */
    eolUtils.calculateSearchConfidence = function(name, version) {
        let confidence = 0.5; // Base confidence

        // Increase confidence for well-known software patterns
        const knownPatterns = [
            /windows.*server/i, /microsoft.*office/i, /visual.*studio/i,
            /red.*hat/i, /rhel/i, /ubuntu/i, /centos/i,
            /sql.*server/i, /\.net/i, /iis/i
        ];

        if (knownPatterns.some(pattern => pattern.test(name))) {
            confidence += 0.3;
        }

        // Increase confidence if version is provided
        if (version) {
            confidence += 0.2;

            // Boost for year-based versions (common for enterprise software)
            if (/^\d{4}$/.test(version)) {
                confidence += 0.1;
            }
        }

        return Math.min(confidence, 1.0);
    };

    /**
     * Determine which agents would be selected based on software name
     * @param {string} softwareName - Software name to analyze
     * @returns {Array} Array of agent objects with name, type, icon, reason
     */
    eolUtils.getSelectedAgents = function(softwareName) {
        if (!softwareName || typeof softwareName !== 'string') {
            return [];
        }

        const softwareNameLower = softwareName.toLowerCase();
        const selectedAgents = [];

        // Microsoft products
        const msKeywords = ['windows', 'microsoft', 'office', 'sql server', 'iis', 'visual studio', '.net'];
        if (msKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'Microsoft Agent',
                type: 'microsoft',
                icon: 'fab fa-microsoft',
                reason: 'Microsoft product detected'
            });
        }

        // Red Hat products
        const rhKeywords = ['red hat', 'rhel', 'centos', 'fedora'];
        if (rhKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'Red Hat Agent',
                type: 'redhat',
                icon: 'fab fa-redhat',
                reason: 'Red Hat product detected'
            });
        }

        // Ubuntu products
        const ubuntuKeywords = ['ubuntu', 'canonical'];
        if (ubuntuKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'Ubuntu Agent',
                type: 'ubuntu',
                icon: 'fab fa-ubuntu',
                reason: 'Ubuntu product detected'
            });
        }

        // Python
        const pythonKeywords = ['python', 'py'];
        if (pythonKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'Python Agent',
                type: 'python',
                icon: 'fab fa-python',
                reason: 'Python detected'
            });
        }

        // Node.js
        const nodeKeywords = ['node', 'nodejs', 'node.js'];
        if (nodeKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'Node.js Agent',
                type: 'nodejs',
                icon: 'fab fa-node-js',
                reason: 'Node.js detected'
            });
        }

        // PHP
        const phpKeywords = ['php'];
        if (phpKeywords.some(keyword => softwareNameLower.includes(keyword))) {
            selectedAgents.push({
                name: 'PHP Agent',
                type: 'php',
                icon: 'fab fa-php',
                reason: 'PHP detected'
            });
        }

        // Always include endoflife.date as fallback
        selectedAgents.push({
            name: 'EndOfLife.date Agent',
            type: 'endoflife',
            icon: 'fas fa-calendar-times',
            reason: 'General EOL database'
        });

        return selectedAgents;
    };

    /**
     * Format date consistently across the application
     * @param {string} dateString - Date string to format
     * @returns {string} Formatted date or 'N/A'
     */
    eolUtils.formatDate = function(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        } catch (e) {
            return dateString;
        }
    };

    /**
     * Calculate days until EOL
     * @param {string} eolDate - EOL date string
     * @returns {number|null} Days until EOL or null if invalid
     */
    eolUtils.daysUntilEOL = function(eolDate) {
        if (!eolDate) return null;
        try {
            const eol = new Date(eolDate);
            const now = new Date();
            const diffTime = eol - now;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            return diffDays;
        } catch (e) {
            return null;
        }
    };

    /**
     * Determine risk level based on days until EOL
     * @param {number} daysUntilEOL - Days until EOL
     * @returns {string} Risk level: critical, high, medium, low, unknown
     */
    eolUtils.getRiskLevel = function(daysUntilEOL) {
        if (daysUntilEOL === null || daysUntilEOL === undefined) {
            return 'unknown';
        }
        
        if (daysUntilEOL < 0) {
            return 'critical';
        } else if (daysUntilEOL <= 90) {
            return 'critical';
        } else if (daysUntilEOL <= 365) {
            return 'high';
        } else if (daysUntilEOL <= 730) {
            return 'medium';
        } else {
            return 'low';
        }
    };

    /**
     * Get badge class based on risk level
     * @param {string} riskLevel - Risk level
     * @returns {string} Bootstrap badge class
     */
    eolUtils.getRiskBadgeClass = function(riskLevel) {
        const riskClasses = {
            'critical': 'bg-danger',
            'high': 'bg-warning text-dark',
            'medium': 'bg-info text-dark',
            'low': 'bg-success',
            'unknown': 'bg-secondary'
        };
        return riskClasses[riskLevel] || 'bg-secondary';
    };

    // Expose to global scope for backward compatibility
    window.cleanSoftwareName = eolUtils.cleanSoftwareName;
    window.parseVersionFromName = eolUtils.parseVersionFromName;
    window.calculateSearchConfidence = eolUtils.calculateSearchConfidence;
    window.getSelectedAgents = eolUtils.getSelectedAgents;

    console.log('✅ EOL Utilities loaded successfully');
})();
