"""Explicit account/day allowance; existing resets remain one hour."""

import sqlalchemy as sa
from alembic import op

revision = "0036_daily_allowance"
down_revision = "0035_managed_transports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "free_quota_resets",
        sa.Column("allowance_seconds", sa.Integer(), nullable=False, server_default="3600"),
    )
    op.create_check_constraint(
        "ck_free_quota_allowance", "free_quota_resets", "allowance_seconds BETWEEN 1 AND 86400"
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM free_quota_resets "
            "WHERE allowance_seconds <> 3600 "
            "AND day >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date)"
        )
    ):
        raise RuntimeError("Wait until custom daily allowances expire before downgrading")
    op.drop_constraint("ck_free_quota_allowance", "free_quota_resets", type_="check")
    op.drop_column("free_quota_resets", "allowance_seconds")
