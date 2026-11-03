"""Core API tests: creation, validation, redirect, clicks, stats, expiry,
deactivation, unknown codes, auth, collisions and error format."""
from __future__ import annotations

import itertools
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import ShortURL
from app.repository import ShortURLRepository

URL = "https://example.com/some/long/path?x=1"
CODE_RE = re.compile(r"^[A-Za-z0-9]{7}$")


# ----------------------------- helpers -----------------------------
def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def assert_error(resp, status=None, code=None):
    """All errors share one JSON structure and never leak stack traces."""
    if status is not None:
        assert resp.status_code == status, resp.text
    assert resp.status_code >= 400
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert isinstance(err["code"], str) and err["code"]
    assert isinstance(err["message"], str) and err["message"]
    assert set(err.keys()) <= {"code", "message", "details"}
    for marker in ("Traceback", 'File "', "sqlalchemy"):
        assert marker not in resp.text
    if code is not None:
        assert err["code"] == code
    return err


def create(client, url=URL, **extra):
    return client.post("/api/urls", json={"url": url, **extra})


def count_records(app) -> int:
    with app.state.session_factory() as session:
        return session.execute(select(func.count()).select_from(ShortURL)).scalar_one()


def make_expired(app, code="ExpiredA"):
    with app.state.session_factory() as session:
        ShortURLRepository(session).create(
            code,
            URL,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
    return code


def stats(client, code, headers):
    return client.get(f"/api/urls/{code}/stats", headers=headers)


def hit(client, code):
    return client.get(f"/{code}", follow_redirects=False)


# ----------------------------- creation -----------------------------
def test_create_success_shape(client):
    resp = create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) >= {"short_code", "short_url", "original_url", "created_at", "expires_at"}
    assert body["original_url"] == URL
    assert body["expires_at"] is None
    parse_ts(body["created_at"])


def test_short_code_is_7_char_base62_and_short_url_prefix(client):
    body = create(client).json()
    assert CODE_RE.match(body["short_code"])
    assert body["short_url"].startswith("http://short.test")
    assert body["short_url"] == f"http://short.test/{body['short_code']}"


def test_same_url_twice_gives_different_codes(client):
    a = create(client).json()
    b = create(client).json()
    assert a["short_code"] != b["short_code"]


