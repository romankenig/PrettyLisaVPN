"""Create subscriptions and grant existing users FREE plans.

Revision ID: 0006_subscriptions
Revises: 0005_devices
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_subscriptions"
down_revision: str | None = "0005_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

subscription_plan = postgresql.ENUM("FREE", "PREMIUM", name="subscription_plan", create_type=False)
subscription_status = postgresql.ENUM(
    "ACTIVE", "CANCELED", "EXPIRED", name="subscription_status", create_type=False
)


def upgrade() -> None:
    """Create subscriptions and backfill a FREE subscription for every user."""
    subscription_plan.create(op.get_bind(), checkfirst=True)
    subscription_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan", subscription_plan, server_default="FREE", nullable=False),
        sa.Column("status", subscription_status, server_default="ACTIVE", nullable=False),
        sa.Column(
            "current_period_start",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plan <> 'FREE' OR NOT auto_renew",
            name=op.f("ck_subscriptions_free_no_auto_renew"),
        ),
        sa.CheckConstraint(
            "current_period_end IS NULL OR current_period_end > current_period_start",
            name=op.f("ck_subscriptions_period"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("user_id", name=op.f("uq_subscriptions_user_id")),
    )
    op.create_index(
        "ix_subscriptions_status_current_period_end",
        "subscriptions",
        ["status", "current_period_end"],
        unique=False,
        postgresql_where=sa.text("current_period_end IS NOT NULL"),
    )
    op.execute(
        """
        INSERT INTO subscriptions (
            id, user_id, plan, status, current_period_start, current_period_end,
            auto_renew, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), id, 'FREE', 'ACTIVE', created_at, NULL,
            false, created_at, updated_at
        FROM users
        """
    )


def downgrade() -> None:
    """Drop subscriptions and their enum types."""
    op.drop_index("ix_subscriptions_status_current_period_end", table_name="subscriptions")
    op.drop_table("subscriptions")
    subscription_status.drop(op.get_bind(), checkfirst=True)
    subscription_plan.drop(op.get_bind(), checkfirst=True)
