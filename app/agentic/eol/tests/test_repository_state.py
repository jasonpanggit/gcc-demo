from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI

import utils.repository_state as repository_state


def test_get_or_init_repository_returns_existing_instance():
    app = FastAPI()
    existing_repo = object()
    app.state.inventory_repo = existing_repo

    result = repository_state.get_or_init_repository(app, "inventory_repo")

    assert result is existing_repo


def test_get_or_init_repository_hydrates_missing_repo(monkeypatch):
    app = FastAPI()
    fake_pool = object()
    fake_repo = object()

    monkeypatch.setattr(repository_state, "postgres_client", SimpleNamespace(pool=fake_pool))
    monkeypatch.setitem(
        repository_state._REPOSITORY_FACTORIES,
        "inventory_repo",
        lambda pool: fake_repo if pool is fake_pool else None,
    )

    result = repository_state.get_or_init_repository(app, "inventory_repo")

    assert result is fake_repo
    assert app.state.inventory_repo is fake_repo


def test_get_or_init_repository_requires_initialized_pool(monkeypatch):
    app = FastAPI()

    monkeypatch.setattr(repository_state, "postgres_client", SimpleNamespace(pool=None))

    try:
        repository_state.get_or_init_repository(app, "inventory_repo")
    except RuntimeError as exc:
        assert "PostgreSQL pool is not initialized" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when PostgreSQL pool is missing")