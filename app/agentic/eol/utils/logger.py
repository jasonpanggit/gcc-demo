"""
Centralized logging configuration for the EOL Multi-Agent App

Supports both standard logging and structured logging with correlation ID.
"""
import logging
import os
import sys
from typing import Any, Dict, Optional

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

try:
    from utils.correlation_id import get_correlation_id
    CORRELATION_ID_AVAILABLE = True
except ImportError:
    CORRELATION_ID_AVAILABLE = False


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages"""
    
    # Define colors
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        # Add color to the log level
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        # Format the message
        return super().format(record)


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Set up a logger with consistent formatting optimized for Azure App Service
    
    Args:
        name: Logger name (typically __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding multiple handlers if logger already exists
    if logger.handlers:
        return logger
    
    # Set log level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # Detect if running in Azure App Service
    is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
    is_container_app = os.environ.get('CONTAINER_APP_NAME') is not None

    # Determine output stream and formatter. Azure environments prefer stderr with
    # plain formatting so logs show up reliably in platform viewers. Container Apps
    # behaves similarly, so apply the same settings there.
    use_plain_formatter = is_azure_app_service or is_container_app
    
    if use_plain_formatter:
        stream = sys.stderr
        handler = logging.StreamHandler(stream)
        formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        stream = sys.stdout
        handler = logging.StreamHandler(stream)
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)
    
    # Ensure the root logger is configured so platform log collectors always capture
    # the output. Avoid duplicating handlers if they already exist.
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        for existing_handler in root_logger.handlers:
            existing_handler.setLevel(numeric_level)
            if use_plain_formatter:
                existing_handler.setFormatter(formatter)
    root_logger.setLevel(numeric_level)

    # Quiet overly chatty dependency loggers unless explicitly overridden.
    noisy_loggers = {
        "openai": os.getenv("OPENAI_LOG_LEVEL", "WARNING"),
        "openai._base_client": os.getenv("OPENAI_BASE_CLIENT_LOG_LEVEL", "WARNING"),
        "httpx": os.getenv("HTTPX_LOG_LEVEL", "WARNING"),
        "httpcore": os.getenv("HTTPCORE_LOG_LEVEL", "WARNING"),
        "httpcore.connection": os.getenv("HTTPCORE_CONNECTION_LOG_LEVEL", "WARNING"),
        "httpcore.http11": os.getenv("HTTPCORE_HTTP11_LOG_LEVEL", "WARNING"),
    }
    for noisy_name, override_level in noisy_loggers.items():
        target_logger = logging.getLogger(noisy_name)
        target_logger.setLevel(getattr(logging, override_level.upper(), logging.WARNING))
        # Keep propagation so important messages still flow to the root handler.

    # Configure the module logger to propagate to root and avoid duplicate handlers.
    logger.handlers.clear()
    logger.setLevel(numeric_level)
    logger.propagate = True

    # Ensure our application loggers are set to the configured level so INFO writes appear.
    for app_logger_name in (
        "agents.mcp_orchestrator",
        "utils.azure_mcp_client",
        "api.azure_mcp",
    ):
        logging.getLogger(app_logger_name).setLevel(numeric_level)
    
    return logger


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Get or create a logger instance

    Args:
        name: Logger name
        level: Optional log level override

    Returns:
        Logger instance
    """
    if level:
        return setup_logger(name, level)
    return logging.getLogger(name)


# ============================================================================
# Structured Logging Support (Phase 2, Day 5)
# ============================================================================

def add_correlation_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processor to add correlation ID to structured logs.

    Args:
        logger: The logger instance
        method_name: The logging method name
        event_dict: The event dictionary

    Returns:
        Modified event dictionary with correlation_id
    """
    if CORRELATION_ID_AVAILABLE:
        cid = get_correlation_id()
        if cid:
            event_dict["correlation_id"] = cid
    return event_dict


def configure_structlog(level: str = "INFO") -> None:
    """
    Configure structlog with standard processors and correlation ID support.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    if not STRUCTLOG_AVAILABLE:
        raise ImportError("structlog is not installed. Install with: pip install structlog")

    # Determine if running in Azure environment
    is_azure_app_service = os.environ.get('WEBSITE_SITE_NAME') is not None
    is_container_app = os.environ.get('CONTAINER_APP_NAME') is not None
    use_json_output = is_azure_app_service or is_container_app

    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,  # Add correlation ID to all logs
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if use_json_output:
        # Use JSON renderer for Azure environments (easier parsing)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Use colored console renderer for local development
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_structured_logger(name: str, **initial_values: Any) -> Any:
    """
    Get a structured logger with correlation ID support.

    Args:
        name: Logger name (typically __name__)
        **initial_values: Initial context values to bind to the logger

    Returns:
        Structured logger instance (structlog.BoundLogger)

    Example:
        >>> logger = get_structured_logger(__name__, component="orchestrator")
        >>> logger.info("processing_request", query="eol data", agent_count=3)
        # Output: {"event": "processing_request", "query": "eol data",
        #          "agent_count": 3, "correlation_id": "...", "component": "orchestrator"}
    """
    if not STRUCTLOG_AVAILABLE:
        raise ImportError("structlog is not installed. Install with: pip install structlog")

    logger = structlog.get_logger(name)

    # Bind initial values if provided
    if initial_values:
        logger = logger.bind(**initial_values)

    return logger


def log_with_context(
    logger: Any,
    level: str,
    message: str,
    **context: Any
) -> None:
    """
    Log a message with additional context using structured logging.

    Args:
        logger: Structured logger instance
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **context: Additional context key-value pairs

    Example:
        >>> logger = get_structured_logger(__name__)
        >>> log_with_context(logger, "info", "agent_completed",
        ...                  agent="microsoft", duration_ms=450)
    """
    log_method = getattr(logger, level.lower())
    log_method(message, **context)


def is_structlog_configured() -> bool:
    """
    Check if structlog is configured.

    Returns:
        True if structlog is available and configured, False otherwise
    """
    return STRUCTLOG_AVAILABLE and structlog.is_configured()
