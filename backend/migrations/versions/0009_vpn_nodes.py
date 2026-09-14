"""Create VPN node control-plane metadata.

Revision ID: 0009_vpn_nodes
Revises: 0008_auth_session_device_fk
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_vpn_nodes"
down_revision: str | None = "0008_auth_session_device_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

vpn_node_provider = postgresql.ENUM(
    "DIGITALOCEAN",
    name="vpn_node_provider",
    create_type=False,
)
vpn_node_status = postgresql.ENUM(
    "ACTIVE",
    "DRAINING",
    "OFFLINE",
    "DISABLED",
    name="vpn_node_status",
    create_type=False,
)


def upgrade() -> None:
    """Create VPN node enums, metadata table, constraints, and indexes."""
    vpn_node_provider.create(op.get_bind(), checkfirst=True)
    vpn_node_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "vpn_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", vpn_node_provider, nullable=False),
        sa.Column("provider_region", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("public_ipv4", postgresql.INET(), nullable=False),
        sa.Column("private_ipv4", postgresql.INET(), nullable=True),
        sa.Column("wireguard_port", sa.Integer(), nullable=False),
        sa.Column("wireguard_public_key", sa.String(length=44), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            vpn_node_status,
            server_default="OFFLINE",
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
            "btrim(name) <> ''",
            name=op.f("ck_vpn_nodes_name_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(provider_region) <> ''",
            name=op.f("ck_vpn_nodes_provider_region_not_blank"),
        ),
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_vpn_nodes_country_code_format"),
        ),
        sa.CheckConstraint(
            "city IS NULL OR btrim(city) <> ''",
            name=op.f("ck_vpn_nodes_city_not_blank"),
        ),
        sa.CheckConstraint(
            "family(public_ipv4) = 4",
            name=op.f("ck_vpn_nodes_public_ipv4_family"),
        ),
        sa.CheckConstraint(
            "private_ipv4 IS NULL OR family(private_ipv4) = 4",
            name=op.f("ck_vpn_nodes_private_ipv4_family"),
        ),
        sa.CheckConstraint(
            "wireguard_port BETWEEN 1 AND 65535",
            name=op.f("ck_vpn_nodes_wireguard_port_range"),
        ),
        sa.CheckConstraint(
            "wireguard_public_key ~ '^[A-Za-z0-9+/]{43}=$'",
            name=op.f("ck_vpn_nodes_wireguard_public_key_format"),
        ),
        sa.CheckConstraint(
            "capacity > 0",
            name=op.f("ck_vpn_nodes_capacity_positive"),
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name=op.f("ck_vpn_nodes_timestamps_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vpn_nodes")),
        sa.UniqueConstraint("name", name=op.f("uq_vpn_nodes_name")),
        sa.UniqueConstraint(
            "public_ipv4",
            "wireguard_port",
            name=op.f("uq_vpn_nodes_public_endpoint"),
        ),
        sa.UniqueConstraint(
            "wireguard_public_key",
            name=op.f("uq_vpn_nodes_wireguard_public_key"),
        ),
    )
    op.create_index(
        "ix_vpn_nodes_last_seen_at",
        "vpn_nodes",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_vpn_nodes_provider_region",
        "vpn_nodes",
        ["provider", "provider_region"],
        unique=False,
    )
    op.create_index(
        "ix_vpn_nodes_status_country_code",
        "vpn_nodes",
        ["status", "country_code"],
        unique=False,
    )


def downgrade() -> None:
    """Drop VPN node metadata and its enum types."""
    op.drop_index("ix_vpn_nodes_status_country_code", table_name="vpn_nodes")
    op.drop_index("ix_vpn_nodes_provider_region", table_name="vpn_nodes")
    op.drop_index("ix_vpn_nodes_last_seen_at", table_name="vpn_nodes")
    op.drop_table("vpn_nodes")
    vpn_node_status.drop(op.get_bind(), checkfirst=True)
    vpn_node_provider.drop(op.get_bind(), checkfirst=True)
