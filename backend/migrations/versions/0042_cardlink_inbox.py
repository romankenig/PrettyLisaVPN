"""Cardlink server-owned bill bindings and deduplicated verified notification inbox."""

import sqlalchemy as sa
from alembic import op

revision = "0042_cardlink_inbox"
down_revision = "0041_product_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_cardlink_bills",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("billing_operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bill_id", sa.String(128), unique=True, nullable=False),
    )
    op.create_table(
        "billing_cardlink_receipts",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("billing_cardlink_bills.operation_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), primary_key=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('UNDERPAID', 'SUCCESS', 'OVERPAID', 'FAIL')",
            name="ck_cardlink_receipt_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_cardlink_receipts")
    op.drop_table("billing_cardlink_bills")
