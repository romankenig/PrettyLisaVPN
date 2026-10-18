"""SQLAlchemy mapping for devices."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class DeviceRecord(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "(status = 'ACTIVE' AND revoked_at IS NULL) OR "
            "(status = 'REVOKED' AND revoked_at IS NOT NULL)",
            name="ck_devices_status_revoked_at",
        ),
        Index(
            "ix_devices_active_user_id",
            "user_id",
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        UniqueConstraint("user_id", "installation_id", name="uq_devices_user_id_installation_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    installation_id: Mapped[UUID]
    platform: Mapped[DevicePlatform] = mapped_column(Enum(DevicePlatform, name="device_platform"))
    device_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status"), default=DeviceStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
