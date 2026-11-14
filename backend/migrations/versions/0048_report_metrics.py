"""Daily service assessments, configured selections and counter-only session metrics."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048_report_metrics"
down_revision = "0047_active_user_speed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_activity_plan", "product_activity_days")
    op.create_check_constraint(
        "ck_activity_plan",
        "product_activity_days",
        "plan IN ('DEMO','FREE','PREMIUM','PLATINUM','UNKNOWN')",
    )
    for column in (
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("traffic_mode", sa.String(8)),
        sa.Column("service_ids", postgresql.JSONB()),
        sa.Column("custom_rules", postgresql.JSONB()),
    ):
        op.add_column("client_wireguard_leases", column)
    op.create_table(
        "product_session_silence",
        sa.Column(
            "lease_id",
            sa.Uuid(),
            sa.ForeignKey("client_wireguard_leases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("observed_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quiet_since", sa.DateTime(timezone=True)),
        sa.Column("first_silence_at", sa.DateTime(timezone=True)),
        sa.Column("complete", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "fleet_service_checks",
        sa.Column("service_id", sa.Uuid(), sa.ForeignKey("traffic_services.id"), primary_key=True),
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
    )
    op.create_index("ix_service_check_due", "fleet_service_checks", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("fleet_service_checks")
    op.drop_table("product_session_silence")
    for name in ("custom_rules", "service_ids", "traffic_mode", "disconnected_at"):
        op.drop_column("client_wireguard_leases", name)
    op.execute("UPDATE product_activity_days SET plan = 'UNKNOWN' WHERE plan = 'DEMO'")
    op.drop_constraint("ck_activity_plan", "product_activity_days")
    op.create_check_constraint(
        "ck_activity_plan",
        "product_activity_days",
        "plan IN ('FREE','PREMIUM','PLATINUM','UNKNOWN')",
    )
