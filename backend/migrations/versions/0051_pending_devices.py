"""Allow OTP-authenticated device management before an active device slot is available."""

import sqlalchemy as sa
from alembic import op

revision = "0051_pending_devices"
down_revision = "0050_method_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE device_status ADD VALUE IF NOT EXISTS 'PENDING'")
    op.drop_constraint("ck_devices_status_revoked_at", "devices", type_="check")
    op.create_check_constraint(
        "ck_devices_status_revoked_at",
        "devices",
        "(status IN ('ACTIVE', 'PENDING') AND revoked_at IS NULL) OR "
        "(status = 'REVOKED' AND revoked_at IS NOT NULL)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM devices WHERE status = 'PENDING')")
    ):
        raise RuntimeError("Pending device sessions require a compatible application rollback")
    op.drop_constraint("ck_devices_status_revoked_at", "devices", type_="check")
    op.create_check_constraint(
        "ck_devices_status_revoked_at",
        "devices",
        "(status = 'ACTIVE' AND revoked_at IS NULL) OR "
        "(status = 'REVOKED' AND revoked_at IS NOT NULL)",
    )
    # PostgreSQL enum members cannot be removed in place; keep the unused member.
