"""Private customer API; credentials and public peer configuration are never cached."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import Response

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.client_vpn.service import ClientVpnService
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.main_errors import error_response


class PrivateRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError:
                response = error_response("INVALID_REQUEST", 422)
            except (InvalidAccessTokenError, InvalidSessionError):
                response = error_response("invalid_session", 401)
            except (BlockedUserError, RevokedDeviceError):
                response = error_response("account_unavailable", 403)
            except AuthServiceUnavailableError:
                response = error_response("VPN_UNAVAILABLE", 503)
            except FleetError as error:
                response = error_response(error.code, error.status)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization"
            return response

        return private


router = APIRouter(prefix="/vpn/wireguard/sessions", tags=["client-vpn"], route_class=PrivateRoute)


def service(request: Request) -> ClientVpnService:
    return cast(ClientVpnService, request.app.state.client_vpn)


def token(value: Annotated[str | None, Depends(bearer_token)]) -> str:
    if not value:
        raise InvalidAccessTokenError
    return value


Service = Annotated[ClientVpnService, Depends(service)]
Token = Annotated[str, Depends(token)]


@router.post("", status_code=202)
async def connect(
    data: ConnectRequest,
    backend: Service,
    credential: Token,
    idempotency_key: Annotated[UUID, Header()],
) -> dict[str, Any]:
    return await backend.connect(credential, data, idempotency_key)


@router.get("/current")
async def current(backend: Service, credential: Token) -> dict[str, Any] | None:
    return await backend.get(credential)


@router.get("/{identifier}")
async def get(identifier: UUID, backend: Service, credential: Token) -> dict[str, Any] | None:
    return await backend.get(credential, identifier)


@router.post("/{identifier}/heartbeat")
async def heartbeat(identifier: UUID, backend: Service, credential: Token) -> dict[str, Any] | None:
    return await backend.get(credential, identifier, "heartbeat")


@router.delete("/{identifier}", status_code=202)
async def revoke(identifier: UUID, backend: Service, credential: Token) -> dict[str, Any] | None:
    return await backend.get(credential, identifier, "revoke")


@router.get("/{identifier}/probe")
async def probe(
    identifier: UUID, request: Request, backend: Service, credential: Token
) -> dict[str, Any] | None:
    return await backend.get(
        credential, identifier, "probe", request.client.host if request.client else None
    )
