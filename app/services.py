"""Business logic for the URL shortener.

This layer is storage-agnostic: it only talks to the repository. All timestamps
are timezone-aware UTC.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.models import ShortURL, utcnow
from app.repository import ShortURLRepository

BASE62_ALPHABET = string.ascii_letters + string.digits
MAX_CODE_ATTEMPTS = 5
ALLOWED_SCHEMES = ("http", "https")


class NotFoundError(AppError):
    """Unknown or deactivated short code (HTTP 404)."""

    def __init__(self, message: str = "Short URL not found") -> None:
        super().__init__(404, "not_found", message)


class GoneError(AppError):
    """Expired short code (HTTP 410)."""

    def __init__(self, message: str = "Short URL has expired") -> None:
        super().__init__(410, "gone", message)


class InvalidURLError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "invalid_url", message)


class InvalidExpirationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "invalid_expiration", message)


class CodeGenerationError(AppError):
    def __init__(self) -> None:
        super().__init__(500, "code_generation_failed", "Could not generate a unique short code")


def generate_short_code(length: int = 7) -> str:
    """Random base62 code using the cryptographically secure ``secrets`` module."""
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))


def validate_url(url: object, max_length: int) -> str:
    """Validate an original URL (http/https, host required, bounded length)."""
    if not isinstance(url, str) or not url:
        raise InvalidURLError("URL is required")
    if len(url) > max_length:
        raise InvalidURLError(f"URL must not exceed {max_length} characters")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise InvalidURLError("URL must not contain whitespace or control characters")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # raises ValueError for an invalid port
    except ValueError:
        raise InvalidURLError("URL is malformed") from None
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidURLError("URL scheme must be http or https")
    if not host:
        raise InvalidURLError("URL must include a host")
    return url


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UrlService:
    """Use cases: create, redirect resolution, stats, deactivation."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        now_fn: Callable[[], datetime] = utcnow,
        code_generator: Optional[Callable[[int], str]] = None,
    ) -> None:
        self.repo = ShortURLRepository(session)
        self.settings = settings
        self._now = now_fn
        self._generate_code = code_generator or generate_short_code

    # ----- helpers -----
    def build_short_url(self, short_code: str) -> str:
        return f"{self.settings.base_url.rstrip('/')}/{short_code}"

    @staticmethod
    def is_expired(record: ShortURL, now: datetime) -> bool:
        """Lazy expiry evaluation at request time."""
        if record.expires_at is None:
            return False
        return _as_utc(record.expires_at) <= now

    def resolve_expiration(
        self,
        expires_at: Optional[datetime],
        ttl_seconds: Optional[int],
        now: datetime,
    ) -> Optional[datetime]:
        """Turn expires_at / ttl_seconds input into an absolute UTC expiry (or None)."""
        if expires_at is not None and ttl_seconds is not None:
            raise InvalidExpirationError("Provide either expires_at or ttl_seconds, not both")
        if ttl_seconds is not None:
            if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
                raise InvalidExpirationError("ttl_seconds must be a positive integer")
            try:
                return now + timedelta(seconds=ttl_seconds)
            except OverflowError:
                raise InvalidExpirationError("ttl_seconds is too large") from None
        if expires_at is not None:
            value = _as_utc(expires_at)
            if value <= now:
                raise InvalidExpirationError("expires_at must be in the future")
            return value
        return None

    # ----- use cases -----
    def create(
        self,
        url: object,
        expires_at: Optional[datetime] = None,
        ttl_seconds: Optional[int] = None,
    ) -> ShortURL:
        """Validate input and create a new, independent short URL."""
        original = validate_url(url, self.settings.max_url_length)
        now = self._now()
        expiry = self.resolve_expiration(expires_at, ttl_seconds, now)
        for _ in range(MAX_CODE_ATTEMPTS):
            code = self._generate_code(self.settings.code_length)
            try:
                return self.repo.create(code, original, expires_at=expiry, created_at=now)
            except IntegrityError:
                continue  # collision: retry with a new code
        raise CodeGenerationError()

    def redirect(self, short_code: str) -> str:
        """Resolve a code to its original URL and atomically count the click.

        Unknown/deactivated -> NotFoundError; expired -> GoneError (no click counted).
        """
        now = self._now()
        record = self.repo.get_by_code(short_code)
        if record is None or not record.is_active:
            raise NotFoundError()
        if self.is_expired(record, now):
            raise GoneError()
        if not self.repo.increment_click(short_code, now):
            # State changed between the read and the atomic update; classify again.
            current = self.repo.get_by_code(short_code)
            if current is None or not current.is_active:
                raise NotFoundError()
            raise GoneError()
        return record.original_url

    def get_stats(self, short_code: str) -> ShortURL:
        """Return the record regardless of expiry/active state; 404 if unknown."""
        record = self.repo.get_by_code(short_code)
        if record is None:
            raise NotFoundError()
        return record

    def deactivate(self, short_code: str) -> None:
        """Idempotent soft delete; 404 if the code is unknown."""
        if not self.repo.deactivate(short_code):
            raise NotFoundError()
