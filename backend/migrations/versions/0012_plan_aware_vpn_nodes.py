"""Add FREE-plan VPN node eligibility metadata.

Revision ID: 0012_plan_aware_vpn_nodes
Revises: 0011_vpn_node_health
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_plan_aware_vpn_nodes"
down_revision: str | None = "0011_vpn_node_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vpn_nodes",
        sa.Column(
            "is_available_for_free",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_vpn_nodes_country_free_status",
        "vpn_nodes",
        ["country_code", "is_available_for_free", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_nodes_country_free_status", table_name="vpn_nodes")
    op.drop_column("vpn_nodes", "is_available_for_free")
