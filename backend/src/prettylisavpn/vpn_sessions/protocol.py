"""Connection policy metadata; node identity stays inside the control plane."""

from dataclasses import dataclass
from uuid import UUID

from prettylisavpn.vpn_nodes.profiles import PROFILES, ProfileId
from prettylisavpn.vpn_sessions.obfuscation import validate_obfuscation


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
    obfuscation_version: int | None = None
    transport_parameters: dict[str, int] | None = None

    @classmethod
    def for_profile(
        cls, profile_id: ProfileId, country: str, node_id: UUID | None, port: int | None = None
    ) -> "ConnectionConfig":
        profile = PROFILES[profile_id]
        return cls(
            country=country,
            node_id=node_id,
            port=profile.default_port if port is None else port,
            protocol=profile.protocol,
            transport=profile.transport,
            encryption_mode=profile.encryption,
            obfuscation_mode="NONE",
        )

    def __post_init__(self) -> None:
        validate_obfuscation(
            self.protocol,
            self.transport,
            self.obfuscation_mode,
            self.obfuscation_version,
            self.transport_parameters,
            self.mtu,
        )
        if (
            len(self.country) != 2
            or not self.country.isascii()
            or not self.country.isupper()
            or not self.country.isalpha()
        ):
            raise ValueError("country must be a two-letter uppercase code")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.mtu != 1280 or self.dns_mode != "VPN" or self.routing_mode != "FULL_TUNNEL":
            raise ValueError("unsupported network policy")
        # Existing clients keep the original native transport policy.
        if (self.protocol, self.transport, self.encryption_mode, self.obfuscation_mode) == (
            "WIREGUARD",
            "NATIVE",
            "WIREGUARD",
            "NATIVE",
        ):
            return
        if not any(
            self.protocol == profile.protocol
            and self.transport == profile.transport
            and self.encryption_mode == profile.encryption
            and (profile.supported_ports is None or self.port in profile.supported_ports)
            for profile in PROFILES.values()
        ):
            raise ValueError("unsupported connection profile")
