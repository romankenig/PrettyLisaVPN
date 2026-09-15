"""Persist durable VPN peer cleanup completion.

Revision ID: 0014_vpn_peer_cleanup
Revises: 0013_safe_vpn_ip_allocation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_vpn_peer_cleanup"
down_revision: str | None = "0013_safe_vpn_ip_allocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vpn_sessions", sa.Column("peer_removed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_vpn_sessions_peer_removed_terminal",
        "vpn_sessions",
        "peer_removed_at IS NULL OR status IN ('EXPIRED', 'DISCONNECTED', 'FAILED')",
    )
    op.create_index(
        "ix_vpn_sessions_cleanup_pending",
        "vpn_sessions",
        ["status"],
        unique=False,
        postgresql_where=sa.text(
            "peer_removed_at IS NULL AND status IN ('EXPIRED', 'DISCONNECTED', 'FAILED')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_sessions_cleanup_pending", table_name="vpn_sessions")
    op.drop_constraint("ck_vpn_sessions_peer_removed_terminal", "vpn_sessions", type_="check")
    op.drop_column("vpn_sessions", "peer_removed_at")
