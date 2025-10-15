"""
Common Utilities and Helper Functions

This module provides core utility functions used throughout the EOL Multi-Agent
application. These functions handle common operations such as:
- Cache key generation
- Software name normalization
- Date/time handling and parsing
- Version information extraction
- Response formatting

All functions in this module are stateless and can be safely imported and used
from any part of the application.

Functions:
    generate_cache_key: Create SHA256-based cache keys
    normalize_software_name: Normalize software names for consistency
    is_cache_expired: Check if cached data has expired
    safe_parse_datetime: Safely parse datetime strings
    extract_version_info: Extract version from software names
    format_eol_date: Format EOL dates for display
    generate_status_cache: Generate cache status snapshots
    create_error_response: Create standardized error responses

Example:
    >>> from utils.helpers import generate_cache_key, normalize_software_name
    >>> key = generate_cache_key("Windows Server", "2019", agent_type="microsoft")
    >>> normalized = normalize_software_name("ms sql server")
"""
from typing import Any, Dict, Optional, Union
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def generate_cache_key(software_name: str, version: Optional[str] = None, agent_type: str = "general", **kwargs) -> str:
    """
    Generate a consistent, optimized cache key for software data.
    
    Creates a deterministic cache key using SHA256 hashing. The key generation
    is optimized for:
    - Performance: SHA256 is faster than MD5 on modern CPUs
    - No collisions: 16-character SHA256 prefix provides sufficient uniqueness
    - Consistency: Same inputs always produce same key
    - Namespace separation: agent_type prevents key conflicts
    
    The cache key includes software name, version, agent type, and any additional
    parameters provided via kwargs. All components are normalized (lowercase,
    trimmed) before hashing to ensure consistency.
    
    Args:
        software_name: Name of the software product. Will be normalized to
                      lowercase and trimmed before hashing.
        version: Optional software version string. If provided, will be
                normalized and included in the cache key.
        agent_type: Type of agent requesting the cache key. Used for namespace
                   separation to prevent key conflicts between different agents
                   (default "general").
        **kwargs: Additional parameters to include in the cache key. These are
                 sorted alphabetically and formatted as "key:value" pairs to
                 ensure consistent ordering.
    
    Returns:
        16-character SHA256 hash string suitable for use as cache key.
        
    Example:
        >>> generate_cache_key("Windows Server", "2019", agent_type="microsoft")
        'a3f5e9c2b1d4a6f8'
        >>> generate_cache_key("Python", "3.11", agent_type="python", arch="x64")
        'b2c4d6e8f1a3c5b7'
    
    Note:
        The 16-character prefix of SHA256 provides >10^19 unique keys, which
        is more than sufficient for application caching needs.
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
    Create standardized error response dictionary.
    
    Converts Python exceptions into a consistent dictionary format suitable
    for API responses, logging, and error tracking. The standardized format
    ensures that all error responses across the application have the same
    structure.
    
    This function is used throughout the application to ensure error responses
    are uniform, making it easier for:
    - Frontend clients to parse and display errors
    - Logging systems to aggregate and analyze errors
    - Monitoring tools to track error patterns
    - Developers to debug issues with full context
    
    Args:
        error: The Python exception that was raised. Any Exception subclass
              is supported.
        context: Additional context string describing where the error occurred.
                Examples: "Software inventory fetch", "EOL data lookup",
                "Cache operation". Helps with debugging and log analysis.
    
    Returns:
        Dictionary containing:
            - error (str): Human-readable error message
            - error_type (str): Python exception class name
            - context (str): Contextual information provided
            - timestamp (str): ISO 8601 timestamp when error was captured
    
    Example:
        >>> try:
        ...     raise ValueError("Invalid software name")
        ... except Exception as e:
        ...     response = create_error_response(e, "Software validation")
        >>> response['error_type']
        'ValueError'
        >>> response['context']
        'Software validation'
    
    Note:
        All timestamps are in UTC to ensure consistency across distributed
        systems and time zones.
    """
    return {
        "error": str(error),
        "error_type": type(error).__name__,
        "context": context,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
