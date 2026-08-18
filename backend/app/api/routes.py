from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, require_min_role
from app.config import settings
from app.database import get_db
from app.enums import ApiRole, EvidenceType, WorkflowStatus
from app.errors import DomainError
from app.schemas import (
    CaseEnvelope,
    CaseSummary,
    DecisionRequest,
    ErrorResponse,
    HealthOut,
    MatchRequest,
    PassportEvidenceOut,
    ResourceConfirmationRequest,
    ResourcePassportRequest,
    RulePolicyOut,
    RulePolicyVersionCreate,
)
from app.seed import GOLDEN_CASE_ID, reset_demo_data
from app.services.evidence import (
    add_passport_evidence,
    delete_evidence_safely,
    evidence_storage_keys_for_case,
    get_passport_evidence,
    list_passport_evidence,
    to_evidence_out,
)
from app.services.match import MatchProvider
from app.services.rule_catalog import (
    activate_rule_policy_version,
    create_rule_policy_version,
    get_rule_policy,
    list_rule_policies,
)
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
from app.storage import EvidenceStorage

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
ViewerPrincipal = Annotated[AuthPrincipal, Depends(require_min_role(ApiRole.VIEWER))]
OperatorPrincipal = Annotated[AuthPrincipal, Depends(require_min_role(ApiRole.OPERATOR))]
DecisionPrincipal = Annotated[AuthPrincipal, Depends(require_min_role(ApiRole.DECISION_MAKER))]
AdminPrincipal = Annotated[AuthPrincipal, Depends(require_min_role(ApiRole.ADMIN))]
PolicyKey = Annotated[
    str,
    ApiPath(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
]

api_router = APIRouter(
    prefix=settings.api_v1_prefix,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Insufficient role"},
        404: {"model": ErrorResponse, "description": "Resource not found"},
        409: {"model": ErrorResponse, "description": "Invalid workflow state"},
        413: {"model": ErrorResponse, "description": "Attachment too large"},
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


def _evidence_storage(request: Request) -> EvidenceStorage:
    return request.app.state.evidence_storage


@api_router.get("/cases", response_model=list[CaseSummary])
def list_cases(
    response: Response,
    db: DbSession,
    _principal: ViewerPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    workflow_status: WorkflowStatus | None = None,
) -> list[CaseSummary]:
    summaries, total = list_case_summaries(
        db,
        limit=limit,
        offset=offset,
        search=search,
        workflow_status=workflow_status,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return summaries


@api_router.get("/cases/{case_id}", response_model=CaseEnvelope)
def read_case(case_id: str, db: DbSession, _principal: ViewerPrincipal) -> CaseEnvelope:
    return get_case_envelope(db, case_id)


@api_router.put("/cases/{case_id}/resource-confirmation", response_model=CaseEnvelope)
def update_resource_confirmation(
    case_id: str,
    payload: ResourceConfirmationRequest,
    request: Request,
    db: DbSession,
    principal: OperatorPrincipal,
) -> CaseEnvelope:
    with db.begin():
        actor = (
            payload.confirmed_by if principal.is_demo and payload.confirmed_by else principal.actor
        )
        record = confirm_resource(
            db,
            case_id,
            payload,
            actor=actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.put("/cases/{case_id}/resource-passport", response_model=CaseEnvelope)
def update_resource_passport(
    case_id: str,
    payload: ResourcePassportRequest,
    request: Request,
    db: DbSession,
    principal: OperatorPrincipal,
) -> CaseEnvelope:
    with db.begin():
        record = save_passport(
            db,
            case_id,
            payload,
            actor=principal.actor,
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
    principal: OperatorPrincipal,
    idempotency_key: IdempotencyKey = None,
) -> CaseEnvelope:
    with db.begin():
        record = run_match(
            db,
            case_id,
            _match_provider(request),
            top_k=payload.top_k,
            idempotency_key=idempotency_key,
            actor=principal.actor,
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
    principal: DecisionPrincipal,
) -> CaseEnvelope:
    with db.begin():
        actor = payload.decided_by if principal.is_demo and payload.decided_by else principal.actor
        record = save_decision(
            db,
            case_id,
            payload,
            actor=actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.post("/cases/{case_id}/esg-scenario", response_model=CaseEnvelope)
def generate_esg_scenario(
    case_id: str,
    request: Request,
    db: DbSession,
    principal: OperatorPrincipal,
) -> CaseEnvelope:
    with db.begin():
        record = create_esg_scenario(
            db,
            case_id,
            actor=principal.actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.post("/cases/{case_id}/receipt", response_model=CaseEnvelope)
def generate_receipt(
    case_id: str,
    request: Request,
    db: DbSession,
    principal: DecisionPrincipal,
    idempotency_key: IdempotencyKey = None,
) -> CaseEnvelope:
    with db.begin():
        record = create_receipt(
            db,
            case_id,
            idempotency_key=idempotency_key,
            actor=principal.actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    return result


@api_router.get("/cases/{case_id}/receipt", response_model=CaseEnvelope)
def read_receipt(case_id: str, db: DbSession, _principal: ViewerPrincipal) -> CaseEnvelope:
    record = get_case(db, case_id)
    if record.receipt is None:
        raise DomainError("RECEIPT_NOT_FOUND", "아직 생성된 Receipt가 없습니다.", 404)
    return CaseEnvelope.model_validate(record.receipt.payload_json)


@api_router.post("/demo/reset", response_model=CaseEnvelope)
def reset_demo(request: Request, db: DbSession, _principal: AdminPrincipal) -> CaseEnvelope:
    if not settings.demo_mode or not settings.demo_reset_enabled:
        raise DomainError("NOT_FOUND", "Demo reset을 사용할 수 없습니다.", 404)
    storage = _evidence_storage(request)
    with db.begin():
        storage_keys = evidence_storage_keys_for_case(db, GOLDEN_CASE_ID)
        record = reset_demo_data(db)
        result = build_case_envelope(db, record)
    for storage_key in storage_keys:
        delete_evidence_safely(storage, storage_key)
    return result


@api_router.post(
    "/cases/{case_id}/resource-passport/evidence",
    response_model=PassportEvidenceOut,
    status_code=201,
)
def upload_passport_evidence(
    case_id: str,
    request: Request,
    db: DbSession,
    principal: OperatorPrincipal,
    file: Annotated[UploadFile, File()],
    evidence_type: Annotated[EvidenceType, Form()],
    description: Annotated[str | None, Form(max_length=2000)] = None,
) -> PassportEvidenceOut:
    storage = _evidence_storage(request)
    evidence = None
    try:
        with db.begin():
            evidence = add_passport_evidence(
                db,
                storage,
                case_id,
                stream=file.file,
                filename=file.filename,
                media_type=file.content_type,
                evidence_type=evidence_type,
                description=description,
                actor=principal.actor,
                max_bytes=settings.evidence_max_bytes,
                trace_id=_trace_id(request),
            )
            result = to_evidence_out(evidence)
    except Exception:
        if evidence is not None:
            delete_evidence_safely(storage, evidence.storage_key)
        raise
    finally:
        file.file.close()
    return result


@api_router.get(
    "/cases/{case_id}/resource-passport/evidence",
    response_model=list[PassportEvidenceOut],
)
def read_passport_evidence(
    case_id: str,
    db: DbSession,
    _principal: ViewerPrincipal,
) -> list[PassportEvidenceOut]:
    return list_passport_evidence(db, case_id)


@api_router.get(
    "/cases/{case_id}/resource-passport/evidence/{evidence_id}/content",
    response_class=FileResponse,
)
def download_passport_evidence(
    case_id: str,
    evidence_id: str,
    request: Request,
    db: DbSession,
    _principal: ViewerPrincipal,
) -> FileResponse:
    evidence = get_passport_evidence(db, case_id, evidence_id)
    path = _evidence_storage(request).resolve(evidence.storage_key)
    return FileResponse(
        path,
        media_type=evidence.media_type,
        filename=evidence.original_filename,
    )


@api_router.get("/rule-policies", response_model=list[RulePolicyOut])
def read_rule_policies(db: DbSession, _principal: ViewerPrincipal) -> list[RulePolicyOut]:
    return list_rule_policies(db)


@api_router.get("/rule-policies/{policy_key}", response_model=RulePolicyOut)
def read_rule_policy(
    policy_key: PolicyKey,
    db: DbSession,
    _principal: ViewerPrincipal,
) -> RulePolicyOut:
    return get_rule_policy(db, policy_key)


@api_router.post(
    "/rule-policies/{policy_key}/versions",
    response_model=RulePolicyOut,
    status_code=201,
)
def create_policy_version(
    policy_key: PolicyKey,
    payload: RulePolicyVersionCreate,
    db: DbSession,
    principal: AdminPrincipal,
) -> RulePolicyOut:
    with db.begin():
        result = create_rule_policy_version(db, policy_key, payload, actor=principal.actor)
    return result


@api_router.post(
    "/rule-policies/{policy_key}/versions/{version}/activate",
    response_model=RulePolicyOut,
)
def activate_policy_version(
    policy_key: PolicyKey,
    version: Annotated[int, ApiPath(ge=1)],
    db: DbSession,
    principal: AdminPrincipal,
) -> RulePolicyOut:
    with db.begin():
        result = activate_rule_policy_version(db, policy_key, version, actor=principal.actor)
    return result


@health_router.get("/health", response_model=HealthOut)
@health_router.get("/health/live", response_model=HealthOut)
def live_health() -> HealthOut:
    return HealthOut(status="ok")


@health_router.get("/health/ready", response_model=HealthOut)
def readiness(request: Request, db: DbSession) -> HealthOut:
    db.execute(text("SELECT 1"))
    provider = _match_provider(request)
    storage = _evidence_storage(request)
    storage.check_ready()
    return HealthOut(
        status="ready",
        database="ok",
        match_provider=provider.__class__.__name__,
        evidence_storage=storage.__class__.__name__,
    )
