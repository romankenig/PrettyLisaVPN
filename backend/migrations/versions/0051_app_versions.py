"""Daily authenticated app-version usage, with an explicit collection boundary."""

import sqlalchemy as sa
from alembic import op

revision = "0051_app_versions"
down_revision = "0050_method_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_analytics_collection",
        sa.Column("app_versions_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE product_analytics_collection SET app_versions_started_at = now()")
    op.create_table(
        "product_app_activity_days",
        sa.Column(
            "device_id",
            sa.Uuid(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app_version", sa.String(100), nullable=True),
        sa.Column("version_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_app_activity_day", "product_app_activity_days", ["day"])


def downgrade() -> None:
    op.drop_table("product_app_activity_days")
    op.drop_column("product_analytics_collection", "app_versions_started_at")
