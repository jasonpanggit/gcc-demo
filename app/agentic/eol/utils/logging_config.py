# Compatibility shim — many modules import get_logger from utils.logging_config
# but the actual implementation lives in utils.logger
from utils.logger import get_logger, setup_logger

__all__ = ["get_logger", "setup_logger"]
