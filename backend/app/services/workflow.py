"""Transactional workflow orchestration for the GreenFab Loop MVP."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, func, nullslast, select
from sqlalchemy.orm import Session, selectinload

from app.enums import (
    DecisionStatus,
    HandoffStatus,
    MatchCandidateStatus,
    MatchRunStatus,
    ResourceConfirmationStatus,
    SourceType,
    WorkflowStatus,
)
from app.errors import DomainError
from app.models import (
    AuditEvent,
    Case,
    Decision,
    Demand,
    ESGScenario,
    MatchCandidate,
    MatchRun,
    Receipt,
    ResourcePassport,
)
from app.schemas import (
    CaseEnvelope,
    CaseOut,
    CaseSummary,
    DecisionOut,
    DecisionRequest,
    ESGScenarioOut,
    MatchCandidateOut,
    MatchOut,
    ReceiptOut,
    ResourceConfirmationOut,
    ResourceConfirmationRequest,
    ResourcePassportOut,
    ResourcePassportRequest,
    RuleCheckOut,
    ShapFeature,
)
from app.services.match import MatchProvider
from app.services.rules import ResourcePassportInput

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def list_case_summaries(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    workflow_status: WorkflowStatus | None = None,
) -> tuple[list[CaseSummary], int]:
    filters = []
    if search:
        filters.append(Case.case_id.icontains(search.strip(), autoescape=True))
    if workflow_status is not None:
        filters.append(Case.workflow_status == workflow_status)
    total = session.scalar(select(func.count()).select_from(Case).where(*filters)) or 0
    records = session.scalars(
        select(Case)
        .where(*filters)
        .order_by(nullslast(Case.risk_rank.asc()), Case.case_id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    summaries = [
        CaseSummary(
            case_id=record.case_id,
            risk_rank=record.risk_rank,
            source_type=record.source_type,
            workflow_status=record.workflow_status,
            updated_at=record.updated_at,
        )
        for record in records
    ]
    return summaries, total


def get_case(session: Session, case_id: str) -> Case:
    record = session.get(Case, case_id)
    if record is None:
        raise DomainError(
            code="CASE_NOT_FOUND",
            message=f"Case {case_id}를 찾을 수 없습니다.",
            status_code=404,
        )
    return record


def get_case_for_update(session: Session, case_id: str) -> Case:
    """Lock a workflow row while applying a state transition on PostgreSQL."""

    record = session.scalar(select(Case).where(Case.case_id == case_id).with_for_update())
    if record is None:
        raise DomainError(
            code="CASE_NOT_FOUND",
            message=f"Case {case_id}를 찾을 수 없습니다.",
            status_code=404,
        )
    return record


def get_case_envelope(session: Session, case_id: str) -> CaseEnvelope:
    record = get_case(session, case_id)
    return build_case_envelope(session, record)


def build_case_envelope(session: Session, record: Case) -> CaseEnvelope:
    confirmation = record.resource_confirmation
    if confirmation is None:
        raise DomainError(
            code="INTEGRITY_ERROR",
            message="Case의 현장 확인 상태가 초기화되지 않았습니다.",
            status_code=500,
        )

    passport = record.resource_passport
    match_run = _latest_completed_match(session, record.case_id)
    decision = record.decision
    scenario = record.esg_scenario
    receipt = record.receipt

    shap_features = (
        [ShapFeature.model_validate(item) for item in record.shap_top_features]
        if record.shap_top_features is not None
        else None
    )

    match_output: MatchOut | None = None
    if match_run is not None:
        match_output = MatchOut(
            model=match_run.model,
            created_at=match_run.completed_at or match_run.created_at,
            source_type=match_run.source_type,
            candidates=[
                MatchCandidateOut(
                    demand_id=candidate.demand_id,
                    company_name=candidate.demand.company_name,
                    demand_description=candidate.demand.demand_description,
                    semantic_similarity=candidate.semantic_similarity,
                    rule_check=RuleCheckOut.model_validate(candidate.rule_check),
                    status=candidate.status,
                )
                for candidate in match_run.candidates
            ],
        )

    return CaseEnvelope(
        case=CaseOut(
            case_id=record.case_id,
            risk_rank=record.risk_rank,
            shap_top_features=shap_features,
            source_type=record.source_type,
        ),
        resource_confirmation=ResourceConfirmationOut(
            status=confirmation.status,
            confirmed_by=confirmation.confirmed_by,
            confirmed_at=confirmation.confirmed_at,
            source_type=confirmation.source_type,
        ),
        resource_passport=(
            ResourcePassportOut(
                passport_id=passport.passport_id,
                description=passport.description,
                quantity=_number(passport.quantity),
                unit=passport.unit,
                condition=passport.condition,
                location=passport.location,
                composition=passport.composition,
                source_type=passport.source_type,
            )
            if passport is not None
            else None
        ),
        match=match_output,
        decision=(
            DecisionOut(
                status=decision.status,
                selected_demand_id=decision.selected_demand_id,
                reason=decision.reason,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
            )
            if decision is not None
            else None
        ),
        esg_scenario=(
            ESGScenarioOut(
                source_type=scenario.source_type,
                inputs=scenario.inputs,
                results=scenario.results,
                formula_version=scenario.formula_version,
                factor_source=scenario.factor_source,
            )
            if scenario is not None
            else None
        ),
        receipt=(
            ReceiptOut(
                receipt_id=receipt.receipt_id,
                case_id=receipt.case_id,
                passport_id=receipt.passport_id,
                selected_demand_id=receipt.selected_demand_id,
                decision_status=receipt.decision_status,
                handoff_status=receipt.handoff_status,
                created_at=receipt.created_at,
            )
            if receipt is not None
            else None
        ),
    )


def confirm_resource(
    session: Session,
    case_id: str,
    payload: ResourceConfirmationRequest,
    *,
    actor: str | None = None,
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    confirmation = record.resource_confirmation
    if confirmation is None:
        raise DomainError("INTEGRITY_ERROR", "현장 확인 레코드가 없습니다.", 500)

    effective_actor = (actor or payload.confirmed_by or "").strip()
    if not effective_actor:
        raise DomainError("INVALID_ACTOR", "현장 확인 담당자가 필요합니다.", 422)

    if confirmation.status is payload.status and confirmation.confirmed_by == effective_actor:
        return record

    _require_status(
        record,
        {WorkflowStatus.DETECTED, WorkflowStatus.CONFIRMATION_PENDING},
        "현장 확인 상태를 변경할 수 없는 단계입니다.",
    )

    before = record.workflow_status
    confirmation.status = payload.status
    confirmation.confirmed_by = effective_actor
    confirmation.confirmed_at = utcnow()

    if payload.status is ResourceConfirmationStatus.CONFIRMED:
        record.workflow_status = WorkflowStatus.RESOURCE_CONFIRMED
    else:
        record.workflow_status = WorkflowStatus.CLOSED

    _audit(
        session,
        record,
        event_type="RESOURCE_CONFIRMATION_RECORDED",
        actor=effective_actor,
        before=before,
        payload={"status": payload.status.value},
        trace_id=trace_id,
    )
    session.flush()
    return record


def save_passport(
    session: Session,
    case_id: str,
    payload: ResourcePassportRequest,
    *,
    actor: str = "demo_operator",
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    _require_status(
        record,
        {WorkflowStatus.RESOURCE_CONFIRMED, WorkflowStatus.PASSPORT_READY},
        "자원 발생 확인 후에만 Passport를 저장할 수 있습니다.",
    )

    before = record.workflow_status
    passport = record.resource_passport
    if passport is None:
        suffix = case_id.removeprefix("SECOM-")
        passport = ResourcePassport(
            passport_id=f"PASSPORT-DEMO-{suffix}",
            case_id=case_id,
            source_type=SourceType.DEMO,
        )
        record.resource_passport = passport

    for field_name, value in payload.model_dump().items():
        setattr(passport, field_name, value.strip() if isinstance(value, str) else value)

    record.workflow_status = WorkflowStatus.PASSPORT_READY
    _audit(
        session,
        record,
        event_type="RESOURCE_PASSPORT_SAVED",
        actor=actor,
        before=before,
        payload={"passport_id": passport.passport_id},
        trace_id=trace_id,
    )
    session.flush()
    return record


def run_match(
    session: Session,
    case_id: str,
    provider: MatchProvider,
    *,
    top_k: int,
    idempotency_key: str | None = None,
    actor: str = "demo_operator",
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    _require_status(
        record,
        {WorkflowStatus.PASSPORT_READY, WorkflowStatus.MATCH_READY},
        "Passport 저장 후에만 Match를 실행할 수 있습니다.",
    )
    passport = record.resource_passport
    if passport is None:
        raise DomainError("INVALID_STATE", "저장된 Passport가 없습니다.", 409)

    if idempotency_key:
        existing = session.scalar(
            select(MatchRun).where(
                MatchRun.case_id == case_id,
                MatchRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return record

    passport_input = ResourcePassportInput(
        passport_id=passport.passport_id,
        description=passport.description,
        quantity=_number(passport.quantity),
        unit=passport.unit,
        condition=passport.condition,
        location=passport.location,
        composition=passport.composition,
        source_type=passport.source_type.value,
    )
    try:
        result = provider.match(passport_input, top_k=top_k)
    except (RuntimeError, ValueError) as exc:
        logger.error(
            "Match provider failed case_id=%s error_type=%s",
            case_id,
            type(exc).__name__,
        )
        raise DomainError(
            "MATCH_UNAVAILABLE",
            "Match 서비스를 일시적으로 사용할 수 없습니다.",
            503,
        ) from exc

    before = record.workflow_status
    completed_at = utcnow()
    match_run = MatchRun(
        case_id=case_id,
        passport_id=passport.passport_id,
        model=result.model,
        model_revision=result.snapshot_id,
        top_k=top_k,
        status=MatchRunStatus.COMPLETED,
        source_type=SourceType.DEMO,
        idempotency_key=idempotency_key,
        completed_at=completed_at,
    )
    session.add(match_run)
    session.flush()

    demand_ids = {candidate.demand_id for candidate in result.candidates}
    demands = {
        demand.demand_id: demand
        for demand in session.scalars(select(Demand).where(Demand.demand_id.in_(demand_ids))).all()
    }
    missing_demands = demand_ids - demands.keys()
    if missing_demands:
        raise DomainError(
            "MATCH_DATA_ERROR",
            f"Demand seed가 없습니다: {', '.join(sorted(missing_demands))}",
            500,
        )

    for candidate in result.candidates:
        session.add(
            MatchCandidate(
                match_run_id=match_run.match_run_id,
                demand_id=candidate.demand_id,
                rank=candidate.rank,
                semantic_similarity=candidate.semantic_similarity,
                rule_check=candidate.rule_check.as_dict(),
                status=MatchCandidateStatus(candidate.status),
            )
        )

    record.workflow_status = WorkflowStatus.MATCH_READY
    _audit(
        session,
        record,
        event_type="MATCH_COMPLETED",
        actor=actor,
        before=before,
        payload={
            "match_run_id": match_run.match_run_id,
            "model": result.model,
            "snapshot_id": result.snapshot_id,
            "top_k": top_k,
        },
        trace_id=trace_id,
    )
    session.flush()
    return record


def save_decision(
    session: Session,
    case_id: str,
    payload: DecisionRequest,
    *,
    actor: str | None = None,
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    _require_status(
        record,
        {WorkflowStatus.MATCH_READY, WorkflowStatus.DECIDED},
        "Match 완료 후에만 Decision을 기록할 수 있습니다.",
    )
    match_run = _latest_completed_match(session, case_id)
    if match_run is None:
        raise DomainError("INVALID_STATE", "완료된 Match가 없습니다.", 409)

    selected: MatchCandidate | None = None
    if payload.selected_demand_id:
        selected = next(
            (
                candidate
                for candidate in match_run.candidates
                if candidate.demand_id == payload.selected_demand_id
            ),
            None,
        )
        if selected is None:
            raise DomainError(
                "INVALID_CANDIDATE",
                "선택한 Demand가 최신 Match 후보에 없습니다.",
                409,
            )

    if payload.status is DecisionStatus.APPROVED:
        if selected is None or selected.status is not MatchCandidateStatus.REVIEW:
            raise DomainError(
                "CANDIDATE_NOT_REVIEWABLE",
                "APPROVED는 REVIEW 상태 후보에만 기록할 수 있습니다.",
                409,
            )

    effective_actor = (actor or payload.decided_by or "").strip()
    if not effective_actor:
        raise DomainError("INVALID_ACTOR", "Decision 담당자가 필요합니다.", 422)

    before = record.workflow_status
    decision = record.decision
    if decision is None:
        decision = Decision(case_id=case_id)
        record.decision = decision
    decision.status = payload.status
    decision.selected_demand_id = payload.selected_demand_id
    decision.selected_match_candidate_id = (
        selected.match_candidate_id if selected is not None else None
    )
    decision.reason = payload.reason.strip()
    decision.decided_by = effective_actor
    decision.decided_at = utcnow()
    record.workflow_status = WorkflowStatus.DECIDED

    _audit(
        session,
        record,
        event_type="HUMAN_DECISION_RECORDED",
        actor=effective_actor,
        before=before,
        payload={
            "status": payload.status.value,
            "selected_demand_id": payload.selected_demand_id,
            "selected_match_candidate_id": (
                selected.match_candidate_id if selected is not None else None
            ),
        },
        trace_id=trace_id,
    )
    session.flush()
    return record


def create_esg_scenario(
    session: Session,
    case_id: str,
    *,
    actor: str = "demo_operator",
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    _require_status(
        record,
        {WorkflowStatus.DECIDED, WorkflowStatus.SCENARIO_READY},
        "Decision 기록 후에만 ESG Scenario를 생성할 수 있습니다.",
    )
    if record.esg_scenario is not None:
        return record
    if record.decision is None or record.resource_passport is None:
        raise DomainError("INVALID_STATE", "Decision 또는 Passport가 없습니다.", 409)

    before = record.workflow_status
    quantity = _number(record.resource_passport.quantity)
    diversion = quantity if record.decision.status is DecisionStatus.APPROVED else 0
    scenario = ESGScenario(
        case_id=case_id,
        decision_id=record.decision.decision_id,
        source_type=SourceType.SCENARIO,
        inputs={
            "resource_quantity": quantity,
            "unit": record.resource_passport.unit,
            "decision_status": record.decision.status.value,
        },
        results={
            # Unknown input stays unknown. Zero is reserved for a deliberate
            # HOLD/REJECTED decision, not for an absent quantity measurement.
            "candidate_diversion_quantity": diversion,
            "unit": record.resource_passport.unit,
        },
        formula_version="candidate_diversion_v0.1",
        factor_source=None,
    )
    record.esg_scenario = scenario
    record.workflow_status = WorkflowStatus.SCENARIO_READY
    _audit(
        session,
        record,
        event_type="ESG_SCENARIO_CREATED",
        actor=actor,
        before=before,
        payload={"formula_version": scenario.formula_version},
        trace_id=trace_id,
    )
    session.flush()
    return record


def create_receipt(
    session: Session,
    case_id: str,
    *,
    idempotency_key: str | None = None,
    actor: str = "demo_operator",
    trace_id: str | None = None,
) -> Case:
    record = get_case_for_update(session, case_id)
    _require_status(
        record,
        {WorkflowStatus.SCENARIO_READY, WorkflowStatus.RECEIPT_CREATED},
        "ESG Scenario 생성 후에만 Receipt를 만들 수 있습니다.",
    )
    if record.receipt is not None:
        if (
            idempotency_key
            and record.receipt.idempotency_key
            and idempotency_key != record.receipt.idempotency_key
        ):
            raise DomainError(
                "RECEIPT_ALREADY_EXISTS",
                "이 Case의 Receipt가 이미 생성되었습니다.",
                409,
            )
        return record
    if record.resource_passport is None or record.decision is None or record.esg_scenario is None:
        raise DomainError("INVALID_STATE", "Passport, Decision 또는 ESG Scenario가 없습니다.", 409)

    before = record.workflow_status
    decision = record.decision
    handoff_status = (
        HandoffStatus.APPROVED
        if decision.status is DecisionStatus.APPROVED
        else HandoffStatus.RESOURCE_CONFIRMED
    )
    receipt = Receipt(
        receipt_id=f"RECEIPT-{uuid4().hex[:16].upper()}",
        case_id=case_id,
        decision_id=decision.decision_id,
        scenario_id=record.esg_scenario.scenario_id,
        passport_id=record.resource_passport.passport_id,
        selected_demand_id=decision.selected_demand_id,
        decision_status=decision.status,
        handoff_status=handoff_status,
        payload_json={},
        idempotency_key=idempotency_key,
    )
    record.receipt = receipt
    record.workflow_status = WorkflowStatus.RECEIPT_CREATED
    session.flush()

    # The persisted snapshot deliberately contains the contract envelope only;
    # it is an MVP decision record, not a legal certificate or immutable ledger.
    receipt.payload_json = build_case_envelope(session, record).model_dump(mode="json")
    _audit(
        session,
        record,
        event_type="GREEN_RECEIPT_CREATED",
        actor=actor,
        before=before,
        payload={"receipt_id": receipt.receipt_id},
        trace_id=trace_id,
    )
    session.flush()
    return record


def _latest_completed_match(session: Session, case_id: str) -> MatchRun | None:
    statement: Select[tuple[MatchRun]] = (
        select(MatchRun)
        .where(
            MatchRun.case_id == case_id,
            MatchRun.status == MatchRunStatus.COMPLETED,
        )
        .options(selectinload(MatchRun.candidates).selectinload(MatchCandidate.demand))
        .order_by(
            nullslast(MatchRun.completed_at.desc()),
            MatchRun.created_at.desc(),
            MatchRun.match_run_id.desc(),
        )
        .limit(1)
    )
    return session.scalar(statement)


def _require_status(
    record: Case,
    allowed: set[WorkflowStatus],
    message: str,
) -> None:
    if record.workflow_status not in allowed:
        raise DomainError(
            code="INVALID_STATE",
            message=message,
            status_code=409,
            field_errors=[
                {
                    "field": "workflow_status",
                    "message": f"현재 상태: {record.workflow_status.value}",
                }
            ],
        )


def _audit(
    session: Session,
    record: Case,
    *,
    event_type: str,
    actor: str,
    before: WorkflowStatus,
    payload: dict[str, Any],
    trace_id: str | None,
) -> None:
    session.add(
        AuditEvent(
            case_id=record.case_id,
            event_type=event_type,
            actor=actor,
            from_status=before,
            to_status=record.workflow_status,
            payload_json=payload,
            trace_id=trace_id,
        )
    )


def _number(value: Decimal | float | int | None) -> float | None:
    return float(value) if value is not None else None
