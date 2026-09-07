"""Create devices.

Revision ID: 0005_devices
Revises: 0004_auth_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_devices"
down_revision: str | None = "0004_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

device_platform = postgresql.ENUM(
    "WINDOWS",
    "MACOS",
    "LINUX",
    "ANDROID",
    "IOS",
    "ANDROID_TV",
    "CHROME_EXTENSION",
    name="device_platform",
    create_type=False,
)
device_status = postgresql.ENUM("ACTIVE", "REVOKED", name="device_status", create_type=False)


def upgrade() -> None:
    """Create device enum types, table, constraints, and active-device index."""
    device_platform.create(op.get_bind(), checkfirst=True)
    device_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("platform", device_platform, nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("status", device_status, nullable=False),
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND revoked_at IS NULL) OR "
            "(status = 'REVOKED' AND revoked_at IS NOT NULL)",
            name=op.f("ck_devices_status_revoked_at"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
        sa.UniqueConstraint(
            "user_id",
            "installation_id",
            name=op.f("uq_devices_user_id_installation_id"),
        ),
    )
    op.create_index(
        "ix_devices_active_user_id",
        "devices",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    """Drop devices and their enum types."""
    op.drop_index("ix_devices_active_user_id", table_name="devices")
    op.drop_table("devices")
    device_status.drop(op.get_bind(), checkfirst=True)
    device_platform.drop(op.get_bind(), checkfirst=True)
