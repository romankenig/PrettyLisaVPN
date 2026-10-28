"""Protocol-neutral lifecycle contracts and deterministic monitoring rules."""

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Interface
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Value(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class FleetError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code, self.status = code, status
        super().__init__(code)


NodeGroup = Literal["INTERMEDIATE", "FREE", "PREMIUM"]


class NodeInput(Value):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    host: IPv4Address
    credential_ref: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    expected_egress_ips: list[IPv4Address] = Field(min_length=1, max_length=4)
    capacity: int = Field(default=100, ge=1, le=10000)
    is_available_for_free: bool = False
    group: NodeGroup | None = None

    @model_validator(mode="after")
    def group_access(self) -> Self:
        if self.group is None:
            self.group = "FREE" if self.is_available_for_free else "PREMIUM"
        elif "is_available_for_free" in self.model_fields_set and self.is_available_for_free != (
            self.group == "FREE"
        ):
            raise ValueError("Free eligibility must match the node group")
        self.is_available_for_free = self.group == "FREE"
        return self

    @field_validator("host")
    @classmethod
    def public_host(cls, value: IPv4Address) -> IPv4Address:
        if not value.is_global:
            raise ValueError("A public IPv4 address is required")
        return value

    @field_validator("expected_egress_ips")
    @classmethod
    def public_egress(cls, values: list[IPv4Address]) -> list[IPv4Address]:
        if any(not item.is_global for item in values) or len(values) != len(set(values)):
            raise ValueError("Unique public egress addresses are required")
        return values


class WireGuardConfig(Value):
    listen_port: int = Field(default=51820, ge=1024, le=65535)
    address: IPv4Interface
    mtu: int = Field(default=1380, ge=1280, le=1420)

    @model_validator(mode="after")
    def private_subnet(self) -> Self:
        private = ("10.", "192.168.")
        ip = self.address.ip
        rfc1918 = (
            str(ip).startswith(private) or int(ip) >> 20 == int(IPv4Address("172.16.0.0")) >> 20
        )
        if not rfc1918 or not 24 <= self.address.network.prefixlen <= 28:
            raise ValueError("Use an RFC1918 /24 to /28 subnet")
        if ip != self.address.network.network_address + 1:
            raise ValueError("The server must use the first usable subnet address")
        return self


class NodeUpdate(Value):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
    group: NodeGroup


class Node(Value):
    id: UUID
    name: str
    country_code: str
    host: str
    credential_ref: str
    expected_egress_ips: list[str]
    capacity: int
    is_available_for_free: bool
    enabled: bool
    group: NodeGroup = "PREMIUM"


class RelayAccess(Value):
    id: UUID
    listen_port: int = Field(ge=20000, le=29999)
    target_host: IPv4Address
    target_port: int = Field(ge=1024, le=65535)
    expires_at: datetime

    @field_validator("target_host")
    @classmethod
    def public_target(cls, value: IPv4Address) -> IPv4Address:
        if not value.is_global:
            raise ValueError("A public target is required")
        return value


class Observation(Value):
    # Only aggregates: no peer IPs, browsing destinations, URLs or private keys.
    status: Literal["HEALTHY", "DEGRADED", "FAILED", "UNKNOWN"]
    mode: Literal["SYNTHETIC", "PASSIVE", "CONTROL"]
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    observed_at: datetime
    active_connections: int = Field(default=0, ge=0)
    authorized_connections: int = Field(default=0, ge=0)
    handshake_ok: bool | None = None
    dns_ok: bool | None = None
    https_ok: bool | None = None
    egress_ok: bool | None = None
    connection_ms: float | None = Field(default=None, ge=0, le=600000)
    download_mbps: float | None = Field(default=None, ge=0, le=1000000)
    upload_mbps: float | None = Field(default=None, ge=0, le=1000000)
    rx_bytes: int = Field(default=0, ge=0)
    tx_bytes: int = Field(default=0, ge=0)
    cleanup_confirmed: bool = True

    @field_validator("observed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTC timestamp required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def honest_success(self) -> Self:
        if self.status == "HEALTHY" and self.mode == "SYNTHETIC":
            if not all((self.handshake_ok, self.dns_ok, self.https_ok, self.egress_ok)):
                raise ValueError("A healthy synthetic check requires every network stage")
        if self.status == "HEALTHY" and self.mode == "CONTROL":
            raise ValueError("Control reachability cannot prove VPN health")
        if self.mode != "SYNTHETIC" and any(
            item is not None for item in (self.dns_ok, self.https_ok, self.egress_ok)
        ):
            raise ValueError("Passive/control observations cannot prove end-to-end access")
        if not self.cleanup_confirmed and self.status == "HEALTHY":
            raise ValueError("Unconfirmed cleanup cannot be healthy")
        return self


class MethodState(Value):
    installed: bool
    public_key: str | None = None
    configuration: dict[str, object] = Field(default_factory=dict)
    authorized_connections: int = Field(default=0, ge=0)
    active_connections: int = Field(default=0, ge=0)


class Access(Value):
    purpose: Literal["monitor", "client"] = "monitor"
    id: UUID
    public_key: str = Field(pattern=r"^[A-Za-z0-9+/]{43}=$")
    address: str
    expires_at: datetime


class VpnMethod(ABC):
    """Implement protocol details; queueing/auth/fencing stay in the application layer."""

    name: str

    @abstractmethod
    async def inspect(self, node: Node) -> MethodState: ...

    @abstractmethod
    async def plan(self, node: Node, config: dict[str, object]) -> dict[str, object]: ...

    @abstractmethod
    async def configure(
        self, node: Node, config: dict[str, object], operation_id: UUID
    ) -> MethodState: ...

    @abstractmethod
    async def grant_access(self, node: Node, access: Access) -> None: ...

    @abstractmethod
    async def revoke_access(self, node: Node, access: Access) -> bool: ...

    async def grant_relay(self, node: Node, access: RelayAccess) -> None:
        raise FleetError("RELAY_UNSUPPORTED")

    async def revoke_relay(self, node: Node, access: RelayAccess) -> bool:
        raise FleetError("RELAY_UNSUPPORTED")

    @abstractmethod
    async def observe(self, node: Node) -> Observation: ...

    @abstractmethod
    async def probe(self, source: Node, target: Node, check_id: UUID) -> Observation: ...

    @abstractmethod
    async def rollback(self, node: Node, operation_id: UUID) -> None: ...


def hourly_slot(node_id: UUID, at: datetime, roster: list[UUID]) -> datetime:
    """Evenly spread a stable roster, with bounded per-node jitter; never catch up in bursts."""
    ordered = sorted(set(roster) | {node_id}, key=str)
    width = 3600 / len(ordered)
    index = ordered.index(node_id)
    jitter = int.from_bytes(hashlib.sha256(node_id.bytes).digest()[:2], "big") / 65535
    offset = min(3599, (index + 0.25 + jitter * 0.5) * width)
    slot = at.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(seconds=offset)
    return slot if slot > at else slot + timedelta(hours=1)


def source_order(target: UUID, at: datetime, roster: list[UUID]) -> list[UUID]:
    ordered = sorted(set(roster), key=str)
    if target not in ordered or len(ordered) < 2:
        return []
    rotation = int(at.timestamp()) // 3600 % (len(ordered) - 1) + 1
    start = ordered.index(target)
    offsets = list(range(rotation, len(ordered))) + list(range(1, rotation))
    return [ordered[(start + offset) % len(ordered)] for offset in offsets]


def server_quality(
    observations: list[Observation],
    capacity: int,
    now: datetime,
    *,
    speed_target_mbps: float = 100,
    connection_target_ms: float = 1000,
    quality_weights: tuple[float, float, float, float] = (0.50, 0.20, 0.15, 0.15),
) -> dict[str, object]:
    recent = sorted(
        (item for item in observations if now - timedelta(hours=24) <= item.observed_at <= now),
        key=lambda item: item.observed_at,
    )
    if not recent or now - recent[-1].observed_at > timedelta(minutes=75):
        return {"quality": 0, "available": False, "confidence": "STALE"}
    latest = recent[-1]
    if latest.status in ("FAILED", "UNKNOWN") or not latest.cleanup_confirmed:
        return {"quality": 0, "available": False, "confidence": latest.status}
    valid = [item for item in recent if item.status != "UNKNOWN"]
    weights = [2 ** (-(now - item.observed_at).total_seconds() / 21600) for item in valid]
    success = sum(
        w * (item.status == "HEALTHY") for w, item in zip(weights, valid, strict=True)
    ) / sum(weights)
    spare = max(0, 1 - latest.active_connections / capacity)
    full = [item for item in recent if item.mode == "SYNTHETIC" and item.status == "HEALTHY"]
    measured = full[-1] if full else None
    # Missing speed is not inferred from user traffic or invented as maximum throughput.
    connect = (
        min(1, connection_target_ms / max(1, measured.connection_ms))
        if measured and measured.connection_ms is not None
        else 0
    )
    speed = (
        min(1, min(measured.download_mbps, measured.upload_mbps) / speed_target_mbps)
        if measured and measured.download_mbps is not None and measured.upload_mbps is not None
        else 0
    )
    quality = round(
        100
        * sum(
            weight * metric
            for weight, metric in zip(
                quality_weights, (success, spare, connect, speed), strict=True
            )
        )
    )
    return {
        "quality": quality,
        "available": spare > 0
        and latest.authorized_connections < capacity
        and latest.status == "HEALTHY",
        "confidence": "FULL" if latest.mode == "SYNTHETIC" else "PASSIVE",
    }