# ----------------------------- validation -----------------------------
@pytest.mark.parametrize(
    "bad_url",
    [
        "not a url",
        "just-text",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://",
        "https:///path-only",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_invalid_urls_rejected_and_no_record(client, app, bad_url):
    resp = create(client, url=bad_url)
    assert resp.status_code in (400, 422)
    assert_error(resp)
    assert count_records(app) == 0


def test_missing_url_field_is_consistent_error(client, app):
    resp = client.post("/api/urls", json={})
    assert_error(resp, 422, "validation_error")
    assert count_records(app) == 0


def test_both_expiration_fields_rejected(client, app):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    resp = create(client, expires_at=future, ttl_seconds=60)
    assert resp.status_code in (400, 422)
    assert_error(resp)
    assert count_records(app) == 0


def test_past_expires_at_rejected(client, app):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    resp = create(client, expires_at=past)
    assert resp.status_code in (400, 422)
    assert_error(resp)
    assert count_records(app) == 0


@pytest.mark.parametrize("ttl", [0, -1, -3600])
def test_non_positive_ttl_rejected(client, app, ttl):
    resp = create(client, ttl_seconds=ttl)
    assert resp.status_code in (400, 422)
    assert_error(resp)
    assert count_records(app) == 0


def test_ttl_derives_expires_at(client):
    body = create(client, ttl_seconds=3600).json()
    created = parse_ts(body["created_at"])
    expires = parse_ts(body["expires_at"])
    assert abs((expires - created).total_seconds() - 3600) < 5


def test_future_expires_at_accepted(client):
    future = datetime.now(timezone.utc) + timedelta(days=1)
    resp = create(client, expires_at=future.isoformat())
    assert resp.status_code == 201
    assert abs((parse_ts(resp.json()["expires_at"]) - future).total_seconds()) < 2


# ----------------------------- redirect & clicks -----------------------------
def test_redirect_302_with_location(client):
    code = create(client).json()["short_code"]
    resp = hit(client, code)
    assert resp.status_code == 302
    assert resp.headers["location"] == URL


def test_click_count_after_n_redirects(client, auth_headers):
    code = create(client).json()["short_code"]
    before = stats(client, code, auth_headers).json()
    assert before["click_count"] == 0
    assert before["last_accessed_at"] is None
    for _ in range(5):
        assert hit(client, code).status_code == 302
    after = stats(client, code, auth_headers).json()
    assert after["click_count"] == 5
    assert after["last_accessed_at"] is not None
    parse_ts(after["last_accessed_at"])
    assert set(after) >= {
        "short_code", "original_url", "click_count", "created_at",
        "expires_at", "is_active", "last_accessed_at",
    }
    assert after["is_active"] is True


def test_concurrent_redirects_exact_click_count(client, app, auth_headers):
    code = create(client).json()["short_code"]
    n = 50

    def worker(_):
        # Separate TestClient per thread; no lifespan, tables already exist.
        c = TestClient(app)
        return c.get(f"/{code}", follow_redirects=False).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(worker, range(n)))
    assert statuses == [302] * n
    assert stats(client, code, auth_headers).json()["click_count"] == n


# ----------------------------- unknown / expired -----------------------------
def test_unknown_code_redirect_404(client):
    assert_error(hit(client, "Zzzzzzz"), 404, "not_found")


def test_expired_code_410_and_no_increment(client, app, auth_headers):
    code = make_expired(app)
    assert_error(hit(client, code), 410, "gone")
    assert_error(hit(client, code), 410, "gone")
    body = stats(client, code, auth_headers).json()
    assert body["click_count"] == 0
    assert body["last_accessed_at"] is None


def test_stats_for_expired_code_reflects_state(client, app, auth_headers):
    code = make_expired(app)
    resp = stats(client, code, auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_at"] is not None
    assert parse_ts(body["expires_at"]) < datetime.now(timezone.utc)


def test_stats_unknown_code_404(client, auth_headers):
    assert_error(stats(client, "Nope123", auth_headers), 404, "not_found")


# ----------------------------- deletion -----------------------------
def test_delete_flow(client, auth_headers):
    code = create(client).json()["short_code"]
    assert hit(client, code).status_code == 302

    resp = client.delete(f"/api/urls/{code}", headers=auth_headers)
    assert resp.status_code == 204
    assert resp.content == b""

    assert_error(hit(client, code), 404, "not_found")
    body = stats(client, code, auth_headers).json()
    assert body["click_count"] == 1  # unchanged by the post-delete redirect
    assert body["is_active"] is False

    # Idempotent second delete.
    assert client.delete(f"/api/urls/{code}", headers=auth_headers).status_code == 204


def test_delete_unknown_code_404(client, auth_headers):
    resp = client.delete("/api/urls/Nope123", headers=auth_headers)
    assert_error(resp, 404, "not_found")


# ----------------------------- auth -----------------------------
def test_stats_requires_api_key(client):
    code = create(client).json()["short_code"]
    missing = client.get(f"/api/urls/{code}/stats")
    assert missing.status_code in (401, 403)
    assert_error(missing)
    wrong = client.get(f"/api/urls/{code}/stats", headers={"X-API-Key": "wrong"})
    assert wrong.status_code in (401, 403)
    assert_error(wrong)


def test_delete_requires_api_key_and_makes_no_change(client, auth_headers):
    code = create(client).json()["short_code"]
    missing = client.delete(f"/api/urls/{code}")
    assert missing.status_code in (401, 403)
    assert_error(missing)
    wrong = client.delete(f"/api/urls/{code}", headers={"X-API-Key": "wrong"})
    assert wrong.status_code in (401, 403)
    assert_error(wrong)
    # Still active and redirectable.
    assert hit(client, code).status_code == 302
    assert stats(client, code, auth_headers).json()["is_active"] is True


def test_create_and_redirect_are_public(client):
    # No API key header is sent for either call.
    code = create(client).json()["short_code"]
    assert hit(client, code).status_code == 302


# ----------------------------- collisions -----------------------------
def test_collision_retry_picks_new_code(client, monkeypatch):
    codes = itertools.chain(["AAAAAAA", "AAAAAAA", "BBBBBBB"], itertools.repeat("CCCCCCC"))
    monkeypatch.setattr("app.services.generate_short_code", lambda *a, **k: next(codes))
    first = create(client)
    assert first.status_code == 201
    assert first.json()["short_code"] == "AAAAAAA"
    second = create(client)  # first attempt collides, retry yields BBBBBBB
    assert second.status_code == 201
    assert second.json()["short_code"] == "BBBBBBB"


def test_collision_exhaustion_returns_json_error(client, app, monkeypatch):
    monkeypatch.setattr("app.services.generate_short_code", lambda *a, **k: "DDDDDDD")
    assert create(client).status_code == 201
    resp = create(client)
    assert_error(resp, 500, "code_generation_failed")
    assert count_records(app) == 1


# ----------------------------- error format -----------------------------
def test_framework_errors_share_error_structure(client):
    assert_error(client.get("/api/does/not/exist"), 404)
    assert_error(client.put("/api/urls", json={"url": URL}), 405)
    assert_error(client.post("/api/urls", content="not json", headers={"Content-Type": "application/json"}))
