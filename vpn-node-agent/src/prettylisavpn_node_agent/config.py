"""Validated environment configuration for the node agent."""

import os
from dataclasses import dataclass, field
from ipaddress import IPv4Interface, IPv4Network, ip_interface, ip_network
from pathlib import Path


def _required_environment(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


@dataclass(frozen=True, slots=True)
class AgentSettings:
    auth_token: str = field(repr=False)
    client_subnet: IPv4Network
    gateway: IPv4Interface
    interface: str = "wg0"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443
    tls_certificate: Path = Path("/etc/prettylisavpn-agent/tls/server.crt")
    tls_private_key: Path = Path("/etc/prettylisavpn-agent/tls/server.key")
    tls_client_ca: Path = Path("/etc/prettylisavpn-agent/tls/client-ca.crt")
    recent_handshake_seconds: int = 180

    def __post_init__(self) -> None:
        if len(self.auth_token) < 32:
            raise ValueError("NODE_AGENT_AUTH_TOKEN must contain at least 32 characters")
        if (
            not self.interface
            or len(self.interface) > 15
            or not all(character.isalnum() or character in "_.-" for character in self.interface)
        ):
            raise ValueError("NODE_AGENT_WIREGUARD_INTERFACE is invalid")
        if self.gateway.network != self.client_subnet:
            raise ValueError("NODE_AGENT_GATEWAY_CIDR must describe NODE_AGENT_CLIENT_SUBNET")
        if self.gateway.ip in (
            self.client_subnet.network_address,
            self.client_subnet.broadcast_address,
        ):
            raise ValueError("NODE_AGENT_GATEWAY_CIDR must use a host address")
        if not 1 <= self.bind_port <= 65535:
            raise ValueError("NODE_AGENT_BIND_PORT must be between 1 and 65535")
        if self.recent_handshake_seconds <= 0:
            raise ValueError("NODE_AGENT_RECENT_HANDSHAKE_SECONDS must be positive")

    @classmethod
    def from_environment(cls) -> "AgentSettings":
        subnet = ip_network(os.getenv("NODE_AGENT_CLIENT_SUBNET", "10.77.0.0/16"), strict=True)
        gateway = ip_interface(os.getenv("NODE_AGENT_GATEWAY_CIDR", "10.77.0.1/16"))
        if not isinstance(subnet, IPv4Network) or not isinstance(gateway, IPv4Interface):
            raise ValueError("node agent supports IPv4 WireGuard networks only")
        return cls(
            auth_token=_required_environment("NODE_AGENT_AUTH_TOKEN"),
            client_subnet=subnet,
            gateway=gateway,
            interface=os.getenv("NODE_AGENT_WIREGUARD_INTERFACE", "wg0"),
            bind_host=os.getenv("NODE_AGENT_BIND_HOST", "0.0.0.0"),
            bind_port=int(os.getenv("NODE_AGENT_BIND_PORT", "8443")),
            tls_certificate=Path(
                os.getenv(
                    "NODE_AGENT_TLS_CERTIFICATE",
                    "/etc/prettylisavpn-agent/tls/server.crt",
                )
            ),
            tls_private_key=Path(
                os.getenv(
                    "NODE_AGENT_TLS_PRIVATE_KEY",
                    "/etc/prettylisavpn-agent/tls/server.key",
                )
            ),
            tls_client_ca=Path(
                os.getenv(
                    "NODE_AGENT_TLS_CLIENT_CA",
                    "/etc/prettylisavpn-agent/tls/client-ca.crt",
                )
            ),
            recent_handshake_seconds=int(os.getenv("NODE_AGENT_RECENT_HANDSHAKE_SECONDS", "180")),
        )
