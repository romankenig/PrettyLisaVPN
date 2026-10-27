"""Independent node lifecycle and monitoring; legacy data remains unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_fleet_lifecycle"
down_revision = "0028_managed_vpn_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_nodes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("host", sa.String(45), nullable=False, unique=True),
        sa.Column("credential_ref", sa.String(40), nullable=False),
        sa.Column("expected_egress_ips", postgresql.JSONB(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_available_for_free", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_owner", sa.UUID()),
        sa.Column("lock_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint("capacity > 0", name="ck_fleet_node_capacity"),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_fleet_node_country"),
    )
    op.create_table(
        "fleet_methods",
        sa.Column("node_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id"), primary_key=True),
        sa.Column("method", sa.String(32), primary_key=True),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("public_key", sa.String(44)),
        sa.Column("configured_at", sa.DateTime(timezone=True)),
        sa.Column("next_check_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_fleet_methods_next_check_at", "fleet_methods", ["next_check_at"])
    op.create_table(
        "fleet_operations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("node_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id"), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_token", sa.UUID()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id")),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.UniqueConstraint("node_id", "kind", "request_key", name="uq_fleet_operation_request"),
    )
    op.create_index("ix_fleet_operations_due", "fleet_operations", ["status", "next_attempt_at"])
    op.create_table(
        "fleet_observations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.UUID(),
            sa.ForeignKey("fleet_operations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("node_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id"), nullable=False),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("fleet_nodes.id")),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_fleet_observation_history", "fleet_observations", ["node_id", "observed_at"]
    )


def downgrade() -> None:
    for table in ("fleet_observations", "fleet_operations", "fleet_methods", "fleet_nodes"):
        op.drop_table(table)
