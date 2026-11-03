"""Auth on management endpoints, stats edge states and consistent error JSON.

Self-contained: builds its own app on an isolated temporary SQLite file.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import Settings
from app.main import create_app
from app.models import ShortURL, utcnow

KEY = "test-secret-key"
AUTH = {"X-API-Key": KEY}
URL = "https://example.com/some/path"


@pytest.fixture()
def auth_app(tmp_path):
    settings = Settings(
        base_url="http://short.test",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        api_key=KEY,
    )
    return create_app(settings)


@pytest.fixture()
def auth_client(auth_app):
    with TestClient(auth_app) as client:
        yield client


def _create(client, **extra):
    resp = client.post("/api/urls", json={"url": URL, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["short_code"]


def _expire_now(app, code):
    session = app.state.session_factory()
    try:
        session.execute(
            update(ShortURL)
            .where(ShortURL.short_code == code)
            .values(expires_at=utcnow() - timedelta(hours=1))
        )
        session.commit()
    finally:
        session.close()


def assert_error_shape(resp, status):
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert isinstance(err, dict)
    assert {"code", "message"} <= set(err.keys())
    assert set(err.keys()) <= {"code", "message", "details"}
    assert isinstance(err["code"], str) and err["code"]
    assert isinstance(err["message"], str) and err["message"]
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text
    return err


# ----- auth -----
def test_stats_requires_api_key(auth_client):
    code = _create(auth_client)
    assert_error_shape(auth_client.get(f"/api/urls/{code}/stats"), 401)
    assert_error_shape(
        auth_client.get(f"/api/urls/{code}/stats", headers={"X-API-Key": "wrong"}), 403
    )
    ok = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH)
    assert ok.status_code == 200


def test_delete_requires_api_key_and_changes_nothing(auth_client):
    code = _create(auth_client)
    assert_error_shape(auth_client.delete(f"/api/urls/{code}"), 401)
    assert_error_shape(
        auth_client.delete(f"/api/urls/{code}", headers={"X-API-Key": "wrong"}), 403
    )
    stats = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH).json()
    assert stats["is_active"] is True
    redirect = auth_client.get(f"/{code}", follow_redirects=False)
    assert redirect.status_code == 302


def test_create_and_redirect_are_public(auth_client):
    code = _create(auth_client)
    resp = auth_client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == URL


def test_unknown_code_auth_checked_before_lookup(auth_client):
    assert_error_shape(auth_client.delete("/api/urls/Zzzzzzz"), 401)
    assert_error_shape(auth_client.get("/api/urls/Zzzzzzz/stats"), 401)


# ----- stats edge states -----
def test_stats_unknown_code_404(auth_client):
    err = assert_error_shape(auth_client.get("/api/urls/Nope123/stats", headers=AUTH), 404)
    assert err["code"] == "not_found"


def test_stats_for_deactivated_code(auth_client):
    code = _create(auth_client)
    assert auth_client.delete(f"/api/urls/{code}", headers=AUTH).status_code == 204
    resp = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert resp.json()["click_count"] == 0


def test_stats_for_expired_code(auth_app, auth_client):
    code = _create(auth_client, ttl_seconds=3600)
    _expire_now(auth_app, code)
    resp = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_at"] is not None
    assert body["is_active"] is True
    assert body["click_count"] == 0


def test_expired_redirect_410_without_increment(auth_app, auth_client):
    code = _create(auth_client, ttl_seconds=3600)
    _expire_now(auth_app, code)
    err = assert_error_shape(auth_client.get(f"/{code}", follow_redirects=False), 410)
    assert err["code"] == "gone"
    stats = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH).json()
    assert stats["click_count"] == 0
    assert stats["last_accessed_at"] is None


# ----- consistent error structure -----
def test_delete_flow_errors(auth_client):
    code = _create(auth_client)
    assert auth_client.delete(f"/api/urls/{code}", headers=AUTH).status_code == 204
    assert auth_client.delete(f"/api/urls/{code}", headers=AUTH).status_code == 204
    err = assert_error_shape(auth_client.get(f"/{code}", follow_redirects=False), 404)
    assert err["code"] == "not_found"
    stats = auth_client.get(f"/api/urls/{code}/stats", headers=AUTH).json()
    assert stats["click_count"] == 0
    assert_error_shape(auth_client.delete("/api/urls/Unknown", headers=AUTH), 404)


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "not a url"},
        {"url": "ftp://example.com/file"},
        {"url": "javascript:alert(1)"},
        {"url": "http:///nohost"},
        {"url": "https://example.com/" + "a" * 2100},
        {"url": URL, "ttl_seconds": 0},
        {"url": URL, "ttl_seconds": -5},
        {"url": URL, "ttl_seconds": 60, "expires_at": "2999-01-01T00:00:00Z"},
        {"url": URL, "expires_at": "2000-01-01T00:00:00Z"},
        {"url": URL, "expires_at": "garbage"},
        {},
    ],
)
def test_invalid_create_requests_share_error_shape_and_create_nothing(auth_app, auth_client, payload):
    resp = auth_client.post("/api/urls", json=payload)
    assert resp.status_code in (400, 422)
    assert_error_shape(resp, resp.status_code)
    session = auth_app.state.session_factory()
    try:
        assert session.query(ShortURL).count() == 0
    finally:
        session.close()


def test_method_not_allowed_uses_same_error_shape(auth_client):
    code = _create(auth_client)
    resp = auth_client.put(f"/api/urls/{code}", headers=AUTH, json={})
    assert_error_shape(resp, 405)
