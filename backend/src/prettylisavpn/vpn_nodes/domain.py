"""VPN node domain values and entity."""

from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import IPv4Address
from uuid import UUID


class VpnNodeProvider(StrEnum):
    DIGITALOCEAN = "DIGITALOCEAN"


class VpnNodeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"


def _normalize_required(value: str, field_name: str, maximum_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > maximum_length:
        raise ValueError(f"{field_name} must not exceed {maximum_length} characters")
    return normalized


def _normalize_country_code(country_code: str) -> str:
    normalized = country_code.strip().upper()
    if len(normalized) != 2 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError("country_code must be a two-letter ASCII code")
    return normalized


def _validate_wireguard_public_key(public_key: str) -> str:
    normalized = public_key.strip()
    try:
        decoded = b64decode(normalized, validate=True)
    except (Base64Error, ValueError) as error:
        raise ValueError("wireguard_public_key must be valid base64") from error
    if len(normalized) != 44 or len(decoded) != 32:
        raise ValueError("wireguard_public_key must encode exactly 32 bytes")
    return normalized


def _normalize_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class VpnNode:
    """Control-plane description of a separately operated VPN data-plane node."""

    id: UUID
    name: str
    provider: VpnNodeProvider
    provider_region: str
    country_code: str
    city: str | None
    public_ipv4: IPv4Address
    private_ipv4: IPv4Address | None
    wireguard_port: int
    wireguard_public_key: str
    capacity: int
    status: VpnNodeStatus
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_required(self.name, "name", 255))
        object.__setattr__(
            self,
            "provider_region",
            _normalize_required(self.provider_region, "provider_region", 64),
        )
        object.__setattr__(self, "country_code", _normalize_country_code(self.country_code))
        if self.city is not None:
            object.__setattr__(self, "city", _normalize_required(self.city, "city", 255))
        if not isinstance(self.public_ipv4, IPv4Address):
            raise ValueError("public_ipv4 must be an IPv4 address")
        if self.private_ipv4 is not None and not isinstance(self.private_ipv4, IPv4Address):
            raise ValueError("private_ipv4 must be an IPv4 address")
        if not 1 <= self.wireguard_port <= 65535:
            raise ValueError("wireguard_port must be between 1 and 65535")
        object.__setattr__(
            self,
            "wireguard_public_key",
            _validate_wireguard_public_key(self.wireguard_public_key),
        )
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        for field_name in ("last_seen_at", "created_at", "updated_at"):
            object.__setattr__(
                self,
                field_name,
                _normalize_utc(getattr(self, field_name), field_name),
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
