"""Audited, idempotent operator resets without removing historical VPN usage."""

import sqlalchemy as sa
from alembic import op

revision = "0032_free_quota_resets"
down_revision = "0031_wireguard_relay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "free_quota_resets",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_free_quota_reset_day"),
    )


def downgrade() -> None:
    op.drop_table("free_quota_resets")
