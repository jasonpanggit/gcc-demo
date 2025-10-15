"""
Utility package for the EOL Multi-Agent App - Optimized
"""
from .logger import setup_logger, get_logger
from .config import config, ConfigManager
from .helpers import (
    generate_cache_key,
    normalize_software_name,
    is_cache_expired,
    safe_parse_datetime,
    extract_version_info,
    format_eol_date,
    generate_status_cache,
    create_error_response
)
from .query_patterns import (
    QueryPatterns,
    matches_eol_pattern,
    matches_approaching_eol_pattern,
    matches_inventory_pattern,
    analyze_query_intent
)
from .software_mappings import (
    SoftwareMappings,
    extract_software_name_and_version,
    get_technology_context
)
from .error_handlers import (
    handle_api_errors,
    handle_agent_errors,
    retry_on_failure
)

__all__ = [
    "setup_logger",
    "get_logger", 
    "config",
    "ConfigManager",
    "generate_cache_key",
    "normalize_software_name",
    "is_cache_expired",
    "safe_parse_datetime",
    "extract_version_info",
    "format_eol_date",
    "generate_status_cache",
    "create_error_response",
    "QueryPatterns",
    "matches_eol_pattern",
    "matches_approaching_eol_pattern",
    "matches_inventory_pattern",
    "analyze_query_intent",
    "SoftwareMappings",
    "extract_software_name_and_version",
    "get_technology_context",
    "handle_api_errors",
    "handle_agent_errors",
    "retry_on_failure"
]
