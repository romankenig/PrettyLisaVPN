"""Connection policy metadata; node identity stays inside the control plane."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    country: str
    node_id: UUID | None
    port: int
    protocol: str = "WIREGUARD"
    # NATIVE preserves the existing locally configured packet transport policy.
    transport: str = "NATIVE"
    encryption_mode: str = "WIREGUARD"
    obfuscation_mode: str = "NATIVE"
    mtu: int = 1280
    dns_mode: str = "VPN"
    routing_mode: str = "FULL_TUNNEL"
