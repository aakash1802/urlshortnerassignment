"""Shared fixtures: isolated temp SQLite DB, app, TestClient and API key.

A file-based SQLite database under pytest's tmp_path is used (instead of
``:memory:``) so concurrent requests from several threads/connections exercise
real database-level atomicity. Nothing external is contacted.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

API_KEY = "test-secret-key"
BASE_URL = "http://short.test"


@pytest.fixture()
def api_key() -> str:
    return API_KEY


@pytest.fixture()
def auth_headers(api_key):
    return {"X-API-Key": api_key}


@pytest.fixture()
def settings(tmp_path) -> Settings:
    db_path = tmp_path / "test.db"
    return Settings(
        base_url=BASE_URL,
        database_url=f"sqlite:///{db_path.as_posix()}",
        api_key=API_KEY,
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    # Context manager runs the lifespan (table creation) and disposes the engine.
    with TestClient(app) as test_client:
        yield test_client
