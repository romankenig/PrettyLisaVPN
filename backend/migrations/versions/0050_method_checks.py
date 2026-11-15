"""Daily connection-method assessments and synthetic relay reservations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050_method_checks"
down_revision = "0049_report_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_method_checks",
        sa.Column("method", sa.String(32), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("code", sa.String(64)),
        sa.Column("relay_node_id", sa.Uuid(), sa.ForeignKey("fleet_nodes.id")),
        sa.Column("relay_port", sa.Integer()),
        sa.Column("reserved_until", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_method_check_due", "fleet_method_checks", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("fleet_method_checks")
