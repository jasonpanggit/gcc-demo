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

__all__ = [
    "setup_logger",
    "get_logger", 
    "config",
    "OptimizedConfigManager",
    "generate_cache_key",
    "normalize_software_name",
    "is_cache_expired",
    "safe_parse_datetime",
    "extract_version_info",
    "format_eol_date",
    "generate_status_cache",
    "create_error_response"
]
