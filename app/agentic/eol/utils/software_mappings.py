"""
Centralized Software Name Mappings
Single source of truth for software name normalization and pattern matching
"""
from typing import Dict, List, Optional, Tuple


class SoftwareMappings:
    """Centralized software name normalization and mapping"""
    
    # Compound software names (multi-word products that must be kept together)
    COMPOUND_PATTERNS: Dict[str, List[str]] = {
        'Microsoft SQL Server': ['microsoft sql server', 'sql server', 'mssql'],
        'Microsoft Exchange': ['microsoft exchange', 'exchange server'],
        'Visual Studio': ['visual studio', 'vs'],
        'Microsoft Teams': ['microsoft teams', 'teams'],
        'Microsoft Edge': ['microsoft edge', 'edge browser'],
        'Windows Server': ['windows server', 'win server'],
        'Red Hat Enterprise Linux': ['red hat enterprise linux', 'rhel'],
        'Internet Information Services': ['internet information services', 'iis'],
        'SQL Server Management Studio': ['sql server management studio', 'ssms'],
        'Visual Studio Code': ['visual studio code', 'vscode', 'vs code'],
        'Microsoft Office': ['microsoft office', 'ms office'],
        'Microsoft 365': ['microsoft 365', 'm365', 'office 365'],
        'Azure DevOps': ['azure devops', 'ado'],
        'Active Directory': ['active directory', 'ad'],
        'VMware vSphere': ['vmware vsphere', 'vsphere'],
        'Apache HTTP Server': ['apache http server', 'apache', 'httpd'],
        'Oracle Database': ['oracle database', 'oracle db'],
        'PostgreSQL': ['postgresql', 'postgres']
    }
    
    # Simple software patterns (single-word or common abbreviations)
    SIMPLE_PATTERNS: Dict[str, List[str]] = {
        'Python': ['python', 'py'],
        'Java': ['java', 'jdk', 'jre'],
        'PHP': ['php'],
        'Node.js': ['nodejs', 'node.js', 'node'],
        'Ruby': ['ruby', 'rb'],
        'Go': ['golang', 'go'],
        'Rust': ['rust'],
        'Docker': ['docker'],
        'Kubernetes': ['kubernetes', 'k8s'],
        'Redis': ['redis'],
        'MongoDB': ['mongodb', 'mongo'],
        'MySQL': ['mysql'],
        'MariaDB': ['mariadb'],
        'Nginx': ['nginx'],
        'Tomcat': ['tomcat'],
        'Ubuntu': ['ubuntu'],
        'Debian': ['debian'],
        'CentOS': ['centos'],
        'Fedora': ['fedora'],
        'Alpine': ['alpine'],
        'Amazon Linux': ['amazon linux', 'amzn']
    }
    
    # Technology context mappings (for specialized agents)
    TECHNOLOGY_CONTEXTS: Dict[str, List[str]] = {
        'microsoft': ['windows', 'microsoft', 'office', 'sql server', 'iis', 'visual studio', '.net', 'azure'],
        'redhat': ['red hat', 'rhel', 'centos', 'fedora'],
        'ubuntu': ['ubuntu', 'canonical'],
        'python': ['python', 'py', 'pip', 'pypi'],
        'nodejs': ['node', 'nodejs', 'node.js', 'npm'],
        'php': ['php', 'composer'],
        'oracle': ['oracle', 'solaris', 'mysql'],
        'vmware': ['vmware', 'vsphere', 'esxi', 'vcenter'],
        'apache': ['apache', 'httpd', 'tomcat'],
        'database': ['sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'oracle']
    }
    
    @classmethod
    def normalize_software_name(cls, software_name: str) -> str:
        """
        Normalize software name to canonical form
        
        Args:
            software_name: Raw software name
            
        Returns:
            Normalized software name
        """
        if not software_name:
            return software_name
        
        software_lower = software_name.lower().strip()
        
        # Check compound patterns first (higher priority)
        for canonical_name, patterns in cls.COMPOUND_PATTERNS.items():
            for pattern in patterns:
                if pattern in software_lower:
                    return canonical_name
        
        # Check simple patterns
        for canonical_name, patterns in cls.SIMPLE_PATTERNS.items():
            for pattern in patterns:
                if software_lower == pattern or software_lower.startswith(pattern + ' '):
                    return canonical_name
        
        # Return original if no match found
        return software_name
    
    @classmethod
    def extract_software_name_and_version(cls, full_name: str) -> Tuple[str, Optional[str]]:
        """
        Extract software name and version from full string
        
        Args:
            full_name: Full software name potentially containing version
            
        Returns:
            Tuple of (software_name, version)
        """
        if not full_name:
            return full_name, None
        
        # Check compound patterns first
        full_lower = full_name.lower().strip()
        
        for canonical_name, patterns in cls.COMPOUND_PATTERNS.items():
            for pattern in patterns:
                if pattern in full_lower:
                    # Extract version if present
                    remaining = full_lower.replace(pattern, '').strip()
                    if remaining:
                        # Try to parse version
                        import re
                        version_match = re.search(r'(\d+(?:\.\d+)*|\d{4})', remaining)
                        if version_match:
                            return canonical_name, version_match.group(1)
                    return canonical_name, None
        
        # Simple version extraction patterns
        import re
        version_patterns = [
            r'^(.+?)\s+(\d{4})$',  # Year-based: "Software 2019"
            r'^(.+?)\s+(v?(?:\d+\.)+\d+)$',  # Dotted version: "Software 1.2.3"
            r'^(.+?)\s+v?(\d+)$'  # Simple number: "Software 12"
        ]
        
        for pattern in version_patterns:
            match = re.match(pattern, full_name.strip(), re.IGNORECASE)
            if match:
                return match.group(1).strip(), match.group(2)
        
        return full_name, None
    
    @classmethod
    def get_technology_context(cls, software_name: str) -> Optional[str]:
        """
        Determine technology context for agent selection
        
        Args:
            software_name: Software name to analyze
            
        Returns:
            Technology context key or None
        """
        if not software_name:
            return None
        
        software_lower = software_name.lower()
        
        for context, keywords in cls.TECHNOLOGY_CONTEXTS.items():
            if any(keyword in software_lower for keyword in keywords):
                return context
        
        return None
    
    @classmethod
    def get_all_variations(cls, canonical_name: str) -> List[str]:
        """
        Get all known variations of a software name
        
        Args:
            canonical_name: Canonical software name
            
        Returns:
            List of all known variations
        """
        # Check compound patterns
        if canonical_name in cls.COMPOUND_PATTERNS:
            return cls.COMPOUND_PATTERNS[canonical_name]
        
        # Check simple patterns
        if canonical_name in cls.SIMPLE_PATTERNS:
            return cls.SIMPLE_PATTERNS[canonical_name]
        
        return [canonical_name]
    
    @classmethod
    def is_known_software(cls, software_name: str) -> bool:
        """
        Check if software is in known mappings
        
        Args:
            software_name: Software name to check
            
        Returns:
            True if software is known
        """
        if not software_name:
            return False
        
        software_lower = software_name.lower()
        
        # Check compound patterns
        for patterns in cls.COMPOUND_PATTERNS.values():
            if any(pattern in software_lower for pattern in patterns):
                return True
        
        # Check simple patterns
        for patterns in cls.SIMPLE_PATTERNS.values():
            if software_lower in patterns:
                return True
        
        return False


# Convenience functions for backward compatibility
def normalize_software_name(software_name: str) -> str:
    """Normalize software name to canonical form"""
    return SoftwareMappings.normalize_software_name(software_name)


def extract_software_name_and_version(full_name: str) -> Tuple[str, Optional[str]]:
    """Extract software name and version from full string"""
    return SoftwareMappings.extract_software_name_and_version(full_name)


def get_technology_context(software_name: str) -> Optional[str]:
    """Determine technology context for agent selection"""
    return SoftwareMappings.get_technology_context(software_name)
