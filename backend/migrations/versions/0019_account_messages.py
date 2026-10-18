"""Persist immutable account messages and account-wide delivery/read receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_account_messages"
down_revision: str | None = "0018_device_last_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("current_revision >= 0", name="ck_account_messages_revision"),
    )
    op.create_table(
        "account_message_revisions",
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("account_messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("acknowledgement_floor", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("user_ids", postgresql.JSONB()),
        sa.Column("plans", postgresql.JSONB()),
        sa.Column("platforms", postgresql.JSONB(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("publisher", sa.String(120), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision > 0", name="ck_account_message_revisions_positive"),
        sa.CheckConstraint("acknowledgement_floor > 0 AND acknowledgement_floor <= revision", name="ck_account_message_revisions_ack_floor"),
        sa.CheckConstraint("expires_at IS NULL OR starts_at IS NULL OR expires_at > starts_at", name="ck_account_message_revisions_interval"),
    )
    op.create_index("ix_account_message_revisions_priority", "account_message_revisions", ["priority", "message_id"])
    op.create_table(
        "account_message_receipts",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("message_id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["message_id", "revision"], ["account_message_revisions.message_id", "account_message_revisions.revision"], ondelete="CASCADE", name="fk_account_message_receipts_revision"),
    )


def downgrade() -> None:
    op.drop_table("account_message_receipts")
    op.drop_index("ix_account_message_revisions_priority", table_name="account_message_revisions")
    op.drop_table("account_message_revisions")
    op.drop_table("account_messages")
