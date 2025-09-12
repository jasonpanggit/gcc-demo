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
    
    if is_azure_app_service:
        # Azure App Service configuration
        # Use stderr for better visibility in App Service logs
        handler = logging.StreamHandler(sys.stderr)
        
        # Simple formatter without colors for Azure (colors can interfere with log parsing)
        formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # Local development configuration with colors
        handler = logging.StreamHandler(sys.stdout)
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)
    
    # For Azure App Service, configure only root logger to avoid duplication
    if is_azure_app_service:
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            root_logger.setLevel(numeric_level)
            root_handler = logging.StreamHandler(sys.stderr)
            root_handler.setFormatter(formatter)
            root_logger.addHandler(root_handler)
        
        # Set level and enable propagation (don't add handler to specific logger)
        logger.setLevel(numeric_level)
        logger.propagate = True
    else:
        # Local development: add handler to specific logger and disable propagation
        logger.addHandler(handler)
        logger.propagate = False
    
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
