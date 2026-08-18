from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int = 400
    field_errors: list[dict[str, str]] = field(default_factory=list)


def error_payload(
    *,
    code: str,
    message: str,
    field_errors: list[dict[str, str]] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "field_errors": field_errors or [],
            "trace_id": trace_id or str(uuid4()),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                field_errors=exc.field_errors,
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="VALIDATION_ERROR",
                message="요청 필드를 확인해주세요.",
                field_errors=field_errors,
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        logger.error(
            "Database operation failed trace_id=%s error_type=%s",
            trace_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content=error_payload(
                code="DATABASE_UNAVAILABLE",
                message="데이터베이스 요청을 처리할 수 없습니다.",
                trace_id=trace_id,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", str(uuid4()))
        logger.error(
            "Unexpected server error trace_id=%s error_type=%s",
            trace_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_ERROR",
                message="서버에서 요청을 처리하지 못했습니다.",
                trace_id=trace_id,
            ),
        )
