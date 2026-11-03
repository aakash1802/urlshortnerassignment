"""Terminal launcher: run the existing application with ``python runproject.py``.

The project's entry point is the FastAPI application ``app.main:app`` (normally
started with ``uvicorn app.main:app``). This script only delegates to uvicorn;
it contains no application logic.
"""
from __future__ import annotations

import sys

APP_IMPORT_PATH = "app.main:app"
HOST = "127.0.0.1"
PORT = 8000  # matches the default BASE_URL (http://localhost:8000)


def main() -> int:
    """Start the existing application and return a process exit status."""
    import uvicorn  # imported lazily so importing this module has no side effects

    uvicorn.run(APP_IMPORT_PATH, host=HOST, port=PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
