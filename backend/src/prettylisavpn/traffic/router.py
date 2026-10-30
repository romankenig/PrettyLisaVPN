"""Catalog transport; user selections are deliberately not uploaded."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.main_errors import error_response
from prettylisavpn.traffic.service import TrafficCatalog, TrafficCatalogService

router = APIRouter(prefix="/vpn/traffic", tags=["traffic"])


@router.get("/services", response_model=TrafficCatalog)
async def services(
    request: Request, response: Response, token: Annotated[str | None, Depends(bearer_token)]
) -> TrafficCatalog | JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    if token is None:
        return error_response("authentication_required", 401)
    try:
        return await cast(TrafficCatalogService, request.app.state.traffic_catalog).catalog(token)
    except (InvalidAccessTokenError, InvalidSessionError):
        return error_response("invalid_session", 401)
    except (BlockedUserError, RevokedDeviceError):
        return error_response("access_denied", 403)
    except (AuthServiceUnavailableError, SQLAlchemyError, ValidationError):
        return error_response("traffic_catalog_unavailable", 503)
