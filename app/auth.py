"""API-key authentication for management endpoints.

Behavior: when ``API_KEY`` is configured, requests must send a matching
``X-API-Key`` header. A missing header -> 401, an invalid key -> 403. When no
API key is configured, management endpoints are open (documented assumption).
"""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Header, Request

from app.errors import AppError


def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    configured = request.app.state.settings.api_key
    if not configured:
        return
    if not x_api_key:
        raise AppError(
            401,
            "unauthorized",
            "Missing API key. Provide it in the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not secrets.compare_digest(x_api_key.encode("utf-8"), configured.encode("utf-8")):
        raise AppError(403, "forbidden", "Invalid API key.")
