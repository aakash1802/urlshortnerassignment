# URL Shortener Service

A small REST service built with FastAPI and SQLAlchemy (SQLite by default). It creates short URLs, redirects with HTTP 302, counts clicks atomically, supports optional expiration and soft deletion, and exposes a stats API. Management endpoints are protected by an API key.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows:     .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
API_KEY=change-me BASE_URL=http://localhost:8000 uvicorn app.main:app --reload
```

PowerShell: `$env:API_KEY="change-me"; uvicorn app.main:app --reload`

Tables are created automatically on startup. Interactive docs are at `http://localhost:8000/docs`.

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Prefix used to build `short_url` (trailing slash stripped). |
| `DATABASE_URL` | `sqlite:///./shortener.db` | SQLAlchemy database URL. Change it to use PostgreSQL (with a suitable driver installed). |
| `API_KEY` | unset | Key required in the `X-API-Key` header for stats and delete. |
| `MAX_URL_LENGTH` | `2048` | Maximum accepted length of the original URL. |
| `CODE_LENGTH` | `7` | Length of generated short codes. |

Integer variables must be positive integers. Invalid values raise an error at startup.

**If `API_KEY` is unset or empty, the management endpoints are open.** This is intended for local development only. Always set a key in any shared deployment.

## API

| Method | Path | Auth | Success |
|---|---|---|---|
| POST | `/api/urls` | none | 201 JSON |
| GET | `/{short_code}` | none | 302 redirect |
| GET | `/api/urls/{short_code}/stats` | `X-API-Key` | 200 JSON |
| DELETE | `/api/urls/{short_code}` | `X-API-Key` | 204 |

### Create

```bash
curl -X POST http://localhost:8000/api/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path", "ttl_seconds": 3600}'
```

```json
{"short_code": "aB3xY9z", "short_url": "http://localhost:8000/aB3xY9z",
 "original_url": "https://example.com/some/long/path",
 "created_at": "2026-01-01T12:00:00Z", "expires_at": "2026-01-01T13:00:00Z"}
```

Body fields:
- `url` (required): an http or https URL with a host, no whitespace or control characters, and within the length limit.
- `expires_at` (optional): a future ISO-8601 timestamp. Naive timestamps are treated as UTC.
- `ttl_seconds` (optional): a positive integer.

Send at most one of `expires_at` and `ttl_seconds`. If you send neither, the URL never expires. Submitting the same URL twice creates two independent short codes.

### Redirect

```bash
curl -i http://localhost:8000/aB3xY9z
# HTTP/1.1 302 Found
# location: https://example.com/some/long/path
```

Each successful redirect increments `click_count` with a single atomic `UPDATE` and sets `last_accessed_at`. Responses include `Cache-Control: no-store`.

### Stats

```bash
curl -H "X-API-Key: change-me" http://localhost:8000/api/urls/aB3xY9z/stats
```

```json
{"short_code": "aB3xY9z", "original_url": "https://example.com/some/long/path",
 "click_count": 3, "created_at": "2026-01-01T12:00:00Z",
 "expires_at": "2026-01-01T13:00:00Z", "is_active": true,
 "last_accessed_at": "2026-01-01T12:30:00Z"}
```

Stats stay available for expired and deactivated codes. The response shows their state in `is_active` and `expires_at`.

### Delete (soft deactivate)

```bash
curl -X DELETE -H "X-API-Key: change-me" http://localhost:8000/api/urls/aB3xY9z
```

Sets `is_active=false` and returns 204. Repeating the call on an existing code also returns 204. An unknown code returns 404.

### Errors

All errors use one JSON shape. Stack traces are never returned.

```json
{"error": {"code": "not_found", "message": "Short URL not found"}}
```

Validation failures of the request body may add a `details` list with `field`, `message` and `type`.

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_url` | Bad scheme, missing host, malformed or too long, or contains whitespace. |
| 400 | `invalid_expiration` | Both expiry fields given, `expires_at` in the past, or `ttl_seconds` not positive. |
| 401 | `unauthorized` | Key configured but `X-API-Key` header missing. |
| 403 | `forbidden` | Wrong API key. |
| 404 | `not_found` | Unknown or deactivated code. |
| 410 | `gone` | Expired code on redirect (no click counted). |
| 422 | `validation_error` | Missing `url` or wrong field types. |
| 500 | `internal_server_error` / `code_generation_failed` | Unexpected error, or no unique code found after 5 attempts. |

## Tests

```bash
pytest
```

The tests use isolated temporary databases. They cover creation, validation, redirects, click counting (including concurrent requests), expiration, deactivation, auth and error format.

## Project layout

- `app/main.py`: app factory (`create_app`) and `app` instance.
- `app/routes.py`: HTTP layer.
- `app/services.py`: business logic (validation, code generation, expiry).
- `app/repository.py`: persistence (SQLAlchemy).
- `app/models.py`, `app/schemas.py`, `app/database.py`, `app/config.py`, `app/auth.py`, `app/errors.py`.

## Assumptions and limitations

- Short codes are random base62 (via `secrets`). A unique constraint plus up to 5 retries guards against collisions. Custom aliases are not supported.
- Only http and https URLs are accepted.
- Expiration is set at creation only and cannot be changed. It is evaluated lazily on each request, and there is no cleanup job.
- Deletion is soft only. Deactivated codes return 404 on redirect.
- Redirects use 302 so that every click reaches the service.
- Analytics are limited to a click counter and `last_accessed_at`. There are no per-click logs, referrers or geo data.
- There are no user accounts. A single shared API key protects stats and delete, so the stats endpoint is not public.
- There is no rate limiting, malicious-URL scanning or deduplication.
- Timestamps are stored and returned in UTC.
- Tables are created with `create_all` on startup, and there are no migrations.
- SQLite is the default. Moving to PostgreSQL only needs `DATABASE_URL` and a driver, but this has not been tested here.
- The catch-all `/{short_code}` route is registered after `/api/...` routes.
