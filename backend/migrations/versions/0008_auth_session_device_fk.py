"""Link authentication sessions to devices.

Revision ID: 0008_auth_session_device_fk
Revises: 0007_product_events
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_auth_session_device_fk"
down_revision: str | None = "0007_product_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Require every authentication session to reference an existing device."""
    op.create_foreign_key(
        op.f("fk_auth_sessions_device_id_devices"),
        "auth_sessions",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove the authentication-session device foreign key."""
    op.drop_constraint(
        op.f("fk_auth_sessions_device_id_devices"),
        "auth_sessions",
        type_="foreignkey",
    )
