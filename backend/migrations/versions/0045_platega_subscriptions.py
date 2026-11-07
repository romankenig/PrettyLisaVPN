"""Durable Platega create fence, agreement binding and deduplicated charge evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0045_platega_subscriptions"
down_revision = "0044_billing_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_platega_agreements",
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("billing_operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider_id", sa.Uuid(), unique=True),
        sa.Column("create_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_payment_id", sa.Uuid(), unique=True),
        sa.Column("state", sa.String(32)),
        sa.Column("next_charge_at", sa.DateTime(timezone=True)),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_billing_platega_agreements_user_id", "billing_platega_agreements", ["user_id"]
    )
    op.create_table(
        "billing_platega_charges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agreement_id",
            sa.Uuid(),
            sa.ForeignKey("billing_platega_agreements.operation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000000", name="ck_platega_charge_amount"
        ),
        sa.CheckConstraint("currency = 'RUB'", name="ck_platega_charge_currency"),
        sa.CheckConstraint(
            "status IN ('PENDING','CONFIRMED','CANCELED','CHARGEBACKED',"
            "'PARTIALLY_REFUNDED','DISPUTED')",
            name="ck_platega_charge_status",
        ),
    )
    op.create_index(
        "ix_billing_platega_charges_agreement_id", "billing_platega_charges", ["agreement_id"]
    )


def downgrade() -> None:
    # Never erase evidence needed to reconcile an external recurring authority.
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS(SELECT 1 FROM billing_platega_agreements)"))
        .scalar()
    ):
        raise RuntimeError("Retain Platega agreements and charge evidence before rollback")
    op.drop_table("billing_platega_charges")
    op.drop_table("billing_platega_agreements")
