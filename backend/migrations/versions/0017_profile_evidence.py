"""Persist independently verified deployment capabilities.

Revision ID: 0017_profile_evidence
Revises: 0016_node_profiles
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_profile_evidence"
down_revision: str | None = "0016_node_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Never promote legacy declarations or successful handshakes to E2E evidence.
    op.add_column(
        "vpn_nodes",
        sa.Column("deployed_profiles", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_check_constraint(
        "ck_vpn_nodes_deployed_array", "vpn_nodes", "jsonb_typeof(deployed_profiles) = 'array'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_vpn_nodes_deployed_array", "vpn_nodes", type_="check")
    op.drop_column("vpn_nodes", "deployed_profiles")
