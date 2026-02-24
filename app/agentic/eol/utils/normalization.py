"""Centralized normalization utilities for consistent cache keys across all agents."""
import re
from typing import Tuple, Optional


def normalize_os_name_version(os_name: str, version: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Normalize OS name and version for consistent cache lookups and storage.
    
    This ensures that both cache queries and cache writes use the same keys,
    preventing duplicates from being created.
    
    Args:
        os_name: Original OS name (e.g., "Microsoft Windows Server 2025 Datacenter")
        version: Original version (e.g., "10.0")
    
    Returns:
        Tuple of (normalized_name, normalized_version)
        
    Examples:
        - "Microsoft Windows Server 2025 Datacenter", "10.0" -> "windows server", "2025"
        - "Windows Server 2019", None -> "windows server", "2019"
        - "Ubuntu 22.04", "22.04" -> "ubuntu", "22.04"
    """
    if not os_name:
        return "", version
    
    os_lower = os_name.lower().strip()
    
    # Windows Server: Extract year from name, ignore build version
    if "windows server" in os_lower:
        # Extract year (e.g., 2025, 2022, 2019)
        year_match = re.search(r"(20\d{2}|19\d{2})", os_name)
        if year_match:
            return "windows server", year_match.group(1)
        return "windows server", version
    
    # Windows (non-server): Extract version number
    if "windows" in os_lower and "server" not in os_lower:
        # Extract version like "11", "10", "8.1"
        version_match = re.search(r"windows\s+(\d+(?:\.\d+)?)", os_lower)
        if version_match:
            return "windows", version_match.group(1)
        return "windows", version
    
    # Ubuntu: Simplify name
    if "ubuntu" in os_lower:
        return "ubuntu", version
    
    # Red Hat / RHEL
    if "red hat" in os_lower or "rhel" in os_lower:
        return "rhel", version
    
    # CentOS
    if "centos" in os_lower:
        return "centos", version
    
    # Debian
    if "debian" in os_lower:
        return "debian", version
    
    # Default: just lowercase and trim
    return os_lower, version


def normalize_software_name_version(software_name: str, version: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Normalize software name and version for consistent cache lookups and storage.
    
    Args:
        software_name: Original software name
        version: Original version
    
    Returns:
        Tuple of (normalized_name, normalized_version)
    """
    if not software_name:
        return "", version
    
    # For now, simple normalization (can be enhanced as needed)
    normalized_name = software_name.lower().strip()
    normalized_version = version.lower().strip() if version else version
    
    return normalized_name, normalized_version
