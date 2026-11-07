"""Bounded real connection traffic history.

Revision ID: 0047
Revises: 0046
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_active_user_speed"
down_revision = "0046_demo_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_traffic_cursors",
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("fleet_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "fleet_traffic_intervals",
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("fleet_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("end_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_fleet_traffic_time", "fleet_traffic_intervals", ["end_at"])


def downgrade() -> None:
    op.drop_table("fleet_traffic_intervals")
    op.drop_table("fleet_traffic_cursors")
