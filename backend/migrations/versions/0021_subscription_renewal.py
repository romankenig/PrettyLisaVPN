"""Separate canceled renewal from paid access; preserve all paid period dates.

Revision ID: 0021_subscription_renewal
Revises: 0020_support_requests
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_subscription_renewal"
down_revision: str | None = "0020_support_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE subscriptions SET auto_renew = false WHERE status = 'CANCELED'")
    op.create_check_constraint(
        "ck_subscriptions_canceled_no_auto_renew",
        "subscriptions",
        "status <> 'CANCELED' OR NOT auto_renew",
    )


def downgrade() -> None:
    op.drop_constraint("ck_subscriptions_canceled_no_auto_renew", "subscriptions", type_="check")
