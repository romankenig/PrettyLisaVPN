"""Authenticated HTTP transport for product-level VPN country availability."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
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
