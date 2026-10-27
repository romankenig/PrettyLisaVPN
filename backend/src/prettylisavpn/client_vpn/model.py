"""Durable customer leases, separate from historical VPN and monitoring peers."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base


class ClientLeaseRecord(Base):
    __tablename__ = "client_wireguard_leases"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_client_lease_request"),
        CheckConstraint(
            "status IN ('PROVISIONING','READY','REVOKING','CLOSED')", name="ck_client_lease_status"
        ),
        Index(
            "uq_client_lease_device",
            "device_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "uq_client_lease_key",
            "public_key",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "uq_client_lease_address",
            "node_id",
            "address",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index(
            "ix_client_lease_due", "next_attempt_at", postgresql_where=text("removed_at IS NULL")
        ),
        Index("ix_client_lease_quota", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID]
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"))
    auth_session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    node_id: Mapped[UUID] = mapped_column(ForeignKey("fleet_nodes.id"))
    country: Mapped[str] = mapped_column(String(4))
    public_key: Mapped[str] = mapped_column(String(44))
    address: Mapped[str] = mapped_column(String(18))
    status: Mapped[str] = mapped_column(String(20), default="PROVISIONING")
    is_free: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None]
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code: Mapped[str | None] = mapped_column(String(64))
