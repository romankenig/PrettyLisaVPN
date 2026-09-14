"""Add observed VPN node health state.

Revision ID: 0011_vpn_node_health
Revises: 0010_vpn_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_vpn_node_health"
down_revision: str | None = "0010_vpn_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vpn_node_health_status = postgresql.ENUM(
    "UNKNOWN",
    "HEALTHY",
    "UNHEALTHY",
    name="vpn_node_health_status",
    create_type=False,
)


def upgrade() -> None:
    vpn_node_health_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "vpn_nodes",
        sa.Column(
            "health_status",
            vpn_node_health_status,
            server_default="UNKNOWN",
            nullable=False,
        ),
    )
    op.add_column(
        "vpn_nodes",
        sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_vpn_nodes_health_checked_after_creation"),
        "vpn_nodes",
        "health_checked_at IS NULL OR health_checked_at >= created_at",
    )
    op.create_check_constraint(
        op.f("ck_vpn_nodes_last_seen_before_health_check"),
        "vpn_nodes",
        "last_seen_at IS NULL OR health_checked_at IS NULL OR last_seen_at <= health_checked_at",
    )
    op.create_index(
        "ix_vpn_nodes_effective_availability",
        "vpn_nodes",
        ["status", "health_status", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_nodes_effective_availability", table_name="vpn_nodes")
    op.drop_constraint(
        op.f("ck_vpn_nodes_last_seen_before_health_check"),
        "vpn_nodes",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_vpn_nodes_health_checked_after_creation"),
        "vpn_nodes",
        type_="check",
    )
    op.drop_column("vpn_nodes", "health_checked_at")
    op.drop_column("vpn_nodes", "health_status")
    vpn_node_health_status.drop(op.get_bind(), checkfirst=True)
