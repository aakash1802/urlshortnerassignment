# URL Shortener Service

A FastAPI service that shortens URLs, redirects short codes, tracks click analytics, and supports expiration and soft deletion. Storage uses SQLAlchemy (SQLite by default, PostgreSQL by changing `DATABASE_URL`).

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Running

From the project root, either use the launcher script:

```bash
python runproject.py
```

`runproject.py` is a thin launcher that delegates to the existing application entry point and propagates its exit status. Importing it does not start the program (it uses an `if __name__ == "__main__":` guard).

Or run uvicorn directly (the documented entry point in `app/main.py`):

```bash
uvicorn app.main:app
```

The service defaults to `http://localhost:8000`. Interactive API docs are available at `/docs` (FastAPI default). Tables are created automatically on startup.

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Prefix used to build the returned `short_url` (trailing `/` stripped). |
| `DATABASE_URL` | `sqlite:///./shortener.db` | SQLAlchemy database URL. |
| `API_KEY` | unset | If set, stats and delete endpoints require the `X-API-Key` header. |
| `MAX_URL_LENGTH` | `2048` | Maximum accepted length of an original URL (positive integer). |
| `CODE_LENGTH` | `7` | Length of generated base62 short codes (positive integer). |

Invalid (non-integer or non-positive) numeric values raise a `ValueError` at settings load.

## API

| Method | Path | Auth | Success |
|---|---|---|---|
| POST | `/api/urls` | none | `201` with JSON |
| GET | `/api/urls/{short_code}/stats` | API key (if configured) | `200` with JSON |
| DELETE | `/api/urls/{short_code}` | API key (if configured) | `204` no body |
| GET | `/{short_code}` | none | `302` redirect |

### Create a short URL

Body fields: `url` (required), `expires_at` (optional datetime), `ttl_seconds` (optional integer).

```bash
curl -X POST http://localhost:8000/api/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/some/long/path", "ttl_seconds": 3600}'
```

Response:

```json
{
  "short_code": "aB3dE9x",
  "short_url": "http://localhost:8000/aB3dE9x",
  "original_url": "https://example.com/some/long/path",
  "created_at": "2025-01-01T12:00:00Z",
  "expires_at": "2025-01-01T13:00:00Z"
}
```

### Redirect

```bash
curl -i http://localhost:8000/aB3dE9x
```

Returns `302` with a `Location` header and `Cache-Control: no-store`. Each successful redirect atomically increments `click_count` and sets `last_accessed_at`. Unknown or deactivated codes return `404`; expired codes return `410` (no click is counted).

### Stats

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/urls/aB3dE9x/stats
```

Returns `short_code`, `original_url`, `click_count`, `created_at`, `expires_at`, `is_active`, `last_accessed_at`.

### Delete (soft delete)

```bash
curl -X DELETE -H "X-API-Key: $API_KEY" http://localhost:8000/api/urls/aB3dE9x
```

Sets `is_active = false`; the record is kept. The call is idempotent for existing codes.

### Errors

All errors share one JSON shape; stack traces are never returned:

```json
{"error": {"code": "invalid_url", "message": "URL scheme must be http or https"}}
```

| Status | Code | When |
|---|---|---|
| 400 | `invalid_url` / `invalid_expiration` | Bad URL or expiry input |
| 401 | `unauthorized` | `API_KEY` configured, header missing |
| 403 | `forbidden` | Wrong API key |
| 404 | `not_found` | Unknown or deactivated code |
| 410 | `gone` | Code has expired |
| 422 | `validation_error` | Malformed request body (includes `details`) |
| 500 | `internal_server_error` / `code_generation_failed` | Server failure |

## Testing

```bash
pytest
```

Tests (in `tests/`) use isolated databases and cover the API, auth/errors, concurrency and code collisions, end-to-end flows, and the `runproject.py` launcher.

## Assumptions and limitations

- If `API_KEY` is not set, stats and delete endpoints are **open** (intended for local development only). Set it in any shared environment.
- Create and redirect endpoints are unauthenticated and not rate limited.
- Only `http` and `https` URLs with a host are accepted; URLs with whitespace or control characters are rejected.
- Expiry is evaluated lazily at request time; expired records are not purged.
- Short codes are random base62; if collisions persist after a few retries, creation fails with `500 code_generation_failed`.
- Tables are created with `create_all` on startup; there are no migrations.
- `runproject.py` adds no command-line options; it behaves like the existing entry point.
