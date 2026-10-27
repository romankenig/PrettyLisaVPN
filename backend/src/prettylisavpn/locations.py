"""Country metadata retained while real VPN connectivity is being rebuilt."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthenticatedSessionHandler,
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.config import Settings
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.main_errors import error_response
from prettylisavpn.subscriptions.entitlements import entitlements_for_plan

router = APIRouter(prefix="/vpn", tags=["locations"])


class Availability(BaseModel):
    quality: int = 0
    available: bool = False


class Country(Availability):
    country_code: str


class Countries(BaseModel):
    autopilot: Availability
    countries: list[Country]


@router.get("/countries", response_model=Countries)
async def countries(
    request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> Countries | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    auth = cast(AuthenticatedSessionHandler, request.app.state.authenticated_sessions)
    try:
        if cast(Settings, request.app.state.fleet_settings).fleet_enabled:
            account = await auth.me(token)
            snapshot = await cast(FleetService, request.app.state.fleet).countries(
                free_only=entitlements_for_plan(account.plan).free_nodes_only
            )
            return Countries.model_validate(snapshot)
        await auth.authenticate(token)
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
    # No health claims or node calls: all real listeners are retired.
    return Countries(
        autopilot=Availability(), countries=[Country(country_code="DE"), Country(country_code="US")]
    )
