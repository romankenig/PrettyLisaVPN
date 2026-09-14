"""SQLAlchemy mapping for VPN node control-plane metadata."""

from datetime import UTC, datetime
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from prettylisavpn.database import Base
from prettylisavpn.vpn_nodes.domain import VpnNodeHealthStatus, VpnNodeProvider, VpnNodeStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class VpnNodeRecord(Base):
    __tablename__ = "vpn_nodes"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_vpn_nodes_name_not_blank"),
        CheckConstraint(
            "btrim(provider_region) <> ''",
            name="ck_vpn_nodes_provider_region_not_blank",
        ),
        CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name="ck_vpn_nodes_country_code_format",
        ),
        CheckConstraint(
            "city IS NULL OR btrim(city) <> ''",
            name="ck_vpn_nodes_city_not_blank",
        ),
        CheckConstraint(
            "family(public_ipv4) = 4",
            name="ck_vpn_nodes_public_ipv4_family",
        ),
        CheckConstraint(
            "private_ipv4 IS NULL OR family(private_ipv4) = 4",
            name="ck_vpn_nodes_private_ipv4_family",
        ),
        CheckConstraint(
            "wireguard_port BETWEEN 1 AND 65535",
            name="ck_vpn_nodes_wireguard_port_range",
        ),
        CheckConstraint(
            "wireguard_public_key ~ '^[A-Za-z0-9+/]{43}=$'",
            name="ck_vpn_nodes_wireguard_public_key_format",
        ),
        CheckConstraint("capacity > 0", name="ck_vpn_nodes_capacity_positive"),
        CheckConstraint(
            "updated_at >= created_at",
            name="ck_vpn_nodes_timestamps_order",
        ),
        CheckConstraint(
            "health_checked_at IS NULL OR health_checked_at >= created_at",
            name="ck_vpn_nodes_health_checked_after_creation",
        ),
        CheckConstraint(
            "last_seen_at IS NULL OR health_checked_at IS NULL "
            "OR last_seen_at <= health_checked_at",
            name="ck_vpn_nodes_last_seen_before_health_check",
        ),
        Index("ix_vpn_nodes_status_country_code", "status", "country_code"),
        Index(
            "ix_vpn_nodes_country_free_status",
            "country_code",
            "is_available_for_free",
            "status",
        ),
        Index("ix_vpn_nodes_provider_region", "provider", "provider_region"),
        Index("ix_vpn_nodes_last_seen_at", "last_seen_at"),
        Index(
            "ix_vpn_nodes_effective_availability",
            "status",
            "health_status",
            "last_seen_at",
        ),
        UniqueConstraint("name", name="uq_vpn_nodes_name"),
        UniqueConstraint(
            "public_ipv4",
            "wireguard_port",
            name="uq_vpn_nodes_public_endpoint",
        ),
        UniqueConstraint(
            "wireguard_public_key",
            name="uq_vpn_nodes_wireguard_public_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[VpnNodeProvider] = mapped_column(
        Enum(
            VpnNodeProvider,
            name="vpn_node_provider",
            values_callable=lambda enum: [provider.value for provider in enum],
        )
    )
    provider_region: Mapped[str] = mapped_column(String(64))
    country_code: Mapped[str] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(255))
    public_ipv4: Mapped[IPv4Address] = mapped_column(INET)
    private_ipv4: Mapped[IPv4Address | None] = mapped_column(INET)
    wireguard_port: Mapped[int] = mapped_column(Integer)
    wireguard_public_key: Mapped[str] = mapped_column(String(44))
    capacity: Mapped[int] = mapped_column(Integer)
    is_available_for_free: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    status: Mapped[VpnNodeStatus] = mapped_column(
        Enum(
            VpnNodeStatus,
            name="vpn_node_status",
            values_callable=lambda enum: [status.value for status in enum],
        ),
        default=VpnNodeStatus.OFFLINE,
        server_default=VpnNodeStatus.OFFLINE.value,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[VpnNodeHealthStatus] = mapped_column(
        Enum(
            VpnNodeHealthStatus,
            name="vpn_node_health_status",
            values_callable=lambda enum: [status.value for status in enum],
        ),
        default=VpnNodeHealthStatus.UNKNOWN,
        server_default=VpnNodeHealthStatus.UNKNOWN.value,
    )
    health_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
