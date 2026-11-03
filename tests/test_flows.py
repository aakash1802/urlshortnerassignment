"""Creation, validation, redirect, click counting and concurrency tests."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from app.models import utcnow
from tests.support import (  # noqa: F401  (fixtures are imported)
    BASE_URL,
    GOOD_URL,
    assert_error,
    create,
    parse_ts,
    record_count,
    sc_app,
    sc_client,
    sc_headers,
)


def test_create_success_shape(sc_client):
    resp = create(sc_client)
    assert resp.status_code == 201
    body = resp.json()
    assert {"short_code", "short_url", "original_url", "created_at", "expires_at"} <= set(body)
    assert body["original_url"] == GOOD_URL
    assert body["expires_at"] is None
    assert re.fullmatch(r"[0-9A-Za-z]{7}", body["short_code"])
    assert body["short_url"] == f"{BASE_URL}/{body['short_code']}"


@pytest.mark.parametrize(
    "bad",
    [
        "not a url",
        "example.com",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "http://",
        "https:///path",
        "http://example.com/" + "a" * 2048,
    ],
)
def test_invalid_urls_rejected_without_record(sc_app, sc_client, bad):
    resp = create(sc_client, bad)
    assert_error(resp, (400, 422))
    assert record_count(sc_app) == 0


def test_missing_url_field_is_consistent_error(sc_client):
    resp = sc_client.post("/api/urls", json={})
    assert_error(resp, (400, 422))


def test_expiration_validation(sc_app, sc_client):
    future = (utcnow() + timedelta(hours=1)).isoformat()
    past = (utcnow() - timedelta(hours=1)).isoformat()
    cases = [
        {"expires_at": future, "ttl_seconds": 60},
        {"expires_at": past},
        {"ttl_seconds": 0},
        {"ttl_seconds": -5},
        {"ttl_seconds": "abc"},
        {"expires_at": "not-a-date"},
    ]
    for extra in cases:
        assert_error(create(sc_client, **extra), (400, 422))
    assert record_count(sc_app) == 0


def test_ttl_derives_expires_at(sc_client):
    before = utcnow()
    resp = create(sc_client, ttl_seconds=3600)
    assert resp.status_code == 201
    expires = parse_ts(resp.json()["expires_at"])
    assert abs((expires - (before + timedelta(seconds=3600))).total_seconds()) < 30


def test_explicit_expires_at_accepted(sc_client):
    future = utcnow() + timedelta(days=1)
    resp = create(sc_client, expires_at=future.isoformat())
    assert resp.status_code == 201
    assert abs((parse_ts(resp.json()["expires_at"]) - future).total_seconds()) < 1


def test_same_url_twice_gives_different_codes(sc_client):
    a = create(sc_client).json()["short_code"]
    b = create(sc_client).json()["short_code"]
    assert a != b


def test_redirect_302_and_click_counting(sc_client, sc_headers):
    code = create(sc_client).json()["short_code"]
    stats = sc_client.get(f"/api/urls/{code}/stats", headers=sc_headers).json()
    assert stats["click_count"] == 0 and stats["last_accessed_at"] is None
    n = 4
    for _ in range(n):
        resp = sc_client.get(f"/{code}")
        assert resp.status_code == 302
        assert resp.headers["location"] == GOOD_URL
    stats = sc_client.get(f"/api/urls/{code}/stats", headers=sc_headers).json()
    assert stats["click_count"] == n
    assert stats["last_accessed_at"] is not None
    assert stats["is_active"] is True
    assert stats["original_url"] == GOOD_URL


def test_concurrent_redirects_exact_count(sc_client, sc_headers):
    code = create(sc_client).json()["short_code"]
    total = 50

    def hit(_):
        return sc_client.get(f"/{code}").status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(hit, range(total)))
    ok = statuses.count(302)
    assert ok == total, statuses
    stats = sc_client.get(f"/api/urls/{code}/stats", headers=sc_headers).json()
    assert stats["click_count"] == ok


def test_unknown_code_redirect_404(sc_client):
    assert_error(sc_client.get("/doesNot1"), 404, "not_found")
