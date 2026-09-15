"""Make live VPN client address ownership globally unique.

Revision ID: 0013_safe_vpn_ip_allocation
Revises: 0012_plan_aware_vpn_nodes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_safe_vpn_ip_allocation"
down_revision: str | None = "0012_plan_aware_vpn_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_vpn_sessions_live_node_ipv4", table_name="vpn_sessions")
    op.create_index(
        "uq_vpn_sessions_live_ipv4",
        "vpn_sessions",
        ["allocated_client_ipv4"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )


def downgrade() -> None:
    op.drop_index("uq_vpn_sessions_live_ipv4", table_name="vpn_sessions")
    op.create_index(
        "uq_vpn_sessions_live_node_ipv4",
        "vpn_sessions",
        ["vpn_node_id", "allocated_client_ipv4"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'ACTIVE')"),
    )
