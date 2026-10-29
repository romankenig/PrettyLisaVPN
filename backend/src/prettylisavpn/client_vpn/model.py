"""Durable customer leases, separate from historical VPN and monitoring peers."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
        CheckConstraint(
            "(right(method, 6) <> '_relay' AND relay_node_id IS NULL AND relay_port IS NULL) OR "
            "(right(method, 6) = '_relay' AND relay_node_id IS NOT NULL AND relay_port IS NOT NULL "
            "AND relay_port BETWEEN 20000 AND 29999 AND relay_node_id <> node_id)",
            name="ck_client_lease_relay",
        ),
        CheckConstraint(
            "(method IN ('wireguard','wireguard_relay') AND address IS NOT NULL "
            "AND engine_port IS NULL) OR "
            "(method NOT IN ('wireguard','wireguard_relay') AND address IS NULL "
            "AND engine_port BETWEEN 40000 AND 49899 AND engine_port IS NOT NULL)",
            name="ck_client_lease_engine",
        ),
        CheckConstraint(
            "method IN ('wireguard','wireguard_relay','vless_reality','vless_reality_relay',"
            "'amneziawg','amneziawg_relay','vless','vless_relay','vmess','vmess_relay',"
            "'hysteria','hysteria_relay',"
            "'sstp','sstp_relay','softether','softether_relay',"
            "'shadowsocks2022','shadowsocks2022_relay','hysteria2','hysteria2_relay',"
            "'hysteria2_salamander','hysteria2_salamander_relay')",
            name="ck_client_lease_method",
        ),
        Index(
            "uq_client_lease_engine_port",
            "node_id",
            "engine_port",
            unique=True,
            postgresql_where=text("removed_at IS NULL AND engine_port IS NOT NULL"),
        ),
        Index(
            "uq_client_lease_relay_port",
            "relay_node_id",
            "relay_port",
            unique=True,
            postgresql_where=text("removed_at IS NULL AND relay_node_id IS NOT NULL"),
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
    method: Mapped[str] = mapped_column(String(32), default="wireguard", server_default="wireguard")
    relay_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fleet_nodes.id", name="fk_client_lease_relay")
    )
    relay_port: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(String(4))
    public_key: Mapped[str] = mapped_column(String(44))
    address: Mapped[str | None] = mapped_column(String(18))
    engine_port: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PROVISIONING")
    is_free: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A Free reservation covers only a short node grant, not the entire daily hour.
    # NULL preserves accounting for historical leases and pre-upgrade workers.
    quota_reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None]
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code: Mapped[str | None] = mapped_column(String(64))


class FreeQuotaResetRecord(Base):
    """An explicit operator reset; historical leases/usage are never rewritten."""

    __tablename__ = "free_quota_resets"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_free_quota_reset_day"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
