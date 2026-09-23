"""Operator-imported node capabilities; declarations and unit tests confer no trust."""

from datetime import datetime, timedelta
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator


class ProfileHealth(StrEnum):
    UNTESTED = "UNTESTED"
    UNIT_TESTED = "UNIT_TESTED"
    SERVER_READY = "SERVER_READY"
    E2E_VERIFIED = "E2E_VERIFIED"
    E2E_FAILED = "E2E_FAILED"


class ProfileEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    node_id: UUID
    profile: str
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: AwareDatetime
    transport_established: StrictBool
    tunnel: StrictBool
    dns: StrictBool
    https: StrictBool
    internet: StrictBool
    route_verified: StrictBool
    egress_ip: IPv4Address | None

    def succeeds(self, node_id: UUID, egress: IPv4Address, now: datetime) -> bool:
        return (
            self.node_id == node_id
            and self.egress_ip == egress
            and all(
                (
                    self.transport_established,
                    self.tunnel,
                    self.dns,
                    self.https,
                    self.internet,
                    self.route_verified,
                )
            )
            and timedelta(0) <= now - self.checked_at <= timedelta(hours=24)
        )


class DeployedConnectionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,14}$")
    protocol: Literal["WIREGUARD", "OPENVPN", "MASQUE"]
    transport: Literal["UDP", "TCP"]
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    encryption_mode: Literal["WIREGUARD", "TLS_1_3_AES_256_GCM", "TLS_1_3_QUIC"]
    obfuscation_mode: Literal["NONE", "SIMPLE_PACKET_WRAPPER_V1", "TLS_TRANSPORT"]
    free_available: StrictBool = False
    enabled: StrictBool = False
    health_status: ProfileHealth = ProfileHealth.UNTESTED
    configuration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence: ProfileEvidence | None = None

    @model_validator(mode="after")
    def compatible(self) -> "DeployedConnectionProfile":
        matrix = {
            ("WIREGUARD", "UDP", "NONE"): "WIREGUARD",
            ("WIREGUARD", "UDP", "SIMPLE_PACKET_WRAPPER_V1"): "WIREGUARD",
            ("OPENVPN", "TCP", "NONE"): "TLS_1_3_AES_256_GCM",
            ("OPENVPN", "TCP", "TLS_TRANSPORT"): "TLS_1_3_AES_256_GCM",
            ("MASQUE", "UDP", "NONE"): "TLS_1_3_QUIC",
        }
        if (
            matrix.get((self.protocol, self.transport, self.obfuscation_mode))
            != self.encryption_mode
        ):
            raise ValueError("unsupported profile combination")
        if self.protocol != "WIREGUARD" and self.port != 443:
            raise ValueError("TLS/QUIC requires port 443")
        if self.health_status is ProfileHealth.E2E_VERIFIED and self.evidence is None:
            raise ValueError("E2E_VERIFIED requires evidence")
        return self

    def usable(self, node_id: UUID, egress: IPv4Address, now: datetime) -> bool:
        return (
            self.enabled
            and self.health_status is ProfileHealth.E2E_VERIFIED
            and self.evidence is not None
            and self.evidence.profile == self.id
            and self.evidence.configuration_sha256 == self.configuration_sha256
            and self.evidence.succeeds(node_id, egress, now)
        )
