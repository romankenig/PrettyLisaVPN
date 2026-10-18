"""Immutable published revisions and account-wide delivery/read receipts."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class MessageRecord(Base):
    __tablename__ = "account_messages"
    __table_args__ = (
        CheckConstraint("current_revision >= 0", name="ck_account_messages_revision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    current_revision: Mapped[int] = mapped_column(Integer, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRevisionRecord(Base):
    __tablename__ = "account_message_revisions"
    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_account_message_revisions_positive"),
        CheckConstraint(
            "acknowledgement_floor > 0 AND acknowledgement_floor <= revision",
            name="ck_account_message_revisions_ack_floor",
        ),
        CheckConstraint(
            "expires_at IS NULL OR starts_at IS NULL OR expires_at > starts_at",
            name="ck_account_message_revisions_interval",
        ),
        Index("ix_account_message_revisions_priority", "priority", "message_id"),
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("account_messages.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    acknowledgement_floor: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_ids: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    plans: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    platforms: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    publisher: Mapped[str] = mapped_column(String(120))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageReceiptRecord(Base):
    __tablename__ = "account_message_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "revision"],
            ["account_message_revisions.message_id", "account_message_revisions.revision"],
            ondelete="CASCADE", name="fk_account_message_receipts_revision",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
