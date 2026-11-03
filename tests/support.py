"""Shared fixtures/helpers for the extended test suite (isolated temp SQLite DB)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import ShortURL

API_KEY = "test-secret-key"
BASE_URL = "http://short.test"
GOOD_URL = "https://example.com/some/long/path?q=1"


@pytest.fixture()
def sc_app(tmp_path):
    settings = Settings(
        base_url=BASE_URL,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_key=API_KEY,
    )
    return create_app(settings)


@pytest.fixture()
def sc_client(sc_app):
    with TestClient(sc_app, follow_redirects=False) as client:
        yield client


@pytest.fixture()
def sc_headers():
    return {"X-API-Key": API_KEY}


def create(client, url=GOOD_URL, **extra):
    return client.post("/api/urls", json={"url": url, **extra})


def record_count(app) -> int:
    session = app.state.session_factory()
    try:
        return session.execute(select(func.count()).select_from(ShortURL)).scalar_one()
    finally:
        session.close()


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def assert_error(resp, statuses, code=None):
    """Assert a response is an error with the shared JSON structure."""
    statuses = (statuses,) if isinstance(statuses, int) else tuple(statuses)
    assert resp.status_code in statuses, (resp.status_code, resp.text)
    body = resp.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert isinstance(err["code"], str) and err["code"]
    assert isinstance(err["message"], str) and err["message"]
    assert set(err.keys()) <= {"code", "message", "details"}
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text
    if code:
        assert err["code"] == code
    return err
