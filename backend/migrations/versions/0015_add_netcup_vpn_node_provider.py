"""Add Netcup as a VPN node infrastructure provider.

Revision ID: 0015_netcup_provider
Revises: 0014_vpn_peer_cleanup
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_netcup_provider"
down_revision: str | None = "0014_vpn_peer_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE vpn_node_provider ADD VALUE IF NOT EXISTS 'NETCUP'")


def downgrade() -> None:
    connection = op.get_bind()
    netcup_nodes = connection.scalar(
        sa.text("SELECT count(*) FROM vpn_nodes WHERE provider::text = 'NETCUP'")
    )
    if netcup_nodes:
        raise RuntimeError("cannot remove NETCUP provider while Netcup VPN nodes exist")

    op.execute("ALTER TYPE vpn_node_provider RENAME TO vpn_node_provider_with_netcup")
    op.execute("CREATE TYPE vpn_node_provider AS ENUM ('DIGITALOCEAN')")
    op.execute(
        "ALTER TABLE vpn_nodes ALTER COLUMN provider TYPE vpn_node_provider "
        "USING provider::text::vpn_node_provider"
    )
    op.execute("DROP TYPE vpn_node_provider_with_netcup")
