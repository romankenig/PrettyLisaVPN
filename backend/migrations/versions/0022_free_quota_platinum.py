"""Durable daily Free reservations and manually assigned Platinum parity.

Revision ID: 0022_free_quota_platinum
Revises: 0021_subscription_renewal
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_free_quota_platinum"
down_revision: str | None = "0021_subscription_renewal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No transaction uses the new enum value until this migration commits.
    op.execute("ALTER TYPE subscription_plan ADD VALUE IF NOT EXISTS 'PLATINUM'")
    op.create_table(
        "free_vpn_usage",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reserved_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reserved_until > reserved_from", name="ck_free_vpn_usage_period"),
        sa.ForeignKeyConstraint(["session_id"], ["vpn_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "day"),
    )
    op.create_index("ix_free_vpn_usage_user_day", "free_vpn_usage", ["user_id", "day"])
    # Retain usage already made before deployment; split UTC midnight crossings.
    op.execute("""
        INSERT INTO free_vpn_usage
            (session_id, day, user_id, reserved_from, reserved_until, activated_at, released_at)
        SELECT v.id, d.utc_day::date, v.user_id,
            greatest(v.started_at, d.utc_day AT TIME ZONE 'UTC'),
            least(v.expires_at, (d.utc_day + interval '1 day') AT TIME ZONE 'UTC'),
            CASE WHEN v.status = 'PENDING' THEN NULL ELSE v.started_at END,
            CASE WHEN v.peer_removed_at IS NULL THEN NULL
                 ELSE least(v.peer_removed_at, v.expires_at) END
        FROM vpn_sessions v
        CROSS JOIN LATERAL generate_series(
            date_trunc('day', v.started_at AT TIME ZONE 'UTC'),
            date_trunc('day', (v.expires_at - interval '1 microsecond') AT TIME ZONE 'UTC'),
            interval '1 day') AS d(utc_day)
        WHERE v.plan_snapshot = 'FREE'
    """)


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed while other tables use them.
    op.drop_index("ix_free_vpn_usage_user_day", table_name="free_vpn_usage")
    op.drop_table("free_vpn_usage")
