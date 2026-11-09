"""Recover the last refresh rotation after a lost response without storing tokens.

Revision ID: 0048
Revises: 0047
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_refresh_retry"
down_revision = "0047_active_user_speed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions", sa.Column("previous_refresh_token_hash", sa.LargeBinary(32), nullable=True)
    )
    op.add_column("auth_sessions", sa.Column("refresh_rotation_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_auth_sessions_refresh_retry_metadata",
        "auth_sessions",
        "(previous_refresh_token_hash IS NULL AND refresh_rotation_id IS NULL) OR "
        "(previous_refresh_token_hash IS NOT NULL AND "
        "octet_length(previous_refresh_token_hash) = 32 AND refresh_rotation_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_auth_sessions_refresh_retry_metadata", "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "refresh_rotation_id")
    op.drop_column("auth_sessions", "previous_refresh_token_hash")
