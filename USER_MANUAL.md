# URL Shortener — Assessor User Manual

This manual is for someone evaluating the project. It covers what the service does, how to install it, how to run it, and how to exercise every feature and judge the result.

The product is a local HTTP API. There is no separate website or desktop window. You talk to it with a browser (interactive docs), `curl`, or the automated test suite.

---

## 1. What you are assessing

The service shortens a long `http` or `https` URL into a random 7-character code, redirects visitors who open that code, counts clicks, and supports optional expiry and soft deletion.

| Capability | What it means in practice |
|---|---|
| Create | `POST /api/urls` stores the original URL and returns a short link. |
| Redirect | `GET /{short_code}` answers `302` and sends the browser to the original URL. |
| Analytics | Each successful redirect increments `click_count` and sets `last_accessed_at`. |
| Expiry | A link can expire at an absolute time or after a number of seconds. Expired links return `410` and do not count a click. |
| Soft delete | `DELETE /api/urls/{short_code}` marks the link inactive. The row stays in the database. A later visit returns `404`. |
| Protection | If you set `API_KEY`, statistics and delete require the header `X-API-Key`. Create and redirect stay public. |

Data is stored in a SQLite file named `shortener.db` in the project folder unless you point `DATABASE_URL` somewhere else. Tables are created automatically the first time the server starts. There is no migration tool and no admin UI.

Default address: `http://127.0.0.1:8000`

---

## 2. What you need before you start

| Requirement | Notes |
|---|---|
| Python | 3.10 or newer. This workspace was developed with Python 3.12. |
| pip | Comes with a normal Python install. |
| A terminal | PowerShell on Windows, or a shell on macOS/Linux. |
| curl | Used in the walkthrough. On Windows 10 and later, `curl.exe` is already installed. |
| Network | Nothing external is required. The server binds to your own machine. |
| Optional | pytest is installed with the project dependencies and is how you run the automated checks. |

You do not need PostgreSQL, Docker, Node.js, or an API key for the basic walkthrough.

Confirm Python before you install anything:

```powershell
python --version
```

