"""
Common utilities and helper functions for the EOL Multi-Agent system
"""
from typing import Any, Dict, Optional, Union
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def generate_cache_key(software_name: str, version: Optional[str] = None, agent_type: str = "general", **kwargs) -> str:
    """
    Generate a consistent, optimized cache key for software data
    Uses SHA256 for better performance and no collision risk
    
    Args:
        software_name: Name of the software
        version: Optional software version
        agent_type: Type of agent (for namespace separation)
        **kwargs: Additional parameters to include in cache key
    
    Returns:
        SHA256 hash (16 chars) to use as cache key
    """
    key_components = [agent_type, software_name.lower().strip()]
    if version:
        key_components.append(version.lower().strip())
    
    # Add any additional kwargs in sorted order for consistency
    if kwargs:
        sorted_kwargs = sorted(f"{k}:{v}" for k, v in kwargs.items())
        key_components.extend(sorted_kwargs)
    
    key_string = "|".join(key_components)
    # Use SHA256 and take first 16 chars for better performance
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]


def normalize_software_name(name: str) -> str:
    """
    Normalize software name for consistent matching
    
    Args:
        name: Raw software name
    
    Returns:
        Normalized software name
    """
    if not name:
        return ""
    
    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()
    
    # Common normalizations
    replacements = {
        "microsoft ": "",
        "® ": "",
        "™ ": "",
        " (x64)": "",
        " (x86)": "",
        " 64-bit": "",
        " 32-bit": "",
    }
    
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    
    return normalized


def is_cache_expired(timestamp: str, hours: int = 24) -> bool:
    """
    Check if cached data has expired
    
    Args:
        timestamp: ISO timestamp string (supports various formats)
        hours: Cache duration in hours
    
    Returns:
        True if cache has expired
    """
    try:
        # Handle various timestamp formats safely
        timestamp_clean = timestamp.strip()
        
        # Handle Z suffix (Zulu time)
        if timestamp_clean.endswith('Z'):
            timestamp_clean = timestamp_clean[:-1] + '+00:00'
        
        # Handle double timezone offset issue
        if '+00:00+00:00' in timestamp_clean:
            timestamp_clean = timestamp_clean.replace('+00:00+00:00', '+00:00')
        
        # Handle existing +00:00 followed by Z
        if '+00:00Z' in timestamp_clean:
            timestamp_clean = timestamp_clean.replace('+00:00Z', '+00:00')
        
        cache_time = datetime.fromisoformat(timestamp_clean)
        expiry_time = cache_time + timedelta(hours=hours)
        current_time = datetime.now(timezone.utc)
        return current_time > expiry_time
    except (ValueError, AttributeError) as e:
        # If we can't parse the timestamp, consider it expired
        logger.warning(f"⚠️ Failed to parse timestamp '{timestamp}': {e}. Considering cache expired.")
        return True


def safe_parse_datetime(timestamp: str) -> datetime:
    """
    Safely parse a datetime string handling various formats
    
    Args:
        timestamp: ISO timestamp string (supports various formats)
    
    Returns:
        Parsed datetime object
        
    Raises:
        ValueError: If timestamp cannot be parsed
    """
    # Handle various timestamp formats safely
    timestamp_clean = timestamp.strip()
    
    # Handle Z suffix (Zulu time)
    if timestamp_clean.endswith('Z'):
        timestamp_clean = timestamp_clean[:-1] + '+00:00'
    
    # Handle double timezone offset issue
    if '+00:00+00:00' in timestamp_clean:
        timestamp_clean = timestamp_clean.replace('+00:00+00:00', '+00:00')
    
    # Handle existing +00:00 followed by Z
    if '+00:00Z' in timestamp_clean:
        timestamp_clean = timestamp_clean.replace('+00:00Z', '+00:00')
    
    return datetime.fromisoformat(timestamp_clean)


def extract_version_info(software_name: str, software_version: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Extract and normalize version information from software name and version
    
    Args:
        software_name: Software name (may contain version info)
        software_version: Explicit version string
    
    Returns:
        Dictionary with normalized name and version
    """
    import re
    
    result = {
        "name": software_name,
        "version": software_version
    }
    
    # If no explicit version provided, try to extract from name
    if not software_version and software_name:
        # Common version patterns
        version_patterns = [
            r'\b(\d+\.\d+(?:\.\d+)*)\b',  # Standard version numbers
            r'\bv(\d+\.\d+(?:\.\d+)*)\b',  # Prefixed with 'v'
            r'\b(\d+)\.(\d+)(?:\.(\d+))?\b',  # Multi-part versions
        ]
        
        for pattern in version_patterns:
            match = re.search(pattern, software_name, re.IGNORECASE)
            if match:
                result["version"] = match.group(1)
                # Remove version from name for cleaner name
                result["name"] = re.sub(pattern, '', software_name, flags=re.IGNORECASE).strip()
                break
    
    return result


def format_eol_date(eol_date: Optional[str]) -> str:
    """
    Format EOL date string consistently
    
    Args:
        eol_date: EOL date string in various formats
    
    Returns:
        Formatted date string or 'Unknown' if invalid
    """
    if not eol_date:
        return "Unknown"
    
    try:
        # Try parsing as ISO format first
        if 'T' in eol_date:
            dt = datetime.fromisoformat(eol_date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        else:
            # Try parsing as date only
            dt = datetime.strptime(eol_date, '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        return eol_date  # Return as-is if can't parse


def generate_status_cache() -> Dict[str, Any]:
    """
    Generate cache status information
    
    Returns:
        Dictionary with cache status details
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def create_error_response(error: Exception, context: str = "") -> Dict[str, Any]:
    """
    Create standardized error response
    
    Args:
        error: Exception that occurred
        context: Additional context about where the error occurred
    
    Returns:
        Standardized error dictionary
    """
    return {
        "error": str(error),
        "error_type": type(error).__name__,
        "context": context,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
