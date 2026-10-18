"""Content and screenshots share one PostgreSQL transaction with the outbox."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class SupportRequestRecord(Base):
    __tablename__ = "support_requests"
    __table_args__ = (
        Index("ix_support_requests_delivery", "status", "next_attempt_at"),
        Index("ix_support_requests_created", "created_at"),
        Index("ix_support_requests_user_created", "user_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[str] = mapped_column(String(16), server_default="ACCEPTED")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportAttachmentRecord(Base):
    __tablename__ = "support_attachments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "request_id"],
            ["support_requests.user_id", "support_requests.request_id"],
            ondelete="CASCADE",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    media_type: Mapped[str] = mapped_column(String(32))
