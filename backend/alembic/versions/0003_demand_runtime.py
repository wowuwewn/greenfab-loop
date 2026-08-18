"""Add Demand lifecycle state for vector-index synchronization.

Revision ID: 0003_demand_runtime
Revises: 0002_productization_foundations
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_demand_runtime"
down_revision: str | None = "0002_productization_foundations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "demands",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_demands_is_active", "demands", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_demands_is_active", table_name="demands")
    op.drop_column("demands", "is_active")
