"""Daily activity-time cohorts and server-owned product analytics snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_product_analytics"
down_revision = "0040_traffic_catalog_refresh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_activity_days",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "plan IN ('FREE','PREMIUM','PLATINUM','UNKNOWN')", name="ck_activity_plan"
        ),
    )
    op.create_index("ix_product_activity_day", "product_activity_days", ["day"])
    op.create_table(
        "product_analytics_snapshots",
        sa.Column("through_date", sa.Date(), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "product_analytics_collection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("id = 1", name="ck_analytics_collection_singleton"),
    )
    op.execute(sa.text("INSERT INTO product_analytics_collection (id) VALUES (1)"))


def downgrade() -> None:
    op.drop_table("product_analytics_collection")
    op.drop_table("product_analytics_snapshots")
    op.drop_table("product_activity_days")
