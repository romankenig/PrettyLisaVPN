"""Authenticated HTTP API for node-local WireGuard control."""

from datetime import UTC, datetime
from hmac import compare_digest
from ipaddress import IPv4Address
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from starlette.requests import Request
from starlette.responses import JSONResponse

from prettylisavpn_node_agent.config import AgentSettings
from prettylisavpn_node_agent.managed import ManagedController, ManagedLease
from prettylisavpn_node_agent.wireguard import (
    PeerConflictError,
    PeerState,
    WireGuardController,
    WireGuardError,
    validate_public_key,
)


class PeerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str
    vpn_ip: IPv4Address

    @field_validator("public_key")
    @classmethod
    def public_key_is_wireguard_key(cls, value: str) -> str:
        return validate_public_key(value)


class PeerKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str

    @field_validator("public_key")
    @classmethod
    def public_key_is_wireguard_key(cls, value: str) -> str:
        return validate_public_key(value)


class PeerResponse(BaseModel):
    public_key: str
    vpn_ip: IPv4Address
    latest_handshake_at: datetime | None
    created: bool | None = None


class RemovalResponse(BaseModel):
    removed: bool


class HealthResponse(BaseModel):
    status: Literal["HEALTHY", "UNHEALTHY"]
    interface: str
    interface_up: bool
    listen_port: int | None


class MetricsResponse(BaseModel):
    uptime_seconds: int
    peers_total: int
    peers_with_recent_handshake: int
    interface_up: bool


class ManagedLeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    secret: SecretStr
    expires: int


def _peer_response(peer: PeerState, created: bool | None = None) -> PeerResponse:
    return PeerResponse(
        public_key=peer.public_key,
        vpn_ip=peer.vpn_ip,
        latest_handshake_at=peer.latest_handshake_at,
        created=created,
    )


def create_app(
    settings: AgentSettings,
    controller: WireGuardController,
    managed: ManagedController | None = None,
) -> FastAPI:
    application_started = monotonic()

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        scheme, separator, credential = (authorization or "").partition(" ")
        if (
            separator != " "
            or scheme.lower() != "bearer"
            or not compare_digest(credential, settings.auth_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "NODE_AGENT_UNAUTHORIZED"},
                headers={"WWW-Authenticate": "Bearer"},
            )

    router = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])

    @router.put("/managed/{lease_id}/plan")
    def issue_plan(lease_id: UUID, body: ManagedLeaseRequest) -> dict[str, object]:
        if managed is None:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"})
        try:
            return managed.issue_plan(
                ManagedLease(lease_id, body.secret.get_secret_value(), body.expires)
            )
        except Exception:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"}) from None

    @router.put("/managed/{lease_id}")
    def issue_managed(lease_id: UUID, body: ManagedLeaseRequest) -> dict[str, object]:
        if managed is None:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"})
        try:
            return managed.issue(
                ManagedLease(lease_id, body.secret.get_secret_value(), body.expires)
            )
        except Exception:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"}) from None

    @router.delete("/managed/{lease_id}")
    def remove_managed(lease_id: UUID) -> dict[str, bool]:
        if managed is None:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"})
        try:
            managed.remove(lease_id)
        except Exception:
            raise HTTPException(503, detail={"code": "NODE_AGENT_MANAGED_UNAVAILABLE"}) from None
        return {"removed": True}

    @router.put("/peers", response_model=PeerResponse)
    def add_peer(request: PeerRequest) -> PeerResponse:
        try:
            peer, created = controller.add_peer(request.public_key, request.vpn_ip)
        except PeerConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "NODE_AGENT_PEER_CONFLICT"},
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "NODE_AGENT_INVALID_PEER"},
            ) from error
        except WireGuardError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "NODE_AGENT_WIREGUARD_UNAVAILABLE"},
            ) from error
        return _peer_response(peer, created)

    @router.delete("/peers", response_model=RemovalResponse)
    def remove_peer(request: PeerKeyRequest) -> RemovalResponse:
        try:
            return RemovalResponse(removed=controller.remove_peer(request.public_key))
        except WireGuardError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "NODE_AGENT_WIREGUARD_UNAVAILABLE"},
            ) from error

    @router.get("/peers", response_model=PeerResponse)
    def get_peer(public_key: Annotated[str, Query()]) -> PeerResponse:
        try:
            peer = controller.get_peer(validate_public_key(public_key))
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "NODE_AGENT_INVALID_PUBLIC_KEY"},
            ) from error
        except WireGuardError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "NODE_AGENT_WIREGUARD_UNAVAILABLE"},
            ) from error
        if peer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NODE_AGENT_PEER_NOT_FOUND"},
            )
        return _peer_response(peer)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            interface = controller.interface_state()
        except WireGuardError:
            return HealthResponse(
                status="UNHEALTHY",
                interface=settings.interface,
                interface_up=False,
                listen_port=None,
            )
        return HealthResponse(
            status="HEALTHY" if interface.is_up and interface.public_key_available else "UNHEALTHY",
            interface=settings.interface,
            interface_up=interface.is_up,
            listen_port=interface.listen_port,
        )

    @router.get("/metrics", response_model=MetricsResponse)
    def metrics() -> MetricsResponse:
        try:
            peers = controller.list_peers().values()
            interface_up = controller.interface_state().is_up
        except WireGuardError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "NODE_AGENT_WIREGUARD_UNAVAILABLE"},
            ) from error
        now = datetime.now(UTC)
        recent = sum(
            1
            for peer in peers
            if peer.latest_handshake_at is not None
            and (now - peer.latest_handshake_at).total_seconds()
            <= settings.recent_handshake_seconds
        )
        return MetricsResponse(
            uptime_seconds=int(monotonic() - application_started),
            peers_total=len(peers),
            peers_with_recent_handshake=recent,
            interface_up=interface_up,
        )

    app = FastAPI(
        title="PrettyLisaVPN Node Agent",
        version="0.3.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI's default validation response can echo private profile values.
        return JSONResponse({"detail": {"code": "NODE_AGENT_INVALID_REQUEST"}}, status_code=422)

    return app
