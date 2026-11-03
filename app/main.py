"""FastAPI application factory.

Run with: ``uvicorn app.main:app``
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.database import build_engine, build_session_factory, init_db
from app.errors import register_exception_handlers
from app.routes import api_router, redirect_router


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create the application.

    Engine, session factory and settings are stored on ``app.state``. Tables are
    created on startup (lifespan).
    """
    settings = settings or get_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="URL Shortener",
        description="URL shortening service with click analytics and expiration.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    register_exception_handlers(app)

    # /api routes first; the catch-all /{short_code} redirect router goes last so
    # it never shadows them.
    app.include_router(api_router)
    app.include_router(redirect_router)
    return app


app = create_app()
