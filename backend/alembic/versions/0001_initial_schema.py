"""Create the GreenFab Loop workflow schema.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=False,
        validate_strings=True,
    )


def _json_type() -> sa.JSON:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _bigint_pk() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


SOURCE_TYPE = ("REAL", "DEMO", "SCENARIO")
WORKFLOW_STATUS = (
    "DETECTED",
    "CONFIRMATION_PENDING",
    "RESOURCE_CONFIRMED",
    "PASSPORT_READY",
    "MATCH_READY",
    "DECIDED",
    "SCENARIO_READY",
    "RECEIPT_CREATED",
    "NOT_CONFIRMED",
    "CLOSED",
)


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("risk_rank", sa.Integer(), nullable=True),
        sa.Column("shap_top_features", _json_type(), nullable=False),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column(
            "workflow_status",
            _enum("workflow_status", *WORKFLOW_STATUS),
            server_default="DETECTED",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("risk_rank IS NULL OR risk_rank >= 1", name="ck_cases_risk_rank"),
        sa.CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_cases_source_type"),
        sa.CheckConstraint(
            "workflow_status IN ('DETECTED', 'CONFIRMATION_PENDING', "
            "'RESOURCE_CONFIRMED', 'PASSPORT_READY', 'MATCH_READY', 'DECIDED', "
            "'SCENARIO_READY', 'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_cases_workflow_status",
        ),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index("ix_cases_workflow_status", "cases", ["workflow_status"])

    op.create_table(
        "demands",
        sa.Column("demand_id", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("demand_description", sa.Text(), nullable=False),
        sa.Column("quantity_min", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("quantity_max", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("accepted_conditions", _json_type(), nullable=False),
        sa.Column("required_fields", _json_type(), nullable=False),
        sa.Column(
            "source_type",
            _enum("source_type", *SOURCE_TYPE),
            server_default="DEMO",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0", name="ck_demands_quantity_min"
        ),
        sa.CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= 0", name="ck_demands_quantity_max"
        ),
        sa.CheckConstraint(
            "quantity_min IS NULL OR quantity_max IS NULL OR quantity_min <= quantity_max",
            name="ck_demands_quantity_range",
        ),
        sa.CheckConstraint(
            "(quantity_min IS NULL AND quantity_max IS NULL) OR unit IS NOT NULL",
            name="ck_demands_quantity_unit",
        ),
        sa.CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_demands_source_type"),
        sa.PrimaryKeyConstraint("demand_id"),
    )

    op.create_table(
        "resource_confirmations",
        sa.Column("confirmation_id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum("resource_confirmation_status", "PENDING", "CONFIRMED", "NOT_CONFIRMED"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("confirmed_by", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'NOT_CONFIRMED')",
            name="ck_resource_confirmations_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('REAL', 'DEMO')",
            name="ck_resource_confirmations_source_type",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR "
            "(status IN ('CONFIRMED', 'NOT_CONFIRMED') AND confirmed_by IS NOT NULL "
            "AND length(trim(confirmed_by)) > 0 AND confirmed_at IS NOT NULL)",
            name="ck_resource_confirmations_completed_fields",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("confirmation_id"),
        sa.UniqueConstraint("case_id"),
    )

    op.create_table(
        "resource_passports",
        sa.Column("passport_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("composition", sa.Text(), nullable=True),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity >= 0", name="ck_resource_passports_quantity"
        ),
        sa.CheckConstraint(
            "(quantity IS NULL AND unit IS NULL) OR "
            "(quantity IS NOT NULL AND unit IS NOT NULL AND length(trim(unit)) > 0)",
            name="ck_resource_passports_quantity_unit_pair",
        ),
        sa.CheckConstraint(
            "source_type IN ('REAL', 'DEMO')",
            name="ck_resource_passports_source_type",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("passport_id"),
        sa.UniqueConstraint("case_id"),
    )

    op.create_table(
        "match_runs",
        sa.Column("match_run_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("passport_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _enum("match_run_status", "PENDING", "COMPLETED", "FAILED"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("top_k > 0", name="ck_match_runs_top_k"),
        sa.CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_match_runs_source_type"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_match_runs_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["passport_id"], ["resource_passports.passport_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("match_run_id"),
        sa.UniqueConstraint(
            "case_id", "idempotency_key", name="uq_match_runs_case_idempotency_key"
        ),
    )
    op.create_index("ix_match_runs_case_created_at", "match_runs", ["case_id", "created_at"])

    op.create_table(
        "match_candidates",
        sa.Column("match_candidate_id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("match_run_id", sa.String(length=64), nullable=False),
        sa.Column("demand_id", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("semantic_similarity", sa.Float(), nullable=True),
        sa.Column("rule_check", _json_type(), nullable=False),
        sa.Column(
            "status",
            _enum("match_candidate_status", "REVIEW", "NEEDS_INFO", "RULE_FAIL"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("rank > 0", name="ck_match_candidates_rank"),
        sa.CheckConstraint(
            "semantic_similarity IS NULL OR "
            "(semantic_similarity >= -1 AND semantic_similarity <= 1)",
            name="ck_match_candidates_similarity",
        ),
        sa.CheckConstraint(
            "status IN ('REVIEW', 'NEEDS_INFO', 'RULE_FAIL')",
            name="ck_match_candidates_status",
        ),
        sa.ForeignKeyConstraint(["demand_id"], ["demands.demand_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["match_run_id"], ["match_runs.match_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("match_candidate_id"),
        sa.UniqueConstraint("match_run_id", "demand_id", name="uq_match_candidate_demand"),
        sa.UniqueConstraint("match_run_id", "rank", name="uq_match_candidate_rank"),
    )

    op.create_table(
        "decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum("decision_status", "APPROVED", "HOLD", "REJECTED"),
            nullable=False,
        ),
        sa.Column("selected_demand_id", sa.String(length=64), nullable=True),
        sa.Column("selected_match_candidate_id", _bigint_pk(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'HOLD', 'REJECTED')",
            name="ck_decisions_status",
        ),
        sa.CheckConstraint(
            "status != 'APPROVED' OR "
            "(selected_demand_id IS NOT NULL AND selected_match_candidate_id IS NOT NULL)",
            name="ck_decisions_approved_fields",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_decisions_reason"),
        sa.CheckConstraint("length(trim(decided_by)) > 0", name="ck_decisions_decided_by"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_demand_id"], ["demands.demand_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["selected_match_candidate_id"],
            ["match_candidates.match_candidate_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint("case_id"),
    )

    op.create_table(
        "esg_scenarios",
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column(
            "source_type",
            _enum("source_type", *SOURCE_TYPE),
            server_default="SCENARIO",
            nullable=False,
        ),
        sa.Column("inputs", _json_type(), nullable=False),
        sa.Column("results", _json_type(), nullable=False),
        sa.Column("formula_version", sa.String(length=255), nullable=True),
        sa.Column("factor_source", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("source_type = 'SCENARIO'", name="ck_esg_scenarios_source_type"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("scenario_id"),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("decision_id"),
    )

    op.create_table(
        "receipts",
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("passport_id", sa.String(length=64), nullable=False),
        sa.Column("selected_demand_id", sa.String(length=64), nullable=True),
        sa.Column(
            "decision_status",
            _enum("decision_status", "APPROVED", "HOLD", "REJECTED"),
            nullable=False,
        ),
        sa.Column(
            "handoff_status",
            _enum("handoff_status", "RESOURCE_CONFIRMED", "APPROVED", "HANDOFF_CONFIRMED"),
            nullable=False,
        ),
        sa.Column("payload_json", _json_type(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision_status IN ('APPROVED', 'HOLD', 'REJECTED')",
            name="ck_receipts_decision_status",
        ),
        sa.CheckConstraint(
            "handoff_status IN ('RESOURCE_CONFIRMED', 'APPROVED', 'HANDOFF_CONFIRMED')",
            name="ck_receipts_handoff_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.decision_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["passport_id"], ["resource_passports.passport_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["selected_demand_id"], ["demands.demand_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["scenario_id"], ["esg_scenarios.scenario_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("receipt_id"),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("decision_id"),
        sa.UniqueConstraint("scenario_id"),
    )

    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column(
            "from_status",
            _enum("audit_from_workflow_status", *WORKFLOW_STATUS),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            _enum("audit_to_workflow_status", *WORKFLOW_STATUS),
            nullable=True,
        ),
        sa.Column("payload_json", _json_type(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('DETECTED', 'CONFIRMATION_PENDING', 'RESOURCE_CONFIRMED', "
            "'PASSPORT_READY', 'MATCH_READY', 'DECIDED', 'SCENARIO_READY', "
            "'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_audit_events_from_status",
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR to_status IN "
            "('DETECTED', 'CONFIRMATION_PENDING', 'RESOURCE_CONFIRMED', "
            "'PASSPORT_READY', 'MATCH_READY', 'DECIDED', 'SCENARIO_READY', "
            "'RECEIPT_CREATED', 'NOT_CONFIRMED', 'CLOSED')",
            name="ck_audit_events_to_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("audit_event_id"),
    )
    op.create_index("ix_audit_events_case_created_at", "audit_events", ["case_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_case_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("receipts")
    op.drop_table("esg_scenarios")
    op.drop_table("decisions")
    op.drop_table("match_candidates")
    op.drop_index("ix_match_runs_case_created_at", table_name="match_runs")
    op.drop_table("match_runs")
    op.drop_table("resource_passports")
    op.drop_table("resource_confirmations")
    op.drop_table("demands")
    op.drop_index("ix_cases_workflow_status", table_name="cases")
    op.drop_table("cases")
