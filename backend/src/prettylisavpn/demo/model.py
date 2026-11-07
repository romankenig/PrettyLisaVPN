"""Only a keyed digest of the app-scoped device identifier is retained."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class DemoDeviceRecord(Base):
    __tablename__ = "demo_devices"

    identity_digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    installation_id: Mapped[UUID] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
