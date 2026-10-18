"""Authenticated HTTP transport for VPN targeting and country availability."""

from dataclasses import asdict
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.responses import JSONResponse

from prettylisavpn.auth.router import ErrorResponse, bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.main_errors import error_response
from prettylisavpn.vpn_nodes.countries import (
    VpnCountryAvailability,
    VpnCountryAvailabilityHandler,
    VpnCountryAvailabilityUnavailableError,
)
from prettylisavpn.vpn_nodes.selection import NodeSelectionMode, NodeSelectionRequest
from prettylisavpn.vpn_sessions.address_allocation import AddressPoolExhaustedError
from prettylisavpn.vpn_sessions.connection import (
    ActiveVpnTransport,
    CountryUnavailableError,
    FreeDailyLimitReachedError,
    VpnConnectionHandler,
    VpnSessionPersistenceUnavailableError,
    VpnSetupFailedError,
    VpnUnavailableError,
)
from prettylisavpn.vpn_sessions.service import DeviceAlreadyHasLiveVpnSessionError
from prettylisavpn.vpn_sessions.status import (
    VpnSessionStatusHandler,
    VpnSessionStatusUnavailableError,
)
from prettylisavpn.vpn_sessions.termination import (
    OwnedVpnSessionNotFoundError,
    VpnTerminationHandler,
    VpnTerminationUnavailableError,
)

router = APIRouter(prefix="/vpn", tags=["vpn"])


class AutopilotAvailabilityResponse(BaseModel):
    quality: int = Field(ge=0, le=100)
    available: bool


