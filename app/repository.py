"""Persistence layer for short URLs.

Only portable SQLAlchemy Core/ORM constructs are used so the backend can be
switched from SQLite to PostgreSQL without touching business logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ShortURL, utcnow


class ShortURLRepository:
    """Data access for :class:`ShortURL` records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        short_code: str,
        original_url: str,
        expires_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ) -> ShortURL:
        """Insert a new record and commit.

        Raises ``sqlalchemy.exc.IntegrityError`` (after rolling back the session)
        if ``short_code`` already exists, so callers can retry with a new code.
        """
        record = ShortURL(
            short_code=short_code,
            original_url=original_url,
            expires_at=expires_at,
            created_at=created_at or utcnow(),
            is_active=True,
            click_count=0,
            last_accessed_at=None,
        )
        self.session.add(record)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise
        return record

    def get_by_code(self, short_code: str) -> Optional[ShortURL]:
        """Fetch a record by its (uniquely indexed) short code, or None.

        Always reads fresh state from the database.
        """
        stmt = (
            select(ShortURL)
            .where(ShortURL.short_code == short_code)
            .execution_options(populate_existing=True)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def increment_click(self, short_code: str, now: datetime) -> bool:
        """Atomically count a click.

        Issues a single ``UPDATE ... SET click_count = click_count + 1,
        last_accessed_at = :now WHERE short_code = :code AND is_active AND
        (expires_at IS NULL OR expires_at > :now)``. Returns True when a row was
        updated; False if the code is unknown, deactivated or expired (in which
        case nothing is changed).
        """
        stmt = (
            update(ShortURL)
            .where(
                ShortURL.short_code == short_code,
                ShortURL.is_active.is_(True),
                or_(ShortURL.expires_at.is_(None), ShortURL.expires_at > now),
            )
            .values(
                click_count=ShortURL.click_count + 1,
                last_accessed_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(stmt)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return result.rowcount == 1

    def deactivate(self, short_code: str) -> bool:
        """Soft-delete a record (``is_active = False``).

        Idempotent: returns True if the code exists (whether or not it was
        already deactivated), False if it is unknown.
        """
        stmt = (
            update(ShortURL)
            .where(ShortURL.short_code == short_code)
            .values(is_active=False)
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(stmt)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        if result.rowcount and result.rowcount > 0:
            return True
        # Some backends report only changed rows; confirm existence explicitly.
        return self.get_by_code(short_code) is not None
