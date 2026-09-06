"""Create the initial empty schema baseline.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the initial revision; no business tables exist yet."""


def downgrade() -> None:
    """Remove the initial revision marker; no business tables exist yet."""