If that command is missing or reports a version older than 3.10, install a current Python from [python.org](https://www.python.org/downloads/) and tick **Add python.exe to PATH** during setup. Then open a new terminal and check the version again.

---

## 3. Install

All commands below assume you are in the project root (the folder that contains `runproject.py`, `requirements.txt`, and the `app` directory).

```powershell
cd C:\Users\Avita\PycharmProjects\urlshortnerassignment
```

### 3.1 Create a virtual environment

A virtual environment keeps this project’s packages separate from the rest of the machine.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activate script, run this once in that window and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

The prompt should gain a `(.venv)` prefix. If it does not, the later `pip` and `python` commands may install into the wrong Python.

### 3.2 Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Role |
|---|---|
| FastAPI | HTTP API and the `/docs` page |
| Uvicorn | Server that actually listens on port 8000 |
| SQLAlchemy | Database access |
| Pydantic | Request and response shapes |
| pytest | Automated tests |
| httpx | HTTP client used by the tests |

Confirm the install:

```powershell
python -c "import fastapi, uvicorn, sqlalchemy, pydantic; print('ok')"
```

Expected output: `ok`

---

## 4. Configuration

Settings are read from environment variables **when the process starts**. Change them in the same terminal, before you launch the server. Changing them after the server is running has no effect until you stop it and start it again.

| Variable | Default | What an assessor should know |
|---|---|---|
| `BASE_URL` | `http://localhost:8000` | Prefix used to build the `short_url` field in create responses. A trailing slash is removed. This does not change the port the server listens on. |
| `DATABASE_URL` | `sqlite:///./shortener.db` | SQLAlchemy URL. The default file appears in the project root after the first successful start. |
| `API_KEY` | unset | When unset, stats and delete are open. Set this before you assess authentication. |
| `MAX_URL_LENGTH` | `2048` | Longest accepted original URL. Must be a positive integer. |
| `CODE_LENGTH` | `7` | Length of generated short codes (letters and digits). Must be a positive integer. |

Invalid values for `MAX_URL_LENGTH` or `CODE_LENGTH` (blank is fine; `0`, negative numbers, and non-integers are not) stop the process at startup with a `ValueError`.

### Recommended settings for an assessment

Use a dedicated database file and a known API key so you can tell protected calls from public ones.

**PowerShell:**

```powershell
$env:API_KEY = "assess-secret"
$env:BASE_URL = "http://127.0.0.1:8000"
$env:DATABASE_URL = "sqlite:///./assessment.db"
```

**Command Prompt:**

```bat
set API_KEY=assess-secret
set BASE_URL=http://127.0.0.1:8000
set DATABASE_URL=sqlite:///./assessment.db
```

**macOS / Linux:**

```bash
export API_KEY=assess-secret
export BASE_URL=http://127.0.0.1:8000
export DATABASE_URL=sqlite:///./assessment.db
```

Leave `API_KEY` unset only if you specifically want to confirm that stats and delete are open in local development. That open behavior is intentional. It is not suitable for a shared machine.

`runproject.py` always listens on `127.0.0.1` port `8000`. It accepts no command-line arguments. Keep `BASE_URL` on port 8000 unless you start Uvicorn yourself on another port (see section 5.2).

---

## 5. Start and stop the server

The virtual environment must still be active, and you must still be in the project root.

### 5.1 Normal start

```powershell
python runproject.py
```

What you should see:

- The process stays running. It does not return to the prompt.
- Uvicorn reports that it is serving the application.
- The listening address is `http://127.0.0.1:8000`.

`runproject.py` only starts Uvicorn against the existing application (`app.main:app`). Importing the file does not start a server. It adds no extra options.

### 5.2 Alternate start

This is the same application without the launcher script. Use it if you need a different port. If you change the port, set `BASE_URL` to match before starting, otherwise returned short links will point at the wrong place.

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5.3 Confirm it is up

Open a **second** terminal, activate `.venv` again if you will run Python there, and run:

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/docs
```

Expected status: `200`

Then open this address in a browser:

`http://127.0.0.1:8000/docs`

You should see a page titled **URL Shortener** with four operations: create, stats, delete, and redirect. That page is generated by FastAPI. A second reference page is at `http://127.0.0.1:8000/redoc`. The raw specification is at `http://127.0.0.1:8000/openapi.json`.

### 5.4 Stop

In the terminal where the server is running, press `Ctrl+C`. Wait until the prompt returns. The SQLite file remains on disk, so links you created are still there the next time you start.

### 5.5 Reset the data

Stop the server first. Then delete the database file you are using (`shortener.db` by default, or `assessment.db` if you set `DATABASE_URL` as in section 4). Start the server again. Tables are recreated empty.

---

## 6. How to call the API

Examples use `curl.exe` so they behave the same in PowerShell and other shells. Replace `assess-secret` if you chose a different `API_KEY`.

If you did **not** set `API_KEY`, omit every `-H "X-API-Key: ..."` header. Stats and delete will succeed without it.

Do not add `curl -L` on redirect checks. `-L` follows the redirect and hides the `302` you are supposed to see. `-i` prints the status line and headers and stops.

From the interactive docs (`/docs`), use **Try it out** on an operation, fill the body or the code, and press **Execute**. For stats and delete, click **Authorize** is not wired as a global scheme; type the header name `X-API-Key` in the parameter list the operation shows, or call those two endpoints with `curl` as below.

---

## 7. Assessment walkthrough

Do these steps in order on a freshly started server. Each step lists the command and the result that counts as a pass.

### Step 1 — Create a short link with no expiry

```powershell
curl.exe -s -D - -o body.json -X POST http://127.0.0.1:8000/api/urls -H "Content-Type: application/json" -d "{\"url\": \"https://example.com/some/long/path\"}"
type body.json
```

Pass criteria:

- HTTP status `201`
- JSON contains `short_code`, `short_url`, `original_url`, `created_at`, and `expires_at`
- `short_code` is 7 characters, letters and digits only
- `short_url` is `http://127.0.0.1:8000/` plus that code (or `http://localhost:8000/` if you left `BASE_URL` at its default)
- `original_url` matches the URL you sent
- `expires_at` is `null`
- `created_at` is a timestamp

Copy the `short_code` value. The rest of this walkthrough calls it `CODE`.

Creating the same URL again must return a **different** code. Shortening is not a lookup of an existing link.

### Step 2 — Create a link that expires in one hour

```powershell
curl.exe -s -D - -X POST http://127.0.0.1:8000/api/urls -H "Content-Type: application/json" -d "{\"url\": \"https://example.com/temporary\", \"ttl_seconds\": 3600}"
```

Pass criteria:

- HTTP status `201`
- `expires_at` is about 3600 seconds after `created_at`

You may instead send an absolute future time and omit `ttl_seconds`:

```json
{"url": "https://example.com/temporary", "expires_at": "2026-12-01T00:00:00Z"}
```

Send only one of those two fields. Sending both is rejected.

### Step 3 — Follow the short link

```powershell
curl.exe -i http://127.0.0.1:8000/CODE
```

Pass criteria:

- HTTP status `302`
- A `Location` header equal to the original URL
- A `Cache-Control: no-store` header

In a browser, opening `http://127.0.0.1:8000/CODE` should land on the original site. The browser follows the redirect, so you will not see the `302` yourself; use `curl.exe -i` when you need the status code.

### Step 4 — Read statistics

```powershell
curl.exe -s -D - http://127.0.0.1:8000/api/urls/CODE/stats -H "X-API-Key: assess-secret"
```

Pass criteria:

- HTTP status `200`
- Body includes `short_code`, `original_url`, `click_count`, `created_at`, `expires_at`, `is_active`, `last_accessed_at`
- After one successful redirect, `click_count` is `1` and `last_accessed_at` is set
- `is_active` is `true`

Repeat the redirect from Step 3 several times and read stats again. `click_count` must equal the number of successful `302` responses.

### Step 5 — Reject a bad API key

Skip this step if you started without `API_KEY`.

```powershell
curl.exe -i http://127.0.0.1:8000/api/urls/CODE/stats
curl.exe -i http://127.0.0.1:8000/api/urls/CODE/stats -H "X-API-Key: wrong-key"
```

Pass criteria:

- Missing header: `401` and `"code": "unauthorized"`
- Wrong key: `403` and `"code": "forbidden"`
- The same two statuses apply to `DELETE`

Create (`POST /api/urls`) and redirect (`GET /CODE`) must still succeed with no API key.

### Step 6 — Soft-delete the link

```powershell
curl.exe -i -X DELETE http://127.0.0.1:8000/api/urls/CODE -H "X-API-Key: assess-secret"
```

Pass criteria:

- HTTP status `204`
- Empty body

Then:

```powershell
curl.exe -i http://127.0.0.1:8000/CODE
curl.exe -s http://127.0.0.1:8000/api/urls/CODE/stats -H "X-API-Key: assess-secret"
curl.exe -i -X DELETE http://127.0.0.1:8000/api/urls/CODE -H "X-API-Key: assess-secret"
```

Pass criteria:

- Redirect is now `404` with `"code": "not_found"`. No further click is counted.
- Stats still return `200`. `is_active` is `false`. `click_count` is unchanged from before the failed redirect.
- Deleting the same code again returns `204`. Delete is idempotent for a code that exists.

Deleting a code that was never created returns `404`.

### Step 7 — Unknown and expired codes

Unknown code:

```powershell
curl.exe -i http://127.0.0.1:8000/doesNotExist
```

Pass criteria: `404`, `"code": "not_found"`.

Expired code: create a link with a short TTL, wait until that TTL has passed, then request the short link. For a manual check without waiting, a past `expires_at` is rejected at creation time, so you cannot create an already-expired link through the API. Expiry is checked when the link is used, not by a background job. After expiry:

- Redirect returns `410` and `"code": "gone"`
- `click_count` does not increase and `last_accessed_at` stays unset if there were no earlier clicks
- Stats still return `200` and still show `is_active: true` together with the past `expires_at`

A deactivated code and an unknown code both look like `404` on redirect. An expired but still active code is the one that returns `410`.

### Step 8 — Invalid create requests

Each of these must fail, return JSON (not an HTML page), and must not create a row you can later redirect.

| Request body | Expected |
|---|---|
| `{}` | `422`, code `validation_error` |
| `{"url": "not a url"}` | `400`, code `invalid_url` |
| `{"url": "ftp://example.com/file"}` | `400`, code `invalid_url` |
| `{"url": "javascript:alert(1)"}` | `400`, code `invalid_url` |
| `{"url": "http://"}` | `400`, code `invalid_url` |
| `{"url": "https://example.com/hello world"}` | `400`, code `invalid_url` (whitespace is rejected) |
| A URL longer than `MAX_URL_LENGTH` (default 2048) | `400`, code `invalid_url` |
| `{"url": "https://example.com", "ttl_seconds": 0}` | `400`, code `invalid_expiration` |
| `{"url": "https://example.com", "ttl_seconds": -5}` | `400`, code `invalid_expiration` |
| Both `expires_at` (in the future) and `ttl_seconds` | `400`, code `invalid_expiration` |
| `expires_at` in the past | `400`, code `invalid_expiration` |
| `expires_at` set to a non-date string | `422`, code `validation_error` |

Example:

```powershell
curl.exe -i -X POST http://127.0.0.1:8000/api/urls -H "Content-Type: application/json" -d "{\"url\": \"ftp://example.com/file\"}"
```

Every error body has this shape, and the response never includes a stack trace:

```json
{"error": {"code": "invalid_url", "message": "URL scheme must be http or https"}}
```

Validation errors (`422`) also include a `details` array of field, message, and type. Other errors omit `details`.

---

## 8. Endpoint reference

| Method | Path | Auth | Success |
|---|---|---|---|
| `POST` | `/api/urls` | none | `201` JSON |
| `GET` | `/api/urls/{short_code}/stats` | `X-API-Key` when `API_KEY` is set | `200` JSON |
| `DELETE` | `/api/urls/{short_code}` | `X-API-Key` when `API_KEY` is set | `204` empty |
| `GET` | `/{short_code}` | none | `302` redirect |

### Create — `POST /api/urls`

```json
{
  "url": "https://example.com/some/long/path",
  "ttl_seconds": 3600
}
```

| Field | Required | Rule |
|---|---|---|
| `url` | yes | Non-empty string. Scheme `http` or `https`. Must include a host. No spaces or control characters. Length at most `MAX_URL_LENGTH`. |
| `expires_at` | no | Future date-time. A value without a timezone is treated as UTC. |
| `ttl_seconds` | no | Positive integer. Converted to an absolute expiry from the creation time. |

Do not send `expires_at` and `ttl_seconds` together. Omit both for a link that does not expire.

Success body:

```json
{
  "short_code": "aB3dE9x",
  "short_url": "http://127.0.0.1:8000/aB3dE9x",
  "original_url": "https://example.com/some/long/path",
  "created_at": "2026-11-03T05:00:00Z",
  "expires_at": "2026-11-03T06:00:00Z"
}
```

`short_code` is random. The same original URL submitted twice produces two independent records.

### Redirect — `GET /{short_code}`

Success: `302`, `Location` set to the stored URL, `Cache-Control: no-store`. The click is counted in the same database update that checks the link is still active and unexpired.

### Stats — `GET /api/urls/{short_code}/stats`

Returns the stored record even when the link is expired or deactivated. Returns `404` only when the code has never existed.

| Field | Meaning |
|---|---|
| `click_count` | Successful redirects only |
| `last_accessed_at` | Time of the latest counted click, or `null` |
| `is_active` | `false` after a successful delete |
| `expires_at` | Absolute expiry, or `null` if the link does not expire |

### Delete — `DELETE /api/urls/{short_code}`

Sets `is_active` to false and keeps the row. A second delete of the same existing code returns `204` again. An unknown code returns `404`.

### Error catalog

| HTTP | `error.code` | When |
|---|---|---|
| 400 | `invalid_url` | URL missing, wrong scheme, no host, too long, whitespace, or malformed |
| 400 | `invalid_expiration` | Non-positive TTL, past `expires_at`, or both expiry fields sent |
| 401 | `unauthorized` | `API_KEY` is set and the `X-API-Key` header is missing |
| 403 | `forbidden` | Header is present but does not match |
| 404 | `not_found` | Unknown code, or redirect/delete target that is deactivated (redirect only; stats still work) |
| 405 | `method_not_allowed` | Verb not defined for that path |
| 410 | `gone` | Code exists, is active, and `expires_at` is in the past |
| 422 | `validation_error` | Body is not valid JSON or a field has the wrong JSON type |
| 500 | `internal_server_error` | Unexpected failure. The client message is generic. |
| 500 | `code_generation_failed` | A unique code could not be reserved after 5 attempts |

---

## 9. Using the browser docs as the assessor UI

1. Start the server (section 5).
2. Open `http://127.0.0.1:8000/docs`.
3. Open **POST /api/urls** → **Try it out**.
4. Set the request body to `{"url": "https://example.com/docs-check"}` and execute.
5. Confirm status `201` and copy `short_code`.
6. Open **GET /{short_code}** → **Try it out**, paste the code, and execute. The docs UI follows redirects, so you may land on the target site or see the redirect response depending on the browser. Prefer `curl.exe -i` when you must record the `302`.
7. Open **GET /api/urls/{short_code}/stats**. If `API_KEY` is set, add header `X-API-Key` with your secret, then execute. Confirm `click_count`.
8. Open **DELETE /api/urls/{short_code}** with the same header. Confirm `204`. Execute it a second time and confirm `204` again.
9. Request the short code once more and confirm `404`.

---

## 10. Automated tests

The test suite is the repeatable half of the assessment. It uses temporary SQLite files and does not touch `shortener.db`. The server does not need to be running. Stop it if port 8000 matters to you for other reasons; pytest does not bind that port.

From the project root, with `.venv` active:

```powershell
pytest
```

Equivalent:

```powershell
python -m pytest -q
```

`pytest.ini` already points at the `tests` directory and puts the project root on the import path.

What the suite covers:

| Area | What it checks |
|---|---|
| Create | Response shape, code alphabet and length, two creates of the same URL get different codes |
| Validation | Bad URLs, missing fields, bad TTL, past expiry, both expiry fields; no row is stored |
| Redirect | `302` and `Location` |
| Clicks | Count matches the number of redirects, including 50 concurrent redirects |
| Expiry | `410` and no click increment; stats still readable |
| Delete | `204`, later redirect is `404`, click count frozen, second delete still `204` |
| Auth | Missing key `401`, wrong key `403`, create and redirect stay public |
| Collisions | A duplicate generated code is retried; giving up returns `code_generation_failed` |
| Errors | One JSON shape, no traceback text |

A pass is a pytest summary with no failures. The suite is quiet (`-q`). A failure prints the test name and assertion; that is an assessment finding, not an environment step you need to “work around.”

---

## 11. Where the data lives

Default file: `shortener.db` in the project root (or `assessment.db` if you followed section 4).

Table `short_urls`:

| Column | Meaning |
|---|---|
| `id` | Internal number |
| `short_code` | Unique public code |
| `original_url` | Stored destination |
| `created_at` | Creation time in UTC |
| `expires_at` | Expiry in UTC, or empty |
| `is_active` | `1` until soft-deleted |
| `click_count` | Successful redirects |
| `last_accessed_at` | Last counted click, or empty |

You can inspect the file with any SQLite browser while the server is stopped, or with the `sqlite3` shell:

```powershell
sqlite3 assessment.db "SELECT short_code, original_url, click_count, is_active FROM short_urls;"
```

If `sqlite3` is not installed, skip this. The stats endpoint shows the same facts.

Switching the URL to PostgreSQL is a configuration change (`DATABASE_URL`) plus a database driver such as `psycopg`. That driver is not in `requirements.txt`. The shipped, supported setup for this assessment is SQLite.

---

## 12. Project map

| Path | What it is |
|---|---|
| `runproject.py` | Starts the server on `127.0.0.1:8000` |
| `app/main.py` | Application object Uvicorn loads |
| `app/routes.py` | The four HTTP endpoints |
| `app/services.py` | Validation, expiry, code generation, click rules |
| `app/repository.py` | Database reads and writes |
| `app/models.py` | `short_urls` table |
| `app/auth.py` | `X-API-Key` checks |
| `app/config.py` | Environment variables |
| `app/errors.py` | Shared JSON error format |
| `tests/` | Automated assessment suite |
| `requirements.txt` | Install list |
| `README.md` | Short technical summary |

---

## 13. Limits you should score as designed behavior

These are not defects relative to the current product:

- With no `API_KEY`, anyone who can reach the port can read stats and delete links.
- Create and redirect are never authenticated and are not rate limited.
- Only `http` and `https` URLs with a host are accepted.
- There is no custom short code, no user account, and no edit-in-place of an existing link.
- Expired rows are not deleted. They stay until you remove the database file.
- Short codes are random. If five generation attempts all collide, create returns `500` with `code_generation_failed`.
- The server has no database migrations. Startup only creates missing tables.
- `runproject.py` cannot change host or port.
- Timestamps are UTC. A create body that omits the timezone on `expires_at` is interpreted as UTC.

---

## 14. Troubleshooting

| What you see | What to do |
|---|---|
| `python` is not recognized | Install Python 3.10+ and open a new terminal, or use the `py` launcher: `py -3 -m venv .venv`. |
| Activate script is disabled | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. |
| `No module named fastapi` or `No module named uvicorn` | Activate `.venv`, then `pip install -r requirements.txt`. |
| `Address already in use` / port 8000 | Another copy is still running. Stop it with `Ctrl+C`, or close the old terminal. Start only one server. |
| Browser works but `curl` shows `302` and the assessor expected the destination page | That is correct for `curl.exe -i`. Add nothing extra. Open the short URL in a browser to see the destination. |
| Stats return `401` | The server was started with `API_KEY`. Send `-H "X-API-Key: <the same value>"`. |
| Stats succeed with no key | The server was started without `API_KEY`. That matches the local-development rule. |
| You set `$env:API_KEY` and nothing changed | The server was already running. Stop it, set the variable, start it again. |
| `short_url` uses a different host than the one you called | `BASE_URL` and the listen address differ. Set `BASE_URL` before startup so it matches how you call the API. |
| `Environment variable CODE_LENGTH must be a positive integer` | Fix or clear `CODE_LENGTH` / `MAX_URL_LENGTH`, then start again. |
| Old links reappear after a restart | The SQLite file was kept. Delete it while the server is stopped to start clean. |
| `pytest` is not recognized | Use `python -m pytest -q` inside the activated virtual environment. |

---

## 15. Suggested assessment record

| Check | Pass? |
|---|---|
| Virtualenv created and `pip install -r requirements.txt` succeeds | |
| `python runproject.py` serves `http://127.0.0.1:8000/docs` | |
| Create returns `201` and a 7-character code | |
| Same URL twice returns two different codes | |
| Redirect returns `302`, correct `Location`, and `Cache-Control: no-store` | |
| Click count matches the number of successful redirects | |
| `ttl_seconds` sets a future `expires_at` | |
| Missing API key is `401`; wrong key is `403`; create and redirect stay public | |
| Delete returns `204`, redirect becomes `404`, stats show `is_active: false` | |
| Second delete of the same code returns `204` | |
| Unknown code is `404`; expired code is `410` and does not count a click | |
| Invalid URLs and bad expiry return the shared `error` JSON and store nothing | |
| `pytest` finishes with no failures | |
