"""Create privacy-conscious product events.

Revision ID: 0007_product_events
Revises: 0006_subscriptions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_product_events"
down_revision: str | None = "0006_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

product_event_name = postgresql.ENUM(
    "otp_requested",
    "otp_sent",
    "otp_verified",
    "login_succeeded",
    "login_failed",
    "device_registered",
    "device_revoked",
    "token_refreshed",
    "logout",
    name="product_event_name",
    create_type=False,
)


def upgrade() -> None:
    """Create product events and their lookup indexes."""
    product_event_name.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "product_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("event_name", product_event_name, nullable=False),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(properties) = 'object'",
            name=op.f("ck_product_events_properties_object"),
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_product_events_device_id_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_product_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_events")),
    )
    op.create_index(
        "ix_product_events_device_id_occurred_at",
        "product_events",
        ["device_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_events_event_name_occurred_at",
        "product_events",
        ["event_name", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_events_user_id_occurred_at",
        "product_events",
        ["user_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop product events and their enum type."""
    op.drop_index("ix_product_events_user_id_occurred_at", table_name="product_events")
    op.drop_index("ix_product_events_event_name_occurred_at", table_name="product_events")
    op.drop_index("ix_product_events_device_id_occurred_at", table_name="product_events")
    op.drop_table("product_events")
    product_event_name.drop(op.get_bind(), checkfirst=True)
