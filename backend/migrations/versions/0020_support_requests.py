"""Durable account-scoped support requests, raster attachments and delivery state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_support_requests"
down_revision: str | None = "0019_account_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_requests",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(none_as_null=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACCEPTED"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_support_requests_delivery", "support_requests", ["status", "next_attempt_at"]
    )
    op.create_index("ix_support_requests_created", "support_requests", ["created_at"])
    op.create_index(
        "ix_support_requests_user_created", "support_requests", ["user_id", "created_at"]
    )
    op.create_table(
        "support_attachments",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "request_id"],
            ["support_requests.user_id", "support_requests.request_id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("support_attachments")
    op.drop_index("ix_support_requests_user_created", table_name="support_requests")
    op.drop_index("ix_support_requests_created", table_name="support_requests")
    op.drop_index("ix_support_requests_delivery", table_name="support_requests")
    op.drop_table("support_requests")
