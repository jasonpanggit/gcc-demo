"""
Centralized logging configuration for the EOL Multi-Agent App
"""
import logging
import os
import sys
from typing import Optional


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
