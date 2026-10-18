"""SQLAlchemy mapping for VPN session control-plane state."""

from datetime import UTC, date, datetime
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class VpnSessionRecord(Base):
    __tablename__ = "vpn_sessions"
    __table_args__ = (
        CheckConstraint(
            "client_wireguard_public_key ~ '^[A-Za-z0-9+/]{43}=$'",
            name="ck_vpn_sessions_client_public_key_format",
        ),
        CheckConstraint(
            "family(allocated_client_ipv4) = 4",
            name="ck_vpn_sessions_allocated_ipv4_family",
        ),
        CheckConstraint(
            "plan_snapshot <> 'FREE' OR expires_at IS NOT NULL",
            name="ck_vpn_sessions_free_expires",
        ),
        CheckConstraint(
            "status <> 'EXPIRED' OR expires_at IS NOT NULL",
            name="ck_vpn_sessions_expired_has_expiry",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > started_at",
            name="ck_vpn_sessions_expiry_after_start",
        ),
        CheckConstraint(
            "started_at >= created_at AND updated_at >= created_at",
            name="ck_vpn_sessions_timestamp_order",
        ),
        CheckConstraint(
            "disconnected_at IS NULL OR disconnected_at >= started_at",
            name="ck_vpn_sessions_disconnected_after_start",
        ),
        CheckConstraint(
            "(status = 'DISCONNECTED') = (disconnected_at IS NOT NULL)",
            name="ck_vpn_sessions_status_disconnected_at",
        ),
        CheckConstraint(
            "peer_removed_at IS NULL OR status IN ('EXPIRED', 'DISCONNECTED', 'FAILED')",
            name="ck_vpn_sessions_peer_removed_terminal",
        ),
        Index("ix_vpn_sessions_user_id_created_at", "user_id", "created_at"),
        Index("ix_vpn_sessions_device_id_created_at", "device_id", "created_at"),
        Index("ix_vpn_sessions_node_status", "vpn_node_id", "status"),
        Index(
            "ix_vpn_sessions_cleanup_pending",
            "status",
            postgresql_where=text(
                "peer_removed_at IS NULL AND status IN ('EXPIRED', 'DISCONNECTED', 'FAILED')"
            ),
        ),
        Index(
            "ix_vpn_sessions_status_expires_at",
            "status",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
        Index(
            "uq_vpn_sessions_live_device",
            "device_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
        Index(
            "uq_vpn_sessions_live_ipv4",
            "allocated_client_ipv4",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
        Index(
            "uq_vpn_sessions_live_client_public_key",
            "client_wireguard_public_key",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'ACTIVE')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    vpn_node_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_nodes.id", ondelete="RESTRICT"))
    client_wireguard_public_key: Mapped[str] = mapped_column(String(44))
    allocated_client_ipv4: Mapped[IPv4Address] = mapped_column(INET)
    plan_snapshot: Mapped[SubscriptionPlan] = mapped_column(
        PostgreSQLEnum(
            SubscriptionPlan,
            name="subscription_plan",
            values_callable=lambda enum: [plan.value for plan in enum],
            create_type=False,
        )
    )
    status: Mapped[VpnSessionStatus] = mapped_column(
        Enum(
            VpnSessionStatus,
            name="vpn_session_status",
            values_callable=lambda enum: [status.value for status in enum],
        ),
        default=VpnSessionStatus.PENDING,
        server_default=VpnSessionStatus.PENDING.value,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    peer_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class FreeVpnUsageRecord(Base):
    """Durable account/day reservation, settled once after a session terminates."""

    __tablename__ = "free_vpn_usage"
    __table_args__ = (
        CheckConstraint("reserved_until > reserved_from", name="ck_free_vpn_usage_period"),
        Index("ix_free_vpn_usage_user_day", "user_id", "day"),
    )
    session_id: Mapped[UUID] = mapped_column(ForeignKey("vpn_sessions.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reserved_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

