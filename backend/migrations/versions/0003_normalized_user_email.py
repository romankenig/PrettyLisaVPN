"""Enforce normalized user emails in PostgreSQL.

Revision ID: 0003_normalized_user_email
Revises: 0002_users
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_normalized_user_email"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reject emails that are not already trimmed and lowercase."""
    op.create_check_constraint(
        "ck_users_email_normalized",
        "users",
        "email = lower(btrim(email))",
    )


def downgrade() -> None:
    """Remove the database-level email normalization invariant."""
    op.drop_constraint("ck_users_email_normalized", "users", type_="check")
