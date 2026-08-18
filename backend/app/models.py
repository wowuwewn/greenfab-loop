"""Relational persistence models for the GreenFab Loop workflow."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.enums import (
    DecisionStatus,
    HandoffStatus,
    MatchCandidateStatus,
    MatchRunStatus,
    ResourceConfirmationStatus,
    SourceType,
    WorkflowStatus,
)


def _identifier(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _json_type() -> JSON:
    """Use JSONB on PostgreSQL while remaining portable to SQLite tests."""

    return JSON().with_variant(JSONB(), "postgresql")


def _bigint_pk() -> BigInteger:
    """Use PostgreSQL BIGINT while retaining SQLite rowid autoincrement."""

    return BigInteger().with_variant(Integer(), "sqlite")


def _enum(enum_class: type, name: str) -> SAEnum:
    """Store contract enums portably as checked VARCHAR values."""

    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Case(TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("risk_rank IS NULL OR risk_rank >= 1", name="ck_cases_risk_rank"),
        CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_cases_source_type"),
        CheckConstraint(
            "workflow_status IN ('DETECTED', 'CONFIRMATION_PENDING', "
            "'RESOURCE_CONFIRMED', 'PASSPORT_READY', 'MATCH_READY', 'DECIDED', "
            "'SCENARIO_READY', 'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_cases_workflow_status",
        ),
        Index("ix_cases_workflow_status", "workflow_status"),
    )

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    risk_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shap_top_features: Mapped[list[dict[str, Any]]] = mapped_column(
        _json_type(), default=list, nullable=False
    )
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False
    )
    workflow_status: Mapped[WorkflowStatus] = mapped_column(
        _enum(WorkflowStatus, "workflow_status"),
        default=WorkflowStatus.DETECTED,
        server_default=WorkflowStatus.DETECTED.value,
        nullable=False,
    )

    resource_confirmation: Mapped["ResourceConfirmation | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    resource_passport: Mapped["ResourcePassport | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    match_runs: Mapped[list["MatchRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    decision: Mapped["Decision | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    esg_scenario: Mapped["ESGScenario | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class ResourceConfirmation(TimestampMixin, Base):
    __tablename__ = "resource_confirmations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'NOT_CONFIRMED')",
            name="ck_resource_confirmations_status",
        ),
        CheckConstraint(
            "source_type IN ('REAL', 'DEMO')",
            name="ck_resource_confirmations_source_type",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR "
            "(status IN ('CONFIRMED', 'NOT_CONFIRMED') AND confirmed_by IS NOT NULL "
            "AND length(trim(confirmed_by)) > 0 AND confirmed_at IS NOT NULL)",
            name="ck_resource_confirmations_completed_fields",
        ),
    )

    confirmation_id: Mapped[int] = mapped_column(_bigint_pk(), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[ResourceConfirmationStatus] = mapped_column(
        _enum(ResourceConfirmationStatus, "resource_confirmation_status"),
        default=ResourceConfirmationStatus.PENDING,
        server_default=ResourceConfirmationStatus.PENDING.value,
        nullable=False,
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="resource_confirmation")


class ResourcePassport(TimestampMixin, Base):
    __tablename__ = "resource_passports"
    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_resource_passports_quantity"),
        CheckConstraint(
            "(quantity IS NULL AND unit IS NULL) OR "
            "(quantity IS NOT NULL AND unit IS NOT NULL AND length(trim(unit)) > 0)",
            name="ck_resource_passports_quantity_unit_pair",
        ),
        CheckConstraint(
            "source_type IN ('REAL', 'DEMO')",
            name="ck_resource_passports_source_type",
        ),
    )

    passport_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    composition: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="resource_passport")
    match_runs: Mapped[list["MatchRun"]] = relationship(back_populates="passport")


class Demand(TimestampMixin, Base):
    __tablename__ = "demands"
    __table_args__ = (
        CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0", name="ck_demands_quantity_min"
        ),
        CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= 0", name="ck_demands_quantity_max"
        ),
        CheckConstraint(
            "quantity_min IS NULL OR quantity_max IS NULL OR quantity_min <= quantity_max",
            name="ck_demands_quantity_range",
        ),
        CheckConstraint(
            "(quantity_min IS NULL AND quantity_max IS NULL) OR unit IS NOT NULL",
            name="ck_demands_quantity_unit",
        ),
        CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_demands_source_type"),
    )

    demand_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    demand_description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    quantity_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accepted_conditions: Mapped[list[str]] = mapped_column(
        _json_type(), default=list, nullable=False
    )
    required_fields: Mapped[list[str]] = mapped_column(_json_type(), default=list, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"),
        default=SourceType.DEMO,
        server_default=SourceType.DEMO.value,
        nullable=False,
    )


class MatchRun(Base):
    __tablename__ = "match_runs"
    __table_args__ = (
        UniqueConstraint("case_id", "idempotency_key", name="uq_match_runs_case_idempotency_key"),
        CheckConstraint("top_k > 0", name="ck_match_runs_top_k"),
        CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_match_runs_source_type"),
        CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_match_runs_status",
        ),
        Index("ix_match_runs_case_created_at", "case_id", "created_at"),
    )

    match_run_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: _identifier("MATCH")
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False
    )
    passport_id: Mapped[str] = mapped_column(
        ForeignKey("resource_passports.passport_id", ondelete="RESTRICT"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(255), nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[MatchRunStatus] = mapped_column(
        _enum(MatchRunStatus, "match_run_status"),
        default=MatchRunStatus.PENDING,
        server_default=MatchRunStatus.PENDING.value,
        nullable=False,
    )
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="match_runs")
    passport: Mapped[ResourcePassport] = relationship(back_populates="match_runs")
    candidates: Mapped[list["MatchCandidate"]] = relationship(
        back_populates="match_run",
        cascade="all, delete-orphan",
        order_by="MatchCandidate.rank",
    )


class MatchCandidate(Base):
    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("match_run_id", "demand_id", name="uq_match_candidate_demand"),
        UniqueConstraint("match_run_id", "rank", name="uq_match_candidate_rank"),
        CheckConstraint("rank > 0", name="ck_match_candidates_rank"),
        CheckConstraint(
            "semantic_similarity IS NULL OR "
            "(semantic_similarity >= -1 AND semantic_similarity <= 1)",
            name="ck_match_candidates_similarity",
        ),
        CheckConstraint(
            "status IN ('REVIEW', 'NEEDS_INFO', 'RULE_FAIL')",
            name="ck_match_candidates_status",
        ),
    )

    match_candidate_id: Mapped[int] = mapped_column(_bigint_pk(), primary_key=True)
    match_run_id: Mapped[str] = mapped_column(
        ForeignKey("match_runs.match_run_id", ondelete="CASCADE"), nullable=False
    )
    demand_id: Mapped[str] = mapped_column(
        ForeignKey("demands.demand_id", ondelete="RESTRICT"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    semantic_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_check: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict, nullable=False)
    status: Mapped[MatchCandidateStatus] = mapped_column(
        _enum(MatchCandidateStatus, "match_candidate_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    match_run: Mapped[MatchRun] = relationship(back_populates="candidates")
    demand: Mapped[Demand] = relationship()


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('APPROVED', 'HOLD', 'REJECTED')",
            name="ck_decisions_status",
        ),
        CheckConstraint(
            "status != 'APPROVED' OR "
            "(selected_demand_id IS NOT NULL AND selected_match_candidate_id IS NOT NULL)",
            name="ck_decisions_approved_fields",
        ),
        CheckConstraint("length(trim(reason)) > 0", name="ck_decisions_reason"),
        CheckConstraint("length(trim(decided_by)) > 0", name="ck_decisions_decided_by"),
    )

    decision_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: _identifier("DECISION")
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[DecisionStatus] = mapped_column(
        _enum(DecisionStatus, "decision_status"), nullable=False
    )
    selected_demand_id: Mapped[str | None] = mapped_column(
        ForeignKey("demands.demand_id", ondelete="RESTRICT"), nullable=True
    )
    selected_match_candidate_id: Mapped[int | None] = mapped_column(
        _bigint_pk(),
        ForeignKey("match_candidates.match_candidate_id", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case: Mapped[Case] = relationship(back_populates="decision")
    selected_demand: Mapped[Demand | None] = relationship()
    selected_match_candidate: Mapped[MatchCandidate | None] = relationship()


class ESGScenario(TimestampMixin, Base):
    __tablename__ = "esg_scenarios"
    __table_args__ = (
        CheckConstraint("source_type = 'SCENARIO'", name="ck_esg_scenarios_source_type"),
    )

    scenario_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: _identifier("SCENARIO")
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"),
        default=SourceType.SCENARIO,
        server_default=SourceType.SCENARIO.value,
        nullable=False,
    )
    inputs: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict, nullable=False)
    formula_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    factor_source: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="esg_scenario")
    decision: Mapped[Decision] = relationship()


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint(
            "decision_status IN ('APPROVED', 'HOLD', 'REJECTED')",
            name="ck_receipts_decision_status",
        ),
        CheckConstraint(
            "handoff_status IN ('RESOURCE_CONFIRMED', 'APPROVED', 'HANDOFF_CONFIRMED')",
            name="ck_receipts_handoff_status",
        ),
    )

    receipt_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: _identifier("RECEIPT")
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("decisions.decision_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("esg_scenarios.scenario_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    passport_id: Mapped[str] = mapped_column(
        ForeignKey("resource_passports.passport_id", ondelete="RESTRICT"), nullable=False
    )
    selected_demand_id: Mapped[str | None] = mapped_column(
        ForeignKey("demands.demand_id", ondelete="RESTRICT"), nullable=True
    )
    decision_status: Mapped[DecisionStatus] = mapped_column(
        _enum(DecisionStatus, "decision_status"), nullable=False
    )
    handoff_status: Mapped[HandoffStatus] = mapped_column(
        _enum(HandoffStatus, "handoff_status"), nullable=False
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="receipt")
    decision: Mapped[Decision] = relationship()
    scenario: Mapped[ESGScenario] = relationship()
    passport: Mapped[ResourcePassport] = relationship()
    selected_demand: Mapped[Demand | None] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('DETECTED', 'CONFIRMATION_PENDING', 'RESOURCE_CONFIRMED', "
            "'PASSPORT_READY', 'MATCH_READY', 'DECIDED', 'SCENARIO_READY', "
            "'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_audit_events_from_status",
        ),
        CheckConstraint(
            "to_status IS NULL OR to_status IN "
            "('DETECTED', 'CONFIRMATION_PENDING', 'RESOURCE_CONFIRMED', "
            "'PASSPORT_READY', 'MATCH_READY', 'DECIDED', 'SCENARIO_READY', "
            "'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_audit_events_to_status",
        ),
        Index("ix_audit_events_case_created_at", "case_id", "created_at"),
    )

    audit_event_id: Mapped[int] = mapped_column(_bigint_pk(), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    from_status: Mapped[WorkflowStatus | None] = mapped_column(
        _enum(WorkflowStatus, "audit_from_workflow_status"), nullable=True
    )
    to_status: Mapped[WorkflowStatus | None] = mapped_column(
        _enum(WorkflowStatus, "audit_to_workflow_status"), nullable=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="audit_events")
