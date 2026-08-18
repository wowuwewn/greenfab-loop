"""Add detect imports, passport evidence, and versioned rule policies.

Revision ID: 0002_productization_foundations
Revises: 0001_initial_schema
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_productization_foundations"
down_revision: str | None = "0001_initial_schema"
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


SOURCE_TYPE = ("REAL", "DEMO", "SCENARIO")


def upgrade() -> None:
    op.create_table(
        "detect_imports",
        sa.Column("detect_import_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_name", sa.String(length=255), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=255), nullable=False),
        sa.Column("validation_method", sa.Text(), nullable=True),
        sa.Column("score_type", sa.Text(), nullable=True),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("provenance_json", _json_type(), nullable=False),
        sa.Column("imported_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("case_count >= 0", name="ck_detect_imports_case_count"),
        sa.CheckConstraint("source_type IN ('REAL', 'DEMO')", name="ck_detect_imports_source_type"),
        sa.PrimaryKeyConstraint("detect_import_id"),
        sa.UniqueConstraint("artifact_sha256"),
    )

    with op.batch_alter_table("cases") as batch_op:
        batch_op.add_column(sa.Column("detect_import_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("risk_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("risk_score_type", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_cases_detect_import_id",
            "detect_imports",
            ["detect_import_id"],
            ["detect_import_id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_cases_risk_score_range",
            "risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1)",
        )
        batch_op.create_check_constraint(
            "ck_cases_risk_score_metadata",
            "(risk_score IS NULL AND risk_score_type IS NULL) OR "
            "(risk_score IS NOT NULL AND risk_score_type IS NOT NULL "
            "AND length(trim(risk_score_type)) > 0)",
        )
        batch_op.create_index("ix_cases_detect_import_id", ["detect_import_id"])

    op.create_table(
        "passport_evidence",
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("passport_id", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "evidence_type",
            _enum("evidence_type", "PHOTO", "DOCUMENT", "ANALYSIS_REPORT", "OTHER"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", _enum("source_type", *SOURCE_TYPE), nullable=False),
        sa.Column("uploaded_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_passport_evidence_size"),
        sa.CheckConstraint(
            "evidence_type IN ('PHOTO', 'DOCUMENT', 'ANALYSIS_REPORT', 'OTHER')",
            name="ck_passport_evidence_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('REAL', 'DEMO')", name="ck_passport_evidence_source_type"
        ),
        sa.ForeignKeyConstraint(
            ["passport_id"], ["resource_passports.passport_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("evidence_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_passport_evidence_passport_created_at",
        "passport_evidence",
        ["passport_id", "created_at"],
    )

    op.create_table(
        "rule_policies",
        sa.Column("policy_key", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active_version", sa.Integer(), nullable=True),
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
            "active_version IS NULL OR active_version >= 1", name="ck_rule_active_version"
        ),
        sa.PrimaryKeyConstraint("policy_key"),
    )

    op.create_table(
        "rule_policy_versions",
        sa.Column("rule_policy_version_id", sa.String(length=64), nullable=False),
        sa.Column("policy_key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition_json", _json_type(), nullable=False),
        sa.Column("definition_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_rule_policy_versions_version"),
        sa.ForeignKeyConstraint(["policy_key"], ["rule_policies.policy_key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rule_policy_version_id"),
        sa.UniqueConstraint("policy_key", "version", name="uq_rule_policy_key_version"),
    )
    op.create_index(
        "ix_rule_policy_versions_policy_created_at",
        "rule_policy_versions",
        ["policy_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rule_policy_versions_policy_created_at", table_name="rule_policy_versions")
    op.drop_table("rule_policy_versions")
    op.drop_table("rule_policies")
    op.drop_index("ix_passport_evidence_passport_created_at", table_name="passport_evidence")
    op.drop_table("passport_evidence")
    with op.batch_alter_table("cases") as batch_op:
        batch_op.drop_index("ix_cases_detect_import_id")
        batch_op.drop_constraint("ck_cases_risk_score_metadata", type_="check")
        batch_op.drop_constraint("ck_cases_risk_score_range", type_="check")
        batch_op.drop_constraint("fk_cases_detect_import_id", type_="foreignkey")
        batch_op.drop_column("risk_score_type")
        batch_op.drop_column("risk_score")
        batch_op.drop_column("detect_import_id")
    op.drop_table("detect_imports")
