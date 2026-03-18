"""Helpers for lazily hydrating repository objects on app.state."""
from __future__ import annotations

from typing import Any, Callable

try:
    from fastapi import FastAPI
    from utils.logging_config import get_logger
    from utils.pg_client import postgres_client
    from utils.repositories.alert_repository import AlertRepository
    from utils.repositories.cve_repository import CVERepository
    from utils.repositories.eol_repository import EOLRepository
    from utils.repositories.inventory_repository import InventoryRepository
    from utils.repositories.patch_repository import PatchRepository
except ModuleNotFoundError:
    from starlette.applications import Starlette as FastAPI  # type: ignore[assignment]
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.pg_client import postgres_client
    from app.agentic.eol.utils.repositories.alert_repository import AlertRepository
    from app.agentic.eol.utils.repositories.cve_repository import CVERepository
    from app.agentic.eol.utils.repositories.eol_repository import EOLRepository
    from app.agentic.eol.utils.repositories.inventory_repository import InventoryRepository
    from app.agentic.eol.utils.repositories.patch_repository import PatchRepository

logger = get_logger(__name__)

_REPOSITORY_FACTORIES: dict[str, Callable[[Any], Any]] = {
    "alert_repo": AlertRepository,
    "cve_repo": CVERepository,
    "eol_repo": EOLRepository,
    "inventory_repo": InventoryRepository,
    "patch_repo": PatchRepository,
}


def get_or_init_repository(app: FastAPI, repository_name: str) -> Any:
    """Return a repository from app.state, creating it from the shared pool if needed."""
    repository = getattr(app.state, repository_name, None)
    if repository is not None:
        return repository

    factory = _REPOSITORY_FACTORIES.get(repository_name)
    if factory is None:
        raise ValueError(f"Unsupported repository name: {repository_name}")

    if postgres_client.pool is None:
        raise RuntimeError(
            f"{repository_name} is unavailable because the PostgreSQL pool is not initialized"
        )

    repository = factory(postgres_client.pool)
    setattr(app.state, repository_name, repository)
    logger.warning(
        "Hydrated missing %s on app.state from the shared PostgreSQL pool",
        repository_name,
    )
    return repository