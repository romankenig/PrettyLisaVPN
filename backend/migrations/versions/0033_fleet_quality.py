"""Preserve rating at check time; existing speed measurements stay in JSONB."""

import sqlalchemy as sa
from alembic import op

revision = "0033_fleet_quality"
down_revision = "0032_free_quota_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fleet_observations", sa.Column("quality", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_fleet_observation_quality", "fleet_observations", "quality BETWEEN 0 AND 100"
    )


def downgrade() -> None:
    op.drop_constraint("ck_fleet_observation_quality", "fleet_observations", type_="check")
    op.drop_column("fleet_observations", "quality")
