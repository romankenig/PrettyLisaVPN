"""SQLAlchemy mapping for authentication sessions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "octet_length(refresh_token_hash) = 32",
            name="ck_auth_sessions_refresh_token_hash_length",
        ),
        CheckConstraint(
            "(previous_refresh_token_hash IS NULL AND refresh_rotation_id IS NULL) OR "
            "(previous_refresh_token_hash IS NOT NULL AND "
            "octet_length(previous_refresh_token_hash) = 32 AND refresh_rotation_id IS NOT NULL)",
            name="ck_auth_sessions_refresh_retry_metadata",
        ),
        Index("ix_auth_sessions_device_id_revoked_at", "device_id", "revoked_at"),
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    refresh_token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    previous_refresh_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    refresh_rotation_id: Mapped[UUID | None]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
