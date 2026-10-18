"""Persistent development provider ledger and deduplicated notifications.

Revision ID: 0025_billing_sandbox
Revises: 0024_billing_operations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0025_billing_sandbox"
down_revision: str | None = "0024_billing_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_sandbox_payments",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("billing_operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("request", JSONB(), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
    )
    op.create_table(
        "billing_sandbox_notifications",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("billing_sandbox_payments.operation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'FAILED', 'CANCELED')",
            name="ck_billing_sandbox_notifications_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_sandbox_notifications")
    op.drop_table("billing_sandbox_payments")