class CountryAvailabilityResponse(BaseModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    quality: int = Field(ge=0, le=100)
    available: bool


class VpnCountriesResponse(BaseModel):
    autopilot: AutopilotAvailabilityResponse
    countries: list[CountryAvailabilityResponse]


class CreateVpnSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: NodeSelectionMode
    country_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    public_key: str = Field(pattern=r"^[A-Za-z0-9+/]{43}=$")

    @model_validator(mode="after")
    def validate_target(self) -> "CreateVpnSessionBody":
        if self.mode is NodeSelectionMode.AUTO and self.country_code is not None:
            raise ValueError("AUTO must not include country_code")
        if self.mode is NodeSelectionMode.COUNTRY and self.country_code is None:
            raise ValueError("COUNTRY requires country_code")
        return self


class VpnEndpointResponse(BaseModel):
    ipv4: IPv4Address
    port: int = Field(ge=1, le=65535)


class WireGuardTransportResponse(BaseModel):
    endpoint: VpnEndpointResponse
    server_public_key: str
    client_address: IPv4Interface
    dns: list[IPv4Address]
    allowed_ips: list[IPv4Network]


class ConnectionConfigResponse(BaseModel):
    country: str
    protocol: str
    transport: str
    port: int
    encryption_mode: str
    obfuscation_mode: str
    mtu: int
    dns_mode: str
    routing_mode: str
    obfuscation_version: int | None = None
    transport_parameters: dict[str, int] | None = None


class ActiveVpnSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["ACTIVE"] = "ACTIVE"
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    expires_at: datetime | None
    server_time: datetime
    transport: WireGuardTransportResponse
    candidates: list[ConnectionConfigResponse] = Field(default_factory=list)


class TerminatedVpnSessionResponse(BaseModel):
    session_id: UUID
    status: Literal["EXPIRED", "DISCONNECTED", "FAILED"]


class CurrentVpnSessionResponse(BaseModel):
    session: ActiveVpnSessionResponse | None


def _active_response(
    transport: ActiveVpnTransport, *, include_candidates: bool = False
) -> ActiveVpnSessionResponse:
    response = ActiveVpnSessionResponse(
        status="ACTIVE",
        session_id=transport.session_id,
        country_code=transport.country_code,
        expires_at=transport.expires_at,
        server_time=datetime.now(UTC),
        transport=WireGuardTransportResponse(
            endpoint=VpnEndpointResponse(
                ipv4=transport.endpoint_ipv4, port=transport.endpoint_port
            ),
            server_public_key=transport.server_public_key,
            client_address=IPv4Interface(f"{transport.client_ipv4}/32"),
            dns=list(transport.dns),
            allowed_ips=list(transport.allowed_ips),
        ),
    )

    if include_candidates:
        response.candidates = [
            ConnectionConfigResponse.model_validate(
                {
                    key: value
                    for key, value in asdict(candidate).items()
                    if key != "node_id" and value is not None
                }
            )
            for candidate in transport.candidates
        ]
    return response


@router.get(
    "/sessions/current",
    response_model=CurrentVpnSessionResponse,
    response_model_exclude_unset=True,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        503: {"model": ErrorResponse, "description": "VPN session state unavailable"},
    },
)
async def current_vpn_session(
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> CurrentVpnSessionResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(VpnSessionStatusHandler, request.app.state.vpn_session_status)
    try:
        result = await service.current(token)
    except InvalidAccessTokenError:
        return error_response("invalid_access_token", 401)
    except InvalidSessionError:
        return error_response("invalid_session", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except RevokedDeviceError:
        return error_response("device_revoked", 403)
    except AuthServiceUnavailableError:
        return error_response("auth_service_unavailable", 503)
    except VpnSessionStatusUnavailableError:
        return error_response("VPN_SESSION_STATUS_UNAVAILABLE", 503)
    return CurrentVpnSessionResponse(
        session=None
        if result is None
        else _active_response(
            result, include_candidates=request.headers.get("X-VPN-Candidates") == "1"
        )
    )


def _response(result: VpnCountryAvailability) -> VpnCountriesResponse:
    return VpnCountriesResponse(
        autopilot=AutopilotAvailabilityResponse(
            quality=result.autopilot.quality,
            available=result.autopilot.available,
        ),
        countries=[
            CountryAvailabilityResponse(
                country_code=country.country_code,
                quality=country.quality,
                available=country.available,
            )
            for country in result.countries
        ],
    )


@router.get(
    "/countries",
    response_model=VpnCountriesResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        503: {"model": ErrorResponse, "description": "Country availability unavailable"},
    },
)
async def list_vpn_countries(
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> VpnCountriesResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(VpnCountryAvailabilityHandler, request.app.state.vpn_country_availability)
    try:
        return _response(await service.list_countries(token))
    except InvalidAccessTokenError:
        return error_response("invalid_access_token", 401)
    except InvalidSessionError:
        return error_response("invalid_session", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except RevokedDeviceError:
        return error_response("device_revoked", 403)
    except AuthServiceUnavailableError:
        return error_response("auth_service_unavailable", 503)
    except VpnCountryAvailabilityUnavailableError:
        return error_response("vpn_country_service_unavailable", 503)


@router.post(
    "/sessions",
    response_model=ActiveVpnSessionResponse,
    response_model_exclude_unset=True,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        409: {"model": ErrorResponse, "description": "VPN target or session unavailable"},
        503: {"model": ErrorResponse, "description": "VPN setup service unavailable"},
    },
)
async def create_vpn_session(
    body: CreateVpnSessionBody,
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> ActiveVpnSessionResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    selection = (
        NodeSelectionRequest.auto()
        if body.mode is NodeSelectionMode.AUTO
        else NodeSelectionRequest.country(cast(str, body.country_code))
    )
    service = cast(VpnConnectionHandler, request.app.state.vpn_connection)
    try:
        result = await service.connect(token, selection, body.public_key)
    except InvalidAccessTokenError:
        return error_response("invalid_access_token", 401)
    except InvalidSessionError:
        return error_response("invalid_session", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except RevokedDeviceError:
        return error_response("device_revoked", 403)
    except AuthServiceUnavailableError:
        return error_response("auth_service_unavailable", 503)
    except CountryUnavailableError:
        return error_response("COUNTRY_UNAVAILABLE", 409)
    except VpnUnavailableError:
        return error_response("VPN_UNAVAILABLE", 409)
    except FreeDailyLimitReachedError:
        return error_response("FREE_DAILY_LIMIT_REACHED", 403)
    except DeviceAlreadyHasLiveVpnSessionError:
        return error_response("VPN_SESSION_ALREADY_ACTIVE", 409)
    except AddressPoolExhaustedError:
        return error_response("VPN_ADDRESS_POOL_EXHAUSTED", 503)
    except (VpnSetupFailedError, VpnSessionPersistenceUnavailableError):
        return error_response("VPN_SETUP_FAILED", 503)
    return _active_response(
        result, include_candidates=request.headers.get("X-VPN-Candidates") == "1"
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=TerminatedVpnSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        404: {"model": ErrorResponse, "description": "Owned VPN session not found"},
        503: {"model": ErrorResponse, "description": "VPN termination unavailable"},
    },
)
async def disconnect_vpn_session(
    session_id: UUID,
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> TerminatedVpnSessionResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(VpnTerminationHandler, request.app.state.vpn_termination)
    try:
        result = await service.disconnect(token, session_id)
    except InvalidAccessTokenError:
        return error_response("invalid_access_token", 401)
    except InvalidSessionError:
        return error_response("invalid_session", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except RevokedDeviceError:
        return error_response("device_revoked", 403)
    except AuthServiceUnavailableError:
        return error_response("auth_service_unavailable", 503)
    except OwnedVpnSessionNotFoundError:
        return error_response("VPN_SESSION_NOT_FOUND", 404)
    except VpnTerminationUnavailableError:
        return error_response("VPN_TERMINATION_UNAVAILABLE", 503)
    return TerminatedVpnSessionResponse(session_id=result.session_id, status=result.status)

