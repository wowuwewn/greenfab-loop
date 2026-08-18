"""Add Demand lifecycle state for vector-index synchronization.

Revision ID: 0003_demand_runtime
Revises: 0002_productization_foundations
Create Date: 2026-08-18
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_demand_runtime"
down_revision: str | None = "0002_productization_foundations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MATCH_RULE_POLICY_KEY = "match-deterministic-v0"
MATCH_RULE_POLICY_VERSION_ID = "RULEPOLICY-MATCH-DETERMINISTIC-V0-V1"
MATCH_RULE_POLICY_DEFINITION = {
    "evaluator": "demand-rules-v0.1",
    "evaluated_conditions": ["quantity_and_unit", "required_fields", "location"],
    "interpretation": (
        "This revision identifies the deterministic evaluator contract. "
        "Demand-specific values remain in each immutable candidate snapshot."
    ),
    "rules": [],
}
MATCH_RULE_POLICY_SHA256 = hashlib.sha256(
    json.dumps(
        MATCH_RULE_POLICY_DEFINITION,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def upgrade() -> None:
    op.add_column(
        "demands",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_demands_is_active", "demands", ["is_active"])
    op.add_column(
        "demands",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("demands", sa.Column("content_sha256", sa.String(length=64), nullable=True))

    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column(
        "match_runs",
        sa.Column("passport_snapshot_json", json_type, server_default="{}", nullable=False),
    )
    op.add_column(
        "match_runs",
        sa.Column("execution_token", sa.String(length=64), server_default="legacy", nullable=False),
    )
    op.add_column(
        "match_runs",
        sa.Column(
            "passport_snapshot_sha256",
            sa.String(length=64),
            server_default="0" * 64,
            nullable=False,
        ),
    )
    op.add_column(
        "match_runs",
        sa.Column(
            "rule_policy_key", sa.String(length=100), server_default="legacy", nullable=False
        ),
    )
    op.add_column(
        "match_runs",
        sa.Column("rule_policy_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "match_runs",
        sa.Column(
            "rule_policy_definition_sha256",
            sa.String(length=64),
            server_default="0" * 64,
            nullable=False,
        ),
    )
    op.add_column(
        "match_candidates",
        sa.Column("demand_snapshot_json", json_type, server_default="{}", nullable=False),
    )

    op.create_table(
        "demand_index_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("demand_id", sa.String(length=64), nullable=True),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=True),
        sa.Column("target_content_sha256", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "operation IN ('UPSERT', 'DELETE', 'SYNC_ALL')",
            name="ck_demand_index_events_operation",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'SKIPPED')",
            name="ck_demand_index_events_status",
        ),
        sa.CheckConstraint(
            "(operation = 'SYNC_ALL' AND demand_id IS NULL) OR "
            "(operation IN ('UPSERT', 'DELETE') AND demand_id IS NOT NULL)",
            name="ck_demand_index_events_target",
        ),
        sa.ForeignKeyConstraint(["demand_id"], ["demands.demand_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_demand_index_events_status_created_at",
        "demand_index_events",
        ["status", "created_at"],
    )
    _ensure_builtin_rule_policy(json_type)


def _ensure_builtin_rule_policy(json_type: sa.types.TypeEngine[object]) -> None:
    """Install the reserved evaluator policy independently from demo seeds."""

    policy_table = sa.table(
        "rule_policies",
        sa.column("policy_key", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("active_version", sa.Integer()),
    )
    version_table = sa.table(
        "rule_policy_versions",
        sa.column("rule_policy_version_id", sa.String()),
        sa.column("policy_key", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("definition_json", json_type),
        sa.column("definition_sha256", sa.String()),
        sa.column("created_by", sa.String()),
        sa.column("activated_at", sa.DateTime(timezone=True)),
        sa.column("activated_by", sa.String()),
    )
    connection = op.get_bind()
    policy_exists = connection.execute(
        sa.select(policy_table.c.policy_key).where(
            policy_table.c.policy_key == MATCH_RULE_POLICY_KEY
        )
    ).first()
    if policy_exists is None:
        connection.execute(
            policy_table.insert().values(
                policy_key=MATCH_RULE_POLICY_KEY,
                display_name="Deterministic demand rule evaluator",
                description="Tracks the evaluator contract; it is not a safety or legal policy.",
                active_version=1,
            )
        )

    version_row = connection.execute(
        sa.select(version_table.c.definition_sha256).where(
            version_table.c.policy_key == MATCH_RULE_POLICY_KEY,
            version_table.c.version == 1,
        )
    ).first()
    if version_row is None:
        now = datetime.now(UTC)
        connection.execute(
            version_table.insert().values(
                rule_policy_version_id=MATCH_RULE_POLICY_VERSION_ID,
                policy_key=MATCH_RULE_POLICY_KEY,
                version=1,
                definition_json=MATCH_RULE_POLICY_DEFINITION,
                definition_sha256=MATCH_RULE_POLICY_SHA256,
                created_by="system",
                activated_at=now,
                activated_by="system",
            )
        )
    elif version_row.definition_sha256 != MATCH_RULE_POLICY_SHA256:
        raise RuntimeError("Built-in Match rule policy migration drift detected")

    connection.execute(
        policy_table.update()
        .where(policy_table.c.policy_key == MATCH_RULE_POLICY_KEY)
        .values(active_version=1)
    )


def downgrade() -> None:
    _remove_migration_owned_builtin_rule_policy()
    op.drop_index("ix_demand_index_events_status_created_at", table_name="demand_index_events")
    op.drop_table("demand_index_events")
    op.drop_column("match_candidates", "demand_snapshot_json")
    op.drop_column("match_runs", "rule_policy_definition_sha256")
    op.drop_column("match_runs", "rule_policy_version")
    op.drop_column("match_runs", "rule_policy_key")
    op.drop_column("match_runs", "passport_snapshot_sha256")
    op.drop_column("match_runs", "execution_token")
    op.drop_column("match_runs", "passport_snapshot_json")
    op.drop_column("demands", "content_sha256")
    op.drop_column("demands", "version")
    op.drop_index("ix_demands_is_active", table_name="demands")
    op.drop_column("demands", "is_active")


def _remove_migration_owned_builtin_rule_policy() -> None:
    """Remove only the deterministic row ID inserted by this migration."""

    version_table = sa.table(
        "rule_policy_versions",
        sa.column("rule_policy_version_id", sa.String()),
        sa.column("policy_key", sa.String()),
    )
    policy_table = sa.table(
        "rule_policies",
        sa.column("policy_key", sa.String()),
    )
    connection = op.get_bind()
    owned = connection.execute(
        sa.select(version_table.c.rule_policy_version_id).where(
            version_table.c.rule_policy_version_id == MATCH_RULE_POLICY_VERSION_ID,
            version_table.c.policy_key == MATCH_RULE_POLICY_KEY,
        )
    ).first()
    if owned is None:
        return
    connection.execute(
        version_table.delete().where(
            version_table.c.rule_policy_version_id == MATCH_RULE_POLICY_VERSION_ID
        )
    )
    remaining = connection.execute(
        sa.select(version_table.c.rule_policy_version_id).where(
            version_table.c.policy_key == MATCH_RULE_POLICY_KEY
        )
    ).first()
    if remaining is None:
        connection.execute(
            policy_table.delete().where(policy_table.c.policy_key == MATCH_RULE_POLICY_KEY)
        )
