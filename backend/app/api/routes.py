from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.errors import DomainError
from app.schemas import (
    CaseEnvelope,
    CaseSummary,
    DecisionRequest,
    ErrorResponse,
    HealthOut,
    MatchRequest,
    ResourceConfirmationRequest,
    ResourcePassportRequest,
)
from app.seed import reset_demo_data
from app.services.match import MatchProvider
from app.services.workflow import (
    build_case_envelope,
    confirm_resource,
    create_esg_scenario,
    create_receipt,
    get_case,
    get_case_envelope,
    list_case_summaries,
    run_match,
    save_decision,
    save_passport,
)

DbSession = Annotated[Session, Depends(get_db)]
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r".*\S.*",
    ),
]
Actor = Annotated[
    str,
    Header(alias="X-Actor", min_length=1, max_length=120, pattern=r".*\S.*"),
]

api_router = APIRouter(
    prefix=settings.api_v1_prefix,
    responses={
        404: {"model": ErrorResponse, "description": "Resource not found"},
        409: {"model": ErrorResponse, "description": "Invalid workflow state"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
        503: {"model": ErrorResponse, "description": "Dependency unavailable"},
    },
)
health_router = APIRouter()


def _trace_id(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def _match_provider(request: Request) -> MatchProvider:
    return request.app.state.match_provider


@api_router.get("/cases", response_model=list[CaseSummary])
def list_cases(db: DbSession) -> list[CaseSummary]:
    return list_case_summaries(db)


@api_router.get("/cases/{case_id}", response_model=CaseEnvelope)
def read_case(case_id: str, db: DbSession) -> CaseEnvelope:
    return get_case_envelope(db, case_id)


@api_router.put("/cases/{case_id}/resource-confirmation", response_model=CaseEnvelope)
def update_resource_confirmation(
    case_id: str,
    payload: ResourceConfirmationRequest,
    request: Request,
    db: DbSession,
) -> CaseEnvelope:
    with db.begin():
        record = confirm_resource(db, case_id, payload, trace_id=_trace_id(request))
        result = build_case_envelope(db, record)
    return result


@api_router.put("/cases/{case_id}/resource-passport", response_model=CaseEnvelope)
def update_resource_passport(
    case_id: str,
    payload: ResourcePassportRequest,
    request: Request,
    db: DbSession,
    x_actor: Actor = "demo_operator",
) -> CaseEnvelope:
    with db.begin():
        record = save_passport(
            db,
            case_id,
            payload,
            actor=x_actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.post("/cases/{case_id}/matches", response_model=CaseEnvelope)
def create_match(
    case_id: str,
    payload: MatchRequest,
    request: Request,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
    x_actor: Actor = "demo_operator",
) -> CaseEnvelope:
    with db.begin():
        record = run_match(
            db,
            case_id,
            _match_provider(request),
            top_k=payload.top_k,
            idempotency_key=idempotency_key,
            actor=x_actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.put("/cases/{case_id}/decision", response_model=CaseEnvelope)
def update_decision(
    case_id: str,
    payload: DecisionRequest,
    request: Request,
    db: DbSession,
) -> CaseEnvelope:
    with db.begin():
        record = save_decision(db, case_id, payload, trace_id=_trace_id(request))
        result = build_case_envelope(db, record)
    return result


@api_router.post("/cases/{case_id}/esg-scenario", response_model=CaseEnvelope)
def generate_esg_scenario(
    case_id: str,
    request: Request,
    db: DbSession,
    x_actor: Actor = "demo_operator",
) -> CaseEnvelope:
    with db.begin():
        record = create_esg_scenario(
            db,
            case_id,
            actor=x_actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.post("/cases/{case_id}/receipt", response_model=CaseEnvelope)
def generate_receipt(
    case_id: str,
    request: Request,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
    x_actor: Actor = "demo_operator",
) -> CaseEnvelope:
    with db.begin():
        record = create_receipt(
            db,
            case_id,
            idempotency_key=idempotency_key,
            actor=x_actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.get("/cases/{case_id}/receipt", response_model=CaseEnvelope)
def read_receipt(case_id: str, db: DbSession) -> CaseEnvelope:
    record = get_case(db, case_id)
    if record.receipt is None:
        raise DomainError("RECEIPT_NOT_FOUND", "아직 생성된 Receipt가 없습니다.", 404)
    return CaseEnvelope.model_validate(record.receipt.payload_json)


@api_router.post("/demo/reset", response_model=CaseEnvelope)
def reset_demo(db: DbSession) -> CaseEnvelope:
    if not settings.demo_mode or not settings.demo_reset_enabled:
        raise DomainError("NOT_FOUND", "Demo reset을 사용할 수 없습니다.", 404)
    with db.begin():
        record = reset_demo_data(db)
        result = build_case_envelope(db, record)
    return result


@health_router.get("/health", response_model=HealthOut)
@health_router.get("/health/live", response_model=HealthOut)
def live_health() -> HealthOut:
    return HealthOut(status="ok")


@health_router.get("/health/ready", response_model=HealthOut)
def readiness(request: Request, db: DbSession) -> HealthOut:
    db.execute(text("SELECT 1"))
    provider = _match_provider(request)
    return HealthOut(
        status="ready",
        database="ok",
        match_provider=provider.__class__.__name__,
    )
