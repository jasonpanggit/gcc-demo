"""PostgreSQL domain repositories for the EOL platform.

Phase 8: Consolidated from 22 scattered in-memory repos into 5 domain repos.
All repos accept asyncpg.Pool in constructor, return List[Dict] or Dict.
"""

from utils.repositories.cve_repository import CVERepository
from utils.repositories.inventory_repository import InventoryRepository
from utils.repositories.patch_repository import PatchRepository
from utils.repositories.alert_repository import AlertRepository
from utils.repositories.eol_repository import EOLRepository

__all__ = [
    "CVERepository",
    "InventoryRepository",
    "PatchRepository",
    "AlertRepository",
    "EOLRepository",
]
