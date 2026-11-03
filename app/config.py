"""Environment-based application settings.

Settings are read from environment variables at call time (see ``get_settings``)
so tests can override them with ``monkeypatch.setenv`` or by passing an explicit
``Settings`` instance to ``create_app``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_DATABASE_URL = "sqlite:///./shortener.db"
DEFAULT_MAX_URL_LENGTH = 2048
DEFAULT_CODE_LENGTH = 7


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be a positive integer, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Application settings.

    API_KEY: when unset/empty, management endpoints (stats, delete) are NOT
    protected (documented assumption for local development).
    """

    base_url: str = DEFAULT_BASE_URL
    database_url: str = DEFAULT_DATABASE_URL
    api_key: Optional[str] = None
    max_url_length: int = DEFAULT_MAX_URL_LENGTH
    code_length: int = DEFAULT_CODE_LENGTH


def get_settings() -> Settings:
    """Build settings from environment variables, applying defaults."""
    base_url = (os.environ.get("BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    database_url = (os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL).strip()
    api_key = (os.environ.get("API_KEY") or "").strip() or None
    return Settings(
        base_url=base_url or DEFAULT_BASE_URL,
        database_url=database_url or DEFAULT_DATABASE_URL,
        api_key=api_key,
        max_url_length=_int_env("MAX_URL_LENGTH", DEFAULT_MAX_URL_LENGTH),
        code_length=_int_env("CODE_LENGTH", DEFAULT_CODE_LENGTH),
    )
