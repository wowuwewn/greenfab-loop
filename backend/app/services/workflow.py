"""Transactional workflow orchestration for the GreenFab Loop MVP."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite
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
    RulePolicyLineageOut,
    ShapFeature,
)
from app.services.demand import demand_content_sha256, demand_snapshot_payload
from app.services.match import MatchProvider, MatchResult
from app.services.rule_catalog import get_active_rule_policy_snapshot
from app.services.rules import DemandRules, ResourcePassportInput, evaluate_rules

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedMatch:
    match_run_id: str
    passport_input: ResourcePassportInput
    passport_snapshot_sha256: str
    workflow_status: WorkflowStatus
    execution_token: str
    already_completed: bool = False


@dataclass(frozen=True, slots=True)
class MatchCompletion:
    record: Case
    error: DomainError | None = None


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
            model_revision=match_run.model_revision,
            created_at=match_run.completed_at or match_run.created_at,
            source_type=match_run.source_type,
            rule_policy=RulePolicyLineageOut(
                policy_key=match_run.rule_policy_key,
                version=match_run.rule_policy_version,
                definition_sha256=match_run.rule_policy_definition_sha256,
            ),
            candidates=[
                MatchCandidateOut(
                    demand_id=candidate.demand_id,
                    company_name=(
                        candidate.demand_snapshot_json.get("company_name")
                        or candidate.demand.company_name
                    ),
                    demand_description=(
                        candidate.demand_snapshot_json.get("demand_description")
                        or candidate.demand.demand_description
                    ),
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


def prepare_match(
    session: Session,
    case_id: str,
    provider: MatchProvider,
    *,
    top_k: int,
    idempotency_key: str | None = None,
    rule_policy_key: str,
    pending_timeout_seconds: int = 120,
) -> PreparedMatch:
    """Reserve a MatchRun and snapshot inputs in a short DB transaction."""

    record = get_case_for_update(session, case_id)
    passport = record.resource_passport
    if passport is None:
        raise DomainError("INVALID_STATE", "저장된 Passport가 없습니다.", 409)

    existing: MatchRun | None = None
    if idempotency_key:
        existing = session.scalar(
            select(MatchRun).where(
                MatchRun.case_id == case_id,
                MatchRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.top_k != top_k:
                raise DomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "같은 Idempotency-Key를 다른 Match 요청에 재사용할 수 없습니다.",
                    409,
                )
            if existing.status is MatchRunStatus.COMPLETED:
                latest_completed_id = session.scalar(
                    select(MatchRun.match_run_id)
                    .where(
                        MatchRun.case_id == case_id,
                        MatchRun.status == MatchRunStatus.COMPLETED,
                    )
                    .order_by(
                        nullslast(MatchRun.completed_at.desc()),
                        MatchRun.created_at.desc(),
                        MatchRun.match_run_id.desc(),
                    )
                    .limit(1)
                )
                if latest_completed_id != existing.match_run_id:
                    raise DomainError(
                        "IDEMPOTENCY_KEY_STALE",
                        "이 Idempotency-Key보다 최신 Match가 있어 "
                        "과거 응답을 현재 Case로 반환할 수 없습니다.",
                        409,
                    )
                return PreparedMatch(
                    match_run_id=existing.match_run_id,
                    passport_input=_passport_input(passport),
                    passport_snapshot_sha256=existing.passport_snapshot_sha256,
                    workflow_status=record.workflow_status,
                    execution_token=existing.execution_token,
                    already_completed=True,
                )
            if existing.status is MatchRunStatus.PENDING:
                created_at = existing.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                if (utcnow() - created_at).total_seconds() < pending_timeout_seconds:
                    raise DomainError(
                        "MATCH_IN_PROGRESS",
                        "같은 Idempotency-Key의 Match가 이미 진행 중입니다.",
                        409,
                    )

    _require_status(
        record,
        {WorkflowStatus.PASSPORT_READY, WorkflowStatus.MATCH_READY},
        "Passport 저장 후에만 Match를 실행할 수 있습니다.",
    )

    passport_input = _passport_input(passport)
    passport_snapshot = _passport_snapshot(passport_input)
    passport_hash = _sha256_json(passport_snapshot)
    policy = get_active_rule_policy_snapshot(session, rule_policy_key)
    provider_model = str(getattr(provider, "model_name", provider.__class__.__name__))
    provider_revision = str(getattr(provider, "snapshot_id", "unversioned"))
    execution_token = uuid4().hex

    if existing is None:
        match_run = MatchRun(
            case_id=case_id,
            passport_id=passport.passport_id,
            model=provider_model,
            model_revision=provider_revision,
            top_k=top_k,
            status=MatchRunStatus.PENDING,
            source_type=passport.source_type,
            idempotency_key=idempotency_key,
            execution_token=execution_token,
            passport_snapshot_json=passport_snapshot,
            passport_snapshot_sha256=passport_hash,
            rule_policy_key=policy.policy_key,
            rule_policy_version=policy.version,
            rule_policy_definition_sha256=policy.definition_sha256,
        )
        session.add(match_run)
    else:
        match_run = existing
        match_run.model = provider_model
        match_run.model_revision = provider_revision
        match_run.top_k = top_k
        match_run.status = MatchRunStatus.PENDING
        match_run.source_type = passport.source_type
        match_run.completed_at = None
        match_run.error_message = None
        match_run.execution_token = execution_token
        match_run.created_at = utcnow()
        match_run.passport_snapshot_json = passport_snapshot
        match_run.passport_snapshot_sha256 = passport_hash
        match_run.rule_policy_key = policy.policy_key
        match_run.rule_policy_version = policy.version
        match_run.rule_policy_definition_sha256 = policy.definition_sha256
    session.flush()
    return PreparedMatch(
        match_run_id=match_run.match_run_id,
        passport_input=passport_input,
        passport_snapshot_sha256=passport_hash,
        workflow_status=record.workflow_status,
        execution_token=execution_token,
    )


def fail_match(
    session: Session,
    match_run_id: str,
    *,
    error_code: str,
    execution_token: str | None = None,
) -> None:
    """Persist a safe failure marker without retaining provider internals."""

    match_run = session.scalar(
        select(MatchRun).where(MatchRun.match_run_id == match_run_id).with_for_update()
    )
    if (
        match_run is None
        or match_run.status is MatchRunStatus.COMPLETED
        or (execution_token is not None and match_run.execution_token != execution_token)
    ):
        return
    match_run.status = MatchRunStatus.FAILED
    match_run.completed_at = utcnow()
    match_run.error_message = error_code
    session.flush()


def complete_match(
    session: Session,
    case_id: str,
    prepared: PreparedMatch,
    result: MatchResult,
    *,
    actor: str,
    trace_id: str | None = None,
) -> MatchCompletion:
    """Persist provider output after verifying immutable input snapshots."""

    record = get_case_for_update(session, case_id)
    match_run = session.scalar(
        select(MatchRun).where(MatchRun.match_run_id == prepared.match_run_id).with_for_update()
    )
    if match_run is None:
        raise DomainError("MATCH_RUN_NOT_FOUND", "예약된 MatchRun이 없습니다.", 409)
    if match_run.status is MatchRunStatus.COMPLETED:
        return MatchCompletion(record)
    if match_run.status is not MatchRunStatus.PENDING:
        raise DomainError("MATCH_NOT_PENDING", "MatchRun이 완료 가능한 상태가 아닙니다.", 409)
    if match_run.execution_token != prepared.execution_token:
        raise DomainError(
            "MATCH_ATTEMPT_SUPERSEDED",
            "이 Match 시도는 더 최신 재시도로 대체되었습니다.",
            409,
        )

    if record.workflow_status is not prepared.workflow_status:
        fail_match(
            session,
            match_run.match_run_id,
            error_code="CASE_CHANGED",
            execution_token=prepared.execution_token,
        )
        return MatchCompletion(
            record,
            DomainError(
                "CASE_CHANGED_DURING_MATCH",
                "Match 실행 중 Case 단계가 변경되었습니다. 현재 상태에서 다시 확인해 주세요.",
                409,
            ),
        )

    passport = record.resource_passport
    current_hash = (
        _sha256_json(_passport_snapshot(_passport_input(passport)))
        if passport is not None
        else None
    )
    if current_hash != prepared.passport_snapshot_sha256:
        fail_match(
            session,
            match_run.match_run_id,
            error_code="PASSPORT_CHANGED",
            execution_token=prepared.execution_token,
        )
        return MatchCompletion(
            record,
            DomainError(
                "PASSPORT_CHANGED_DURING_MATCH",
                "Match 실행 중 Passport가 변경되었습니다. 다시 실행해 주세요.",
                409,
            ),
        )

    if not _valid_provider_candidates(result, match_run.top_k):
        fail_match(
            session,
            match_run.match_run_id,
            error_code="PROVIDER_RESULT_INVALID",
            execution_token=prepared.execution_token,
        )
        return MatchCompletion(
            record,
            DomainError(
                "MATCH_UNAVAILABLE",
                "Match Provider가 유효한 후보 형식을 반환하지 않았습니다.",
                503,
            ),
        )

    demand_ids = {candidate.demand_id for candidate in result.candidates}
    demands = {
        demand.demand_id: demand
        for demand in session.scalars(
            select(Demand)
            .where(Demand.demand_id.in_(demand_ids))
            .order_by(Demand.demand_id.asc())
            .with_for_update()
        ).all()
    }
    missing_demands = demand_ids - demands.keys()
    changed_demands = {
        candidate.demand_id
        for candidate in result.candidates
        if candidate.demand_id in demands
        and not _candidate_matches_current_demand(candidate, demands[candidate.demand_id])
    }
    if missing_demands or changed_demands:
        fail_match(
            session,
            match_run.match_run_id,
            error_code="DEMAND_CHANGED",
            execution_token=prepared.execution_token,
        )
        return MatchCompletion(
            record,
            DomainError(
                "DEMAND_CHANGED_DURING_MATCH",
                "Match 실행 중 Demand가 변경되었습니다. 인덱스 동기화 후 다시 실행해 주세요.",
                409,
            ),
        )

    before = record.workflow_status
    match_run.model = result.model
    match_run.model_revision = result.snapshot_id
    match_run.source_type = (
        SourceType.DEMO
        if prepared.passport_input.source_type == SourceType.DEMO.value
        or any(demand.source_type is SourceType.DEMO for demand in demands.values())
        else SourceType.REAL
    )
    match_run.status = MatchRunStatus.COMPLETED
    match_run.completed_at = utcnow()
    match_run.error_message = None

    for candidate in result.candidates:
        demand = demands[candidate.demand_id]
        verified_rule_check = evaluate_rules(
            prepared.passport_input,
            _demand_rules(demand),
        )
        snapshot = demand_snapshot_payload(demand)
        snapshot["content_sha256"] = demand.content_sha256 or demand_content_sha256(demand)
        snapshot["rule_check"] = verified_rule_check.as_dict()
        session.add(
            MatchCandidate(
                match_run_id=match_run.match_run_id,
                demand_id=candidate.demand_id,
                rank=candidate.rank,
                semantic_similarity=candidate.semantic_similarity,
                rule_check=verified_rule_check.as_dict(),
                demand_snapshot_json=snapshot,
                status=MatchCandidateStatus(verified_rule_check.status),
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
            "top_k": match_run.top_k,
            "rule_policy": {
                "policy_key": match_run.rule_policy_key,
                "version": match_run.rule_policy_version,
                "definition_sha256": match_run.rule_policy_definition_sha256,
            },
            "passport_snapshot_sha256": match_run.passport_snapshot_sha256,
        },
        trace_id=trace_id,
    )
    session.flush()
    return MatchCompletion(record)


def _passport_input(passport: ResourcePassport | None) -> ResourcePassportInput:
    if passport is None:
        raise DomainError("INVALID_STATE", "저장된 Passport가 없습니다.", 409)
    return ResourcePassportInput(
        passport_id=passport.passport_id,
        description=passport.description,
        quantity=_number(passport.quantity),
        unit=passport.unit,
        condition=passport.condition,
        location=passport.location,
        composition=passport.composition,
        source_type=passport.source_type.value,
    )


def _passport_snapshot(passport: ResourcePassportInput) -> dict[str, Any]:
    return {
        "passport_id": passport.passport_id,
        "description": passport.description,
        "quantity": passport.quantity,
        "unit": passport.unit,
        "condition": passport.condition,
        "location": passport.location,
        "composition": passport.composition,
        "source_type": passport.source_type,
    }


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_matches_current_demand(candidate: Any, demand: Demand) -> bool:
    if not demand.is_active:
        return False
    current_hash = demand.content_sha256 or demand_content_sha256(demand)
    current_rules = _demand_rules(demand)
    return (
        candidate.company_name == demand.company_name
        and candidate.demand_description == demand.demand_description
        and candidate.source_type == demand.source_type.value
        and candidate.demand_rules == current_rules
        and candidate.demand_version == demand.version
        and candidate.demand_content_sha256 == current_hash
    )


def _demand_rules(demand: Demand) -> DemandRules:
    return DemandRules(
        quantity_min=_number(demand.quantity_min),
        quantity_max=_number(demand.quantity_max),
        unit=demand.unit,
        accepted_locations=(demand.location,) if demand.location else (),
        required_fields=tuple(demand.required_fields),
    )


def _valid_provider_candidates(result: MatchResult, top_k: int) -> bool:
    candidates = result.candidates
    if len(candidates) > top_k:
        return False
    if [candidate.rank for candidate in candidates] != list(range(1, len(candidates) + 1)):
        return False
    if len({candidate.demand_id for candidate in candidates}) != len(candidates):
        return False
    try:
        return all(
            isfinite(float(candidate.semantic_similarity))
            and -1.0 <= float(candidate.semantic_similarity) <= 1.0
            for candidate in candidates
        )
    except (TypeError, ValueError):
        return False


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
        selected_demand = session.scalar(
            select(Demand).where(Demand.demand_id == selected.demand_id).with_for_update()
        )
        snapshot = selected.demand_snapshot_json
        snapshot_version = snapshot.get("version")
        snapshot_hash = snapshot.get("content_sha256")
        current_hash = (
            selected_demand.content_sha256 or demand_content_sha256(selected_demand)
            if selected_demand is not None
            else None
        )
        if (
            selected_demand is None
            or not selected_demand.is_active
            or snapshot_version != selected_demand.version
            or snapshot_hash != current_hash
        ):
            raise DomainError(
                "DEMAND_CHANGED_SINCE_MATCH",
                "선택한 Demand가 Match 이후 변경되었습니다. 다시 Match해 주세요.",
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
