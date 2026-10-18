"""Private read-only HTTP billing contract; no payment operations are registered."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
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
from prettylisavpn.billing.domain import Overview
from prettylisavpn.billing.service import BillingOverviewPort, BillingUnavailableError
from prettylisavpn.main_errors import error_response


class BillingRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
            except (InvalidAccessTokenError, InvalidSessionError):
                response = error_response("AUTH_INVALID", 401)
            except (BlockedUserError, RevokedDeviceError):
                response = error_response("AUTH_INVALID", 403)
            except (AuthServiceUnavailableError, BillingUnavailableError):
                response = error_response("BILLING_UNAVAILABLE", 503)
            except Exception:
                response = error_response("BILLING_UNAVAILABLE", 503)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization"
            return response

        return private


router = APIRouter(prefix="/billing", tags=["billing"], route_class=BillingRoute)


@router.get("/overview", response_model=Overview)
async def overview(
    request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> Overview | Response:
    if token is None:
        return error_response("AUTH_INVALID", 401)
    return await cast(BillingOverviewPort, request.app.state.billing).overview(token)
