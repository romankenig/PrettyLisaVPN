"""VPN session domain values and entity."""

from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address
from uuid import UUID, uuid4

from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import FREE_ENTITLEMENTS


class VpnSessionStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DISCONNECTED = "DISCONNECTED"
    FAILED = "FAILED"


def _validate_wireguard_public_key(public_key: str) -> str:
    normalized = public_key.strip()
    try:
        decoded = b64decode(normalized, validate=True)
    except (Base64Error, ValueError) as error:
        raise ValueError("client_wireguard_public_key must be valid base64") from error
    if len(normalized) != 44 or len(decoded) != 32:
        raise ValueError("client_wireguard_public_key must encode exactly 32 bytes")
    return normalized


def _normalize_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class VpnSession:
    """Control-plane allocation and lifecycle state for one VPN connection."""

    id: UUID
    user_id: UUID
    device_id: UUID
    vpn_node_id: UUID
    client_wireguard_public_key: str
    allocated_client_ipv4: IPv4Address
    plan_snapshot: SubscriptionPlan
    status: VpnSessionStatus
    started_at: datetime
    expires_at: datetime | None
    disconnected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "client_wireguard_public_key",
            _validate_wireguard_public_key(self.client_wireguard_public_key),
        )
        if not isinstance(self.allocated_client_ipv4, IPv4Address):
            raise ValueError("allocated_client_ipv4 must be an IPv4 address")
        for field_name in (
            "started_at",
            "expires_at",
            "disconnected_at",
            "created_at",
            "updated_at",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_utc(getattr(self, field_name), field_name),
            )
        if self.plan_snapshot is SubscriptionPlan.FREE and self.expires_at is None:
            raise ValueError("FREE VPN sessions must expire")
        if self.status is VpnSessionStatus.EXPIRED and self.expires_at is None:
            raise ValueError("EXPIRED VPN sessions must have expires_at")
        if self.expires_at is not None and self.expires_at <= self.started_at:
            raise ValueError("expires_at must be after started_at")
        if self.started_at < self.created_at:
            raise ValueError("started_at must not be before created_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        if self.disconnected_at is not None and self.disconnected_at < self.started_at:
            raise ValueError("disconnected_at must not be before started_at")
        if (self.status is VpnSessionStatus.DISCONNECTED) != (self.disconnected_at is not None):
            raise ValueError("status and disconnected_at are inconsistent")

    @classmethod
    def new(
        cls,
        *,
        user_id: UUID,
        device_id: UUID,
        vpn_node_id: UUID,
        client_wireguard_public_key: str,
        allocated_client_ipv4: IPv4Address,
        plan_snapshot: SubscriptionPlan,
        now: datetime,
        free_session_limit: timedelta | None = FREE_ENTITLEMENTS.vpn_session_limit,
    ) -> "VpnSession":
        """Create a pending allocation with an expiry computed by the control plane."""
        if plan_snapshot is SubscriptionPlan.FREE:
            if free_session_limit is None or free_session_limit <= timedelta(0):
                raise ValueError("free_session_limit must be positive")
            expires_at = now + free_session_limit
        else:
            expires_at = None
        return cls(
            id=uuid4(),
            user_id=user_id,
            device_id=device_id,
            vpn_node_id=vpn_node_id,
            client_wireguard_public_key=client_wireguard_public_key,
            allocated_client_ipv4=allocated_client_ipv4,
            plan_snapshot=plan_snapshot,
            status=VpnSessionStatus.PENDING,
            started_at=now,
            expires_at=expires_at,
            disconnected_at=None,
            created_at=now,
            updated_at=now,
        )

    def is_live(self) -> bool:
        return self.status in (VpnSessionStatus.PENDING, VpnSessionStatus.ACTIVE)
