"""Private billing overview, durable command admission and operation recovery."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
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
from prettylisavpn.billing.domain import Overview
from prettylisavpn.billing.operations import (
    BillingConflictError,
    BillingDisabledError,
    BillingOperationNotFoundError,
    BillingOperationsPort,
)
from prettylisavpn.billing.operations_domain import BillingCommand, BillingOperation
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
            except BillingConflictError as error:
                response = error_response(error.code, 409)
            except BillingDisabledError:
                response = error_response("BILLING_DISABLED", 503)
            except BillingOperationNotFoundError:
                response = error_response("BILLING_OPERATION_NOT_FOUND", 404)
            except RequestValidationError:
                response = error_response("validation_error", 422)
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


@router.post("/operations", response_model=BillingOperation)
async def start_operation(
    request: Request, command: BillingCommand, token: Annotated[str | None, Depends(bearer_token)]
) -> BillingOperation | Response:
    if token is None:
        return error_response("AUTH_INVALID", 401)
    return await cast(BillingOperationsPort, request.app.state.billing_operations).start(
        token, command
    )


@router.get("/operations/{operation_id}", response_model=BillingOperation)
async def operation(
    request: Request, operation_id: UUID, token: Annotated[str | None, Depends(bearer_token)]
) -> BillingOperation | Response:
    if token is None:
        return error_response("AUTH_INVALID", 401)
    return await cast(BillingOperationsPort, request.app.state.billing_operations).get(
        token, operation_id
    )
