from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import AuthPrincipal, require_min_role, require_min_role_without_actor_override
from app.config import settings
from app.database import get_db
from app.enums import ApiRole, EvidenceType, WorkflowStatus
from app.errors import DomainError
from app.schemas import (
    CaseEnvelope,
    CaseSummary,
    DecisionRequest,
    DemandCreate,
    DemandIndexEventOut,
    DemandIndexSyncOut,
    DemandOut,
    DemandUpdate,
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
from app.services.demand import (
    complete_index_event,
    create_demand,
    create_index_event,
    create_index_event_retry,
    deactivate_demand,
    list_demands,
    list_index_events,
    update_demand,
)
from app.services.evidence import (
    add_passport_evidence,
    delete_evidence_safely,
    evidence_storage_keys_for_case,
    get_passport_evidence,
    list_passport_evidence,
    to_evidence_out,
)
from app.services.match import DemandIndexManager, IndexSyncResult, MatchProvider
from app.services.rule_catalog import (
    activate_rule_policy_version,
    create_rule_policy_version,
    get_rule_policy,
    list_rule_policies,
)
from app.services.workflow import (
    build_case_envelope,
    complete_match,
    confirm_resource,
    create_esg_scenario,
    create_receipt,
    fail_match,
    get_case,
    get_case_envelope,
    list_case_summaries,
    prepare_match,
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
StrictViewerPrincipal = Annotated[
    AuthPrincipal,
    Depends(require_min_role_without_actor_override(ApiRole.VIEWER)),
]
StrictAdminPrincipal = Annotated[
    AuthPrincipal,
    Depends(require_min_role_without_actor_override(ApiRole.ADMIN)),
]
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
logger = logging.getLogger(__name__)


def _trace_id(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def _match_provider(request: Request) -> MatchProvider:
    return request.app.state.match_provider


def _evidence_storage(request: Request) -> EvidenceStorage:
    return request.app.state.evidence_storage


def _demand_index(request: Request) -> DemandIndexManager | None:
    provider = _match_provider(request)
    return provider if isinstance(provider, DemandIndexManager) else None


def _process_demand_index_event(
    request: Request,
    db: Session,
    event_id: str,
    *,
    operation: str,
    demand_id: str | None = None,
) -> IndexSyncResult | None:
    index = _demand_index(request)
    if index is None:
        with db.begin():
            complete_index_event(db, event_id, status="SKIPPED")
        return None
    try:
        if operation == "UPSERT" and demand_id is not None:
            index.upsert_demand(demand_id)
            result = IndexSyncResult(upserted=1, deleted=0)
        elif operation == "DELETE" and demand_id is not None:
            index.delete_demand(demand_id)
            result = IndexSyncResult(upserted=0, deleted=1)
        elif operation == "SYNC_ALL":
            result = index.sync_all_demands()
        else:
            raise RuntimeError("Invalid Demand index operation")
    except Exception as exc:
        logger.error(
            "Demand index mutation failed demand_id=%s error_type=%s",
            demand_id or "ALL",
            type(exc).__name__,
        )
        with db.begin():
            complete_index_event(
                db,
                event_id,
                status="FAILED",
                error_message=type(exc).__name__,
            )
        raise DomainError(
            "DEMAND_INDEX_UNAVAILABLE",
            "Demand는 PostgreSQL에 저장됐지만 검색 인덱스를 갱신하지 못했습니다.",
            503,
        ) from exc
    with db.begin():
        complete_index_event(db, event_id, status="SUCCEEDED")
    return result


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


@api_router.get("/demands", response_model=list[DemandOut])
def read_demands(
    response: Response,
    db: DbSession,
    _principal: StrictViewerPrincipal,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DemandOut]:
    records, total = list_demands(
        db,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return [DemandOut.model_validate(record) for record in records]


@api_router.post("/demands", response_model=DemandOut, status_code=201)
def add_demand(
    payload: DemandCreate,
    request: Request,
    db: DbSession,
    principal: StrictAdminPrincipal,
) -> DemandOut:
    with db.begin():
        record = create_demand(db, payload)
        event = create_index_event(
            db,
            operation="UPSERT",
            demand_id=record.demand_id,
            requested_by=principal.actor,
            target_version=record.version,
            target_content_sha256=record.content_sha256,
            trace_id=_trace_id(request),
        )
        result = DemandOut.model_validate(record)
    _process_demand_index_event(
        request,
        db,
        event.event_id,
        operation="UPSERT",
        demand_id=record.demand_id,
    )
    return result


@api_router.put("/demands/{demand_id}", response_model=DemandOut)
def replace_demand(
    demand_id: str,
    payload: DemandUpdate,
    request: Request,
    db: DbSession,
    principal: StrictAdminPrincipal,
) -> DemandOut:
    with db.begin():
        record, changed = update_demand(db, demand_id, payload)
        result = DemandOut.model_validate(record)
        event = (
            create_index_event(
                db,
                operation="UPSERT",
                demand_id=record.demand_id,
                requested_by=principal.actor,
                target_version=record.version,
                target_content_sha256=record.content_sha256,
                trace_id=_trace_id(request),
            )
            if changed
            else None
        )
    if event is None:
        return result
    _process_demand_index_event(
        request,
        db,
        event.event_id,
        operation="UPSERT",
        demand_id=record.demand_id,
    )
    return result


@api_router.post("/demands/{demand_id}/deactivate", response_model=DemandOut)
def remove_demand_from_matching(
    demand_id: str,
    request: Request,
    db: DbSession,
    principal: StrictAdminPrincipal,
) -> DemandOut:
    with db.begin():
        record, changed = deactivate_demand(db, demand_id)
        result = DemandOut.model_validate(record)
        event = (
            create_index_event(
                db,
                operation="DELETE",
                demand_id=record.demand_id,
                requested_by=principal.actor,
                target_version=record.version,
                target_content_sha256=record.content_sha256,
                trace_id=_trace_id(request),
            )
            if changed
            else None
        )
    if event is None:
        return result
    _process_demand_index_event(
        request,
        db,
        event.event_id,
        operation="DELETE",
        demand_id=record.demand_id,
    )
    return result


@api_router.post("/demands/index/sync", response_model=DemandIndexSyncOut)
def reconcile_demand_index(
    request: Request,
    db: DbSession,
    principal: StrictAdminPrincipal,
) -> DemandIndexSyncOut:
    with db.begin():
        event = create_index_event(
            db,
            operation="SYNC_ALL",
            requested_by=principal.actor,
            trace_id=_trace_id(request),
        )
    result = _process_demand_index_event(
        request,
        db,
        event.event_id,
        operation="SYNC_ALL",
    )
    if result is None:
        raise DomainError(
            "DEMAND_INDEX_NOT_CONFIGURED",
            "현재 Match Provider에는 Demand 검색 인덱스가 없습니다.",
            409,
        )
    return DemandIndexSyncOut(
        provider=_demand_index(request).provider_name,
        upserted=result.upserted,
        deleted=result.deleted,
    )


@api_router.get("/demands/index/events", response_model=list[DemandIndexEventOut])
def read_demand_index_events(
    db: DbSession,
    _principal: StrictAdminPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DemandIndexEventOut]:
    return [DemandIndexEventOut.model_validate(item) for item in list_index_events(db, limit=limit)]


@api_router.post(
    "/demands/index/events/{event_id}/retry",
    response_model=DemandIndexEventOut,
    status_code=201,
)
def retry_demand_index_event(
    event_id: str,
    request: Request,
    db: DbSession,
    principal: StrictAdminPrincipal,
) -> DemandIndexEventOut:
    with db.begin():
        event = create_index_event_retry(
            db,
            event_id,
            requested_by=principal.actor,
            trace_id=_trace_id(request),
        )
        retry_event_id = event.event_id
        operation = event.operation
        demand_id = event.demand_id
    _process_demand_index_event(
        request,
        db,
        retry_event_id,
        operation=operation,
        demand_id=demand_id,
    )
    with db.begin():
        completed = db.get(type(event), retry_event_id)
        if completed is None:
            raise RuntimeError("Completed Demand index event is missing")
        return DemandIndexEventOut.model_validate(completed)


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
    provider = _match_provider(request)
    with db.begin():
        prepared = prepare_match(
            db,
            case_id,
            provider,
            top_k=payload.top_k,
            idempotency_key=idempotency_key,
            rule_policy_key=settings.match_rule_policy_key,
            pending_timeout_seconds=settings.match_pending_timeout_seconds,
        )
        if prepared.already_completed:
            record = get_case(db, case_id)
            return build_case_envelope(db, record)

    try:
        provider_result = provider.match(prepared.passport_input, top_k=payload.top_k)
    except Exception as exc:
        logger.error(
            "Match provider failed case_id=%s error_type=%s",
            case_id,
            type(exc).__name__,
        )
        with db.begin():
            fail_match(
                db,
                prepared.match_run_id,
                error_code="PROVIDER_UNAVAILABLE",
                execution_token=prepared.execution_token,
            )
        raise DomainError(
            "MATCH_UNAVAILABLE",
            "Match 서비스를 일시적으로 사용할 수 없습니다.",
            503,
        ) from exc

    with db.begin():
        completion = complete_match(
            db,
            case_id,
            prepared,
            provider_result,
            actor=principal.actor,
            trace_id=_trace_id(request),
        )
        response = build_case_envelope(db, completion.record) if completion.error is None else None
    if completion.error is not None:
        raise completion.error
    return response


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
def reset_demo(request: Request, db: DbSession, _principal: StrictAdminPrincipal) -> CaseEnvelope:
    if not settings.demo_mode or not settings.demo_reset_enabled:
        raise DomainError("NOT_FOUND", "Demo reset을 사용할 수 없습니다.", 404)
    storage = _evidence_storage(request)
    with db.begin():
        storage_keys = evidence_storage_keys_for_case(db, GOLDEN_CASE_ID)
        record = reset_demo_data(db)
        event = create_index_event(
            db,
            operation="SYNC_ALL",
            requested_by=_principal.actor,
            trace_id=_trace_id(request),
        )
        result = build_case_envelope(db, record)
    _process_demand_index_event(
        request,
        db,
        event.event_id,
        operation="SYNC_ALL",
    )
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
    if policy_key == settings.match_rule_policy_key:
        raise DomainError(
            "RULE_POLICY_RESERVED",
            "내장 Match evaluator policy는 애플리케이션 버전과 함께 관리됩니다.",
            409,
        )
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
    if policy_key == settings.match_rule_policy_key:
        raise DomainError(
            "RULE_POLICY_RESERVED",
            "내장 Match evaluator policy는 애플리케이션 버전과 함께 관리됩니다.",
            409,
        )
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
    try:
        provider.ready()
    except Exception as exc:
        raise DomainError(
            "MATCH_UNAVAILABLE",
            "설정된 Match Provider를 사용할 수 없습니다.",
            503,
        ) from exc
    return HealthOut(
        status="ready",
        database="ok",
        match_provider=provider.__class__.__name__,
        evidence_storage=storage.__class__.__name__,
    )
