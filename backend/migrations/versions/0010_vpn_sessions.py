"""Create VPN session control-plane state.

Revision ID: 0010_vpn_sessions
Revises: 0009_vpn_nodes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_vpn_sessions"
down_revision: str | None = "0009_vpn_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

subscription_plan = postgresql.ENUM(
    "FREE",
    "PREMIUM",
    name="subscription_plan",
    create_type=False,
)
vpn_session_status = postgresql.ENUM(
    "PENDING",
    "ACTIVE",
    "EXPIRED",
    "DISCONNECTED",
    "FAILED",
    name="vpn_session_status",
    create_type=False,
)
live_status = sa.text("status IN ('PENDING', 'ACTIVE')")


def upgrade() -> None:
    """Create VPN session enum, state table, constraints, and indexes."""
    vpn_session_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "vpn_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("vpn_node_id", sa.Uuid(), nullable=False),
        sa.Column("client_wireguard_public_key", sa.String(length=44), nullable=False),
        sa.Column("allocated_client_ipv4", postgresql.INET(), nullable=False),
        sa.Column("plan_snapshot", subscription_plan, nullable=False),
        sa.Column(
            "status",
            vpn_session_status,
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "client_wireguard_public_key ~ '^[A-Za-z0-9+/]{43}=$'",
            name=op.f("ck_vpn_sessions_client_public_key_format"),
        ),
        sa.CheckConstraint(
            "family(allocated_client_ipv4) = 4",
            name=op.f("ck_vpn_sessions_allocated_ipv4_family"),
        ),
        sa.CheckConstraint(
            "plan_snapshot <> 'FREE' OR expires_at IS NOT NULL",
            name=op.f("ck_vpn_sessions_free_expires"),
        ),
        sa.CheckConstraint(
            "status <> 'EXPIRED' OR expires_at IS NOT NULL",
            name=op.f("ck_vpn_sessions_expired_has_expiry"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > started_at",
            name=op.f("ck_vpn_sessions_expiry_after_start"),
        ),
        sa.CheckConstraint(
            "started_at >= created_at AND updated_at >= created_at",
            name=op.f("ck_vpn_sessions_timestamp_order"),
        ),
        sa.CheckConstraint(
            "disconnected_at IS NULL OR disconnected_at >= started_at",
            name=op.f("ck_vpn_sessions_disconnected_after_start"),
        ),
        sa.CheckConstraint(
            "(status = 'DISCONNECTED') = (disconnected_at IS NOT NULL)",
            name=op.f("ck_vpn_sessions_status_disconnected_at"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_vpn_sessions_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vpn_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vpn_node_id"],
            ["vpn_nodes.id"],
            name=op.f("fk_vpn_sessions_vpn_node_id_vpn_nodes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vpn_sessions")),
    )
    op.create_index(
        "ix_vpn_sessions_device_id_created_at",
        "vpn_sessions",
        ["device_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_vpn_sessions_node_status",
        "vpn_sessions",
        ["vpn_node_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_vpn_sessions_status_expires_at",
        "vpn_sessions",
        ["status", "expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index(
        "ix_vpn_sessions_user_id_created_at",
        "vpn_sessions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_vpn_sessions_live_client_public_key",
        "vpn_sessions",
        ["client_wireguard_public_key"],
        unique=True,
        postgresql_where=live_status,
    )
    op.create_index(
        "uq_vpn_sessions_live_device",
        "vpn_sessions",
        ["device_id"],
        unique=True,
        postgresql_where=live_status,
    )
    op.create_index(
        "uq_vpn_sessions_live_node_ipv4",
        "vpn_sessions",
        ["vpn_node_id", "allocated_client_ipv4"],
        unique=True,
        postgresql_where=live_status,
    )


def downgrade() -> None:
    """Drop VPN session state and its status enum."""
    op.drop_index("uq_vpn_sessions_live_node_ipv4", table_name="vpn_sessions")
    op.drop_index("uq_vpn_sessions_live_device", table_name="vpn_sessions")
    op.drop_index("uq_vpn_sessions_live_client_public_key", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_user_id_created_at", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_status_expires_at", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_node_status", table_name="vpn_sessions")
    op.drop_index("ix_vpn_sessions_device_id_created_at", table_name="vpn_sessions")
    op.drop_table("vpn_sessions")
    vpn_session_status.drop(op.get_bind(), checkfirst=True)
