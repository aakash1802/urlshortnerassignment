"""Consistent JSON error handling.

Every error response has the shape::

    {"error": {"code": "<machine_code>", "message": "<human message>", "details": [...]?}}

Stack traces and internal exception text are never returned to clients.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    422: "validation_error",
    500: "internal_server_error",
}


class AppError(Exception):
    """Application-level error carrying an HTTP status and machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Optional[dict[str, str]] = None,
        details: Optional[list[Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details


def error_body(code: str, message: str, details: Optional[list[Any]] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: Optional[dict[str, str]] = None,
    details: Optional[list[Any]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message, details),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.headers, exc.details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    detail = exc.detail
    message = detail if isinstance(detail, str) and detail else code.replace("_", " ").capitalize()
    return error_response(exc.status_code, code, message, getattr(exc, "headers", None))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        details.append(
            {
                "field": ".".join(loc),
                "message": str(err.get("msg", "Invalid value")),
                "type": str(err.get("type", "value_error")),
            }
        )
    return error_response(422, "validation_error", "Request validation failed", details=details)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log server-side only; the client gets a generic message.
    logger.error(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=(type(exc), exc, exc.__traceback__)
    )
    return error_response(500, "internal_server_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
