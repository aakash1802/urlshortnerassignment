"""HTTP routes.

``api_router`` holds the /api/urls endpoints; ``redirect_router`` holds the
catch-all ``GET /{short_code}`` and must be included AFTER ``api_router`` so it
cannot shadow /api routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.database import get_db
from app.schemas import CreateURLRequest, CreateURLResponse, StatsResponse
from app.services import UrlService

api_router = APIRouter(prefix="/api/urls", tags=["urls"])
redirect_router = APIRouter(tags=["redirect"])


def get_service(request: Request, db: Session = Depends(get_db)) -> UrlService:
    return UrlService(db, request.app.state.settings)


@api_router.post("", response_model=CreateURLResponse, status_code=201)
def create_short_url(payload: CreateURLRequest, service: UrlService = Depends(get_service)):
    record = service.create(payload.url, payload.expires_at, payload.ttl_seconds)
    return CreateURLResponse(
        short_code=record.short_code,
        short_url=service.build_short_url(record.short_code),
        original_url=record.original_url,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


@api_router.get(
    "/{short_code}/stats",
    response_model=StatsResponse,
    dependencies=[Depends(require_api_key)],
)
def get_stats(short_code: str, service: UrlService = Depends(get_service)):
    return StatsResponse.model_validate(service.get_stats(short_code))


@api_router.delete(
    "/{short_code}",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(require_api_key)],
)
def delete_short_url(short_code: str, service: UrlService = Depends(get_service)) -> Response:
    service.deactivate(short_code)
    return Response(status_code=204)


@redirect_router.get("/{short_code}", include_in_schema=True)
def redirect(short_code: str, service: UrlService = Depends(get_service)) -> RedirectResponse:
    target = service.redirect(short_code)
    return RedirectResponse(
        url=target,
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
