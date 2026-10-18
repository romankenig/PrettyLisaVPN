"""Record the last successful OTP login without inferring historical timestamps."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_device_last_login"
down_revision: str | None = "0017_profile_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "last_login_at")
