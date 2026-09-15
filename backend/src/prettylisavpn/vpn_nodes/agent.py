"""Authenticated mTLS adapter for the VPN Node Control Agent."""

import ssl
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

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


class NodeAgentPort(NodeAgentHealthPort, NodeAgentPeerPort, Protocol):
    pass


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

    def _url(self, node: VpnNode, path: str) -> str:
        return f"https://{node.public_ipv4}:{self._agent_port}{path}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._auth_token}"}

    async def close(self) -> None:
        await self._client.aclose()
