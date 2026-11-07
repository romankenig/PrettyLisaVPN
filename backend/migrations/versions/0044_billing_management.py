"""Verified payment summaries and explicit cancellation of a recurring contract."""

import sqlalchemy as sa
from alembic import op

revision = "0044_billing_management"
down_revision = "0043_browser_proxy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("method_kind", sa.String(16), nullable=True),
        sa.Column("card_brand", sa.String(16), nullable=True),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("next_charge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_canceled_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("billing_accounts", column)
    op.create_check_constraint(
        "ck_billing_account_method_kind",
        "billing_accounts",
        "method_kind IS NULL OR method_kind IN ('CARD', 'SBP', 'UNKNOWN')",
    )
    op.create_check_constraint(
        "ck_billing_account_card_summary",
        "billing_accounts",
        "((method_kind IS NULL OR method_kind <> 'CARD') "
        "AND card_brand IS NULL AND card_last4 IS NULL) OR "
        "(method_kind = 'CARD' AND card_brand IS NOT NULL AND card_last4 IS NOT NULL "
        "AND card_brand IN ('visa','mastercard','mir','unknown') "
        "AND card_last4 ~ '^[0-9]{4}$')",
    )
    # Only a confirmed local cancellation closes a contract; legacy absence of a
    # saved method is not evidence that an external recurring authority stopped.
    op.execute(
        sa.text("""
        UPDATE billing_accounts AS account
        SET renewal_canceled_at = operation.completed_at
        FROM (
            SELECT DISTINCT ON (user_id) user_id, completed_at, command
            FROM billing_operations
            WHERE status = 'SUCCEEDED'
            ORDER BY user_id, completed_at DESC, created_at DESC
        ) AS operation
        WHERE account.user_id = operation.user_id
          AND account.mandate_reference IS NULL
          AND operation.command ->> 'action' = 'CANCEL'
    """)
    )


def downgrade() -> None:
    op.drop_constraint("ck_billing_account_card_summary", "billing_accounts", type_="check")
    op.drop_constraint("ck_billing_account_method_kind", "billing_accounts", type_="check")
    for name in (
        "renewal_canceled_at",
        "next_charge_at",
        "card_last4",
        "card_brand",
        "method_kind",
    ):
        op.drop_column("billing_accounts", name)
