"""Concurrent redirect counting and short-code collision retry behavior."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.models import ShortURL
from app.services import UrlService

KEY = "concurrency-key"
AUTH = {"X-API-Key": KEY}
URL = "https://example.com/target"


@pytest.fixture()
def conc_settings(tmp_path):
    return Settings(
        base_url="http://short.test",
        database_url=f"sqlite:///{tmp_path / 'conc.db'}",
        api_key=KEY,
    )


@pytest.fixture()
def conc_app(conc_settings):
    return create_app(conc_settings)


@pytest.fixture()
def conc_client(conc_app):
    with TestClient(conc_app) as client:
        yield client


def test_concurrent_redirects_have_exact_click_count(conc_client):
    code = conc_client.post("/api/urls", json={"url": URL}).json()["short_code"]
    n = 50

    def hit(_):
        return conc_client.get(f"/{code}", follow_redirects=False).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(hit, range(n)))

    successes = sum(1 for s in statuses if s == 302)
    assert successes == n
    stats = conc_client.get(f"/api/urls/{code}/stats", headers=AUTH).json()
    assert stats["click_count"] == successes
    assert stats["last_accessed_at"] is not None


def _service(app, generator):
    session = app.state.session_factory()
    return session, UrlService(session, app.state.settings, code_generator=generator)


def test_collision_is_retried_with_new_code(conc_app, conc_client):
    first = conc_client.post("/api/urls", json={"url": URL}).json()["short_code"]
    codes = iter([first, first, "Fresh12"])
    session, service = _service(conc_app, lambda length: next(codes))
    try:
        record = service.create("https://example.com/other", None, None)
        assert record.short_code == "Fresh12"
        assert session.query(ShortURL).count() == 2
    finally:
        session.close()


def test_collision_exhaustion_raises_error_and_creates_nothing(conc_app, conc_client):
    first = conc_client.post("/api/urls", json={"url": URL}).json()["short_code"]
    session, service = _service(conc_app, lambda length: first)
    try:
        with pytest.raises(AppError) as info:
            service.create("https://example.com/other", None, None)
        assert info.value.status_code == 500
        assert session.query(ShortURL).count() == 1
    finally:
        session.close()


def test_api_collision_exhaustion_returns_consistent_error(conc_client, monkeypatch):
    first = conc_client.post("/api/urls", json={"url": URL}).json()["short_code"]
    monkeypatch.setattr("app.services.generate_short_code", lambda length=7: first)
    resp = conc_client.post("/api/urls", json={"url": "https://example.com/x"})
    assert resp.status_code == 500
    body = resp.json()
    assert set(body) == {"error"}
    assert {"code", "message"} <= set(body["error"])
    assert "Traceback" not in resp.text


def test_same_url_twice_yields_distinct_codes_base62(conc_client):
    a = conc_client.post("/api/urls", json={"url": URL}).json()
    b = conc_client.post("/api/urls", json={"url": URL}).json()
    assert a["short_code"] != b["short_code"]
    for item in (a, b):
        assert len(item["short_code"]) == 7
        assert item["short_code"].isalnum() and item["short_code"].isascii()
        assert item["short_url"] == f"http://short.test/{item['short_code']}"
