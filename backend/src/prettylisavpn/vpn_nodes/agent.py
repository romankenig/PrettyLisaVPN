"""Authenticated mTLS adapter for the VPN Node Control Agent."""

import ssl
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from prettylisavpn.config import Settings
from prettylisavpn.vpn_nodes.domain import VpnNode


class NodeAgentUnavailableError(RuntimeError):
    """The authenticated node agent health state could not be obtained."""


@dataclass(frozen=True, slots=True)
class NodeAgentHealth:
    healthy: bool
    interface_up: bool
    listen_port: int | None


class NodeAgentHealthPort(Protocol):
    async def get_health(self, node: VpnNode) -> NodeAgentHealth: ...


class NodeAgentPeerPort(Protocol):
    async def add_peer(self, node: VpnNode, public_key: str, vpn_ip: IPv4Address) -> None: ...

    async def remove_peer(self, node: VpnNode, public_key: str) -> None: ...

    async def peer_exists(self, node: VpnNode, public_key: str) -> bool: ...


class NodeAgentPort(NodeAgentHealthPort, NodeAgentPeerPort, Protocol):
    pass


class ManagedNodeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: int = Field(ge=1024, le=65535)
    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    server_name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,251}[a-zA-Z0-9]$")
    short_id: str = Field(pattern=r"^(?:[0-9a-f]{2}){1,8}$")


class ManagedNodeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    method: Literal[
        "VLESS_REALITY",
        "VLESS_TLS",
        "VMESS_TLS",
        "TROJAN_TLS",
        "SHADOWSOCKS",
        "SHADOWSOCKS_2022",
        "HYSTERIA2_TLS",
        "HYSTERIA2_SALAMANDER",
    ]
    port: int = Field(ge=1024, le=65535)
    secret: str = Field(repr=False, min_length=16, max_length=128, pattern=r"^[^\r\n\x00]+$")
    server_name: str | None = Field(
        default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,251}[a-zA-Z0-9]$"
    )
    public_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")
    short_id: str | None = Field(default=None, pattern=r"^(?:[0-9a-f]{2}){1,8}$")
    certificate_pin: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    transport: Literal["ws", "grpc", "httpupgrade", "xhttp"] | None = None
    path: Literal["plvpn", "/plvpn"] | None = None
    obfs_secret: str | None = Field(default=None, repr=False, min_length=16, max_length=128)

    @model_validator(mode="after")
    def validate_method(self) -> "ManagedNodeCandidate":
        reality = self.method == "VLESS_REALITY"
        tls = self.method in (
            "VLESS_TLS",
            "VMESS_TLS",
            "TROJAN_TLS",
            "HYSTERIA2_TLS",
            "HYSTERIA2_SALAMANDER",
        )
        if (self.server_name is not None) != (reality or tls):
            raise ValueError("invalid server identity")
        if (
            (self.certificate_pin is not None) != tls
            or (self.public_key is not None) != reality
            or (self.short_id is not None) != reality
        ):
            raise ValueError("invalid server authentication")
        if self.transport is not None and self.method not in (
            "VLESS_TLS",
            "VMESS_TLS",
            "TROJAN_TLS",
        ):
            raise ValueError("invalid transport")
        expected_path = (
            None if self.transport is None else "plvpn" if self.transport == "grpc" else "/plvpn"
        )
        if self.path != expected_path or (self.obfs_secret is not None) != (
            self.method == "HYSTERIA2_SALAMANDER"
        ):
            raise ValueError("invalid transport parameters")
        return self


class ManagedNodePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    profiles: list[ManagedNodeCandidate] = Field(repr=False, min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self) -> "ManagedNodePlan":
        if len({(p.method, p.transport) for p in self.profiles}) != len(self.profiles) or len(
            {p.port for p in self.profiles}
        ) != len(self.profiles):
            raise ValueError("duplicate managed candidate")
        return self


@runtime_checkable
class ManagedNodePort(Protocol):
    async def issue_managed(
        self, node: VpnNode, session_id: UUID, secret: str, expires: datetime
    ) -> ManagedNodeProfile: ...
    async def issue_managed_plan(
        self, node: VpnNode, session_id: UUID, secret: str, expires: datetime
    ) -> ManagedNodePlan: ...
    async def remove_managed(self, node: VpnNode, session_id: UUID) -> None: ...


class _AgentHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["HEALTHY", "UNHEALTHY"]
    interface: str
    interface_up: bool
    listen_port: int | None


class _AgentPeerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str
    vpn_ip: IPv4Address
    latest_handshake_at: datetime | None
    created: bool | None = None


class _AgentRemovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removed: bool


class HttpNodeAgentClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        auth_token: str,
        agent_port: int,
    ) -> None:
        self._client = client
        self._auth_token = auth_token
        self._agent_port = agent_port

    @classmethod
    def from_settings(cls, settings: Settings) -> "HttpNodeAgentClient":
        token = settings.vpn_node_agent_auth_token
        ca = settings.vpn_node_agent_tls_ca
        certificate = settings.vpn_node_agent_tls_client_certificate
        private_key = settings.vpn_node_agent_tls_client_key
        if token is None or ca is None or certificate is None or private_key is None:
            raise ValueError("VPN node agent credentials are not configured")
        tls_context = ssl.create_default_context(cafile=str(ca))
        tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_context.load_cert_chain(certfile=str(certificate), keyfile=str(private_key))
        client = httpx.AsyncClient(
            verify=tls_context,
            timeout=settings.dependency_timeout_seconds,
            trust_env=False,
        )
        return cls(client, token.get_secret_value(), settings.vpn_node_agent_port)

    async def get_health(self, node: VpnNode) -> NodeAgentHealth:
        try:
            response = await self._client.get(
                f"https://{node.public_ipv4}:{self._agent_port}/v1/health",
                headers={"Authorization": f"Bearer {self._auth_token}"},
            )
            response.raise_for_status()
            health = _AgentHealthResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise NodeAgentUnavailableError("node agent health request failed") from error
        return NodeAgentHealth(
            healthy=health.status == "HEALTHY",
            interface_up=health.interface_up,
            listen_port=health.listen_port,
        )

    async def add_peer(self, node: VpnNode, public_key: str, vpn_ip: IPv4Address) -> None:
        try:
            response = await self._client.put(
                self._url(node, "/v1/peers"),
                headers=self._headers(),
                json={"public_key": public_key, "vpn_ip": str(vpn_ip)},
            )
            response.raise_for_status()
            peer = _AgentPeerResponse.model_validate(response.json())
            if peer.public_key != public_key or peer.vpn_ip != vpn_ip:
                raise ValueError("node agent returned a mismatched peer")
        except (httpx.HTTPError, ValueError) as error:
            raise NodeAgentUnavailableError("node agent peer creation failed") from error

    async def remove_peer(self, node: VpnNode, public_key: str) -> None:
        try:
            response = await self._client.request(
                "DELETE",
                self._url(node, "/v1/peers"),
                headers=self._headers(),
                json={"public_key": public_key},
            )
            response.raise_for_status()
            _AgentRemovalResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as error:
            raise NodeAgentUnavailableError("node agent peer removal failed") from error

    async def peer_exists(self, node: VpnNode, public_key: str) -> bool:
        try:
            response = await self._client.get(
                self._url(node, "/v1/peers"),
                headers=self._headers(),
                params={"public_key": public_key},
            )
            if response.status_code == 404:
                return False
            response.raise_for_status()
            peer = _AgentPeerResponse.model_validate(response.json())
            if peer.public_key != public_key:
                raise ValueError("node agent returned a mismatched peer")
            return True
        except (httpx.HTTPError, ValueError) as error:
            raise NodeAgentUnavailableError("node agent peer query failed") from error

    def _url(self, node: VpnNode, path: str) -> str:
        return f"https://{node.public_ipv4}:{self._agent_port}{path}"

    async def issue_managed(
        self, node: VpnNode, session_id: UUID, secret: str, expires: datetime
    ) -> ManagedNodeProfile:
        try:
            response = await self._client.put(
                self._url(node, f"/v1/managed/{session_id}"),
                headers=self._headers(),
                json={"secret": secret, "expires": int(expires.timestamp())},
                timeout=12,
            )
            response.raise_for_status()
            return ManagedNodeProfile.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise NodeAgentUnavailableError("managed authorization unavailable") from None

    async def remove_managed(self, node: VpnNode, session_id: UUID) -> None:
        try:
            response = await self._client.delete(
                self._url(node, f"/v1/managed/{session_id}"), headers=self._headers(), timeout=12
            )
            response.raise_for_status()
            if response.json() != {"removed": True}:
                raise ValueError("unconfirmed managed cleanup")
        except (httpx.HTTPError, ValueError):
            raise NodeAgentUnavailableError("managed cleanup unavailable") from None

    async def issue_managed_plan(
        self, node: VpnNode, session_id: UUID, secret: str, expires: datetime
    ) -> ManagedNodePlan:
        try:
            response = await self._client.put(
                self._url(node, f"/v1/managed/{session_id}/plan"),
                headers=self._headers(),
                json={"secret": secret, "expires": int(expires.timestamp())},
                timeout=12,
            )
            response.raise_for_status()
            return ManagedNodePlan.model_validate(response.json())
        except (httpx.HTTPError, ValueError):
            raise NodeAgentUnavailableError("managed plan unavailable") from None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._auth_token}"}

    async def close(self) -> None:
        await self._client.aclose()
