"""Store event-time tariffs for connection and app-version analytics."""

import sqlalchemy as sa
from alembic import op

revision = "0053_analytics_plans"
down_revision = "0052_pending_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_wireguard_leases", sa.Column("plan_snapshot", sa.String(16)))
    op.create_check_constraint(
        "ck_client_lease_plan_snapshot",
        "client_wireguard_leases",
        "plan_snapshot IN ('DEMO','FREE','PREMIUM','PLATINUM','UNKNOWN')",
    )
    op.add_column("product_app_activity_days", sa.Column("plan", sa.String(16)))
    op.create_check_constraint(
        "ck_app_activity_plan",
        "product_app_activity_days",
        "plan IN ('DEMO','FREE','PREMIUM','PLATINUM','UNKNOWN')",
    )
    # Do not manufacture historical tariffs from mutable current subscriptions.


def downgrade() -> None:
    op.drop_constraint("ck_app_activity_plan", "product_app_activity_days", type_="check")
    op.drop_column("product_app_activity_days", "plan")
    op.drop_constraint("ck_client_lease_plan_snapshot", "client_wireguard_leases", type_="check")
    op.drop_column("client_wireguard_leases", "plan_snapshot")
