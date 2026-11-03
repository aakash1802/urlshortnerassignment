"""SQLAlchemy engine/session setup.

The engine and session factory are created per application (stored on
``app.state``) so tests can use isolated databases. Switching to PostgreSQL only
requires changing DATABASE_URL.
"""
from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine(database_url: str) -> Engine:
    """Create an engine with sensible per-backend options."""
    url = make_url(database_url)
    kwargs: dict = {"future": True}
    if url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if url.database in (None, "", ":memory:"):
            # Share a single in-memory connection across threads.
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(database_url, **kwargs)


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db(engine: Engine) -> None:
    """Create all tables (idempotent)."""
    # Import models so they are registered on Base.metadata.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the app's engine."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
