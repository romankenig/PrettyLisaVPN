"""Implementation capabilities and operator-owned node profile declarations."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileId(StrEnum):
    WIREGUARD_UDP = "WIREGUARD_UDP"
    OPENVPN_TLS_TCP = "OPENVPN_TLS_TCP"
    MASQUE_QUIC = "MASQUE_QUIC"


@dataclass(frozen=True, slots=True)
class ProfileCapabilities:
    protocol: str
    transport: str
    supported_ports: tuple[int, ...] | None  # None: any valid configurable port
    default_port: int
    encryption: str
    supports_obfuscation: bool = False
    supports_ipv6: bool = False  # Current integration contract, not theoretical protocol support
    supports_full_tunnel: bool = True
    resembles_ordinary_tls: bool = False


PROFILES = {
    ProfileId.WIREGUARD_UDP: ProfileCapabilities("WIREGUARD", "UDP", None, 51820, "WIREGUARD"),
    ProfileId.OPENVPN_TLS_TCP: ProfileCapabilities(
        "OPENVPN", "TCP", (443,), 443, "TLS_1_3_AES_256_GCM"
    ),
    ProfileId.MASQUE_QUIC: ProfileCapabilities("MASQUE", "UDP", (443,), 443, "TLS_1_3_QUIC"),
}


class NodeConnectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ProfileId
    ports: tuple[Annotated[int, Field(strict=True, ge=1, le=65535)], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ports(self) -> "NodeConnectionProfile":
        supported = PROFILES[self.profile].supported_ports
        if len(set(self.ports)) != len(self.ports):
            raise ValueError("profile ports must be unique")
        if supported is not None and any(port not in supported for port in self.ports):
            raise ValueError("port is unsupported by this profile")
        return self


def validate_node_profiles(profiles: tuple[NodeConnectionProfile, ...]) -> None:
    if any(not isinstance(profile, NodeConnectionProfile) for profile in profiles):
        raise ValueError("profiles must be validated NodeConnectionProfile values")
    if len({profile.profile for profile in profiles}) != len(profiles):
        raise ValueError("node profile identifiers must be unique")
