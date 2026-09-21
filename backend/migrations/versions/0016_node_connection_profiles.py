"""Declare multiple connection profiles per VPN node.

Revision ID: 0016_node_profiles
Revises: 0015_netcup_provider
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_node_profiles"
down_revision: str | None = "0015_netcup_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL remains a compatibility sentinel for legacy registration/import scripts.
    # An explicit [] means no supported profiles and must never imply WireGuard.
    op.add_column("vpn_nodes", sa.Column("connection_profiles", postgresql.JSONB(), nullable=True))
    op.execute(
        "UPDATE vpn_nodes SET connection_profiles = jsonb_build_array("
        "jsonb_build_object('profile', 'WIREGUARD_UDP', 'ports', "
        "jsonb_build_array(wireguard_port)))"
    )
    op.create_check_constraint(
        "ck_vpn_nodes_profiles_array",
        "vpn_nodes",
        "connection_profiles IS NULL OR jsonb_typeof(connection_profiles) = 'array'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_vpn_nodes_profiles_array", "vpn_nodes", type_="check")
    op.drop_column("vpn_nodes", "connection_profiles")
