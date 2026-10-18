"""Authenticated JSON v1 transport; private responses are never cacheable."""

from collections.abc import Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response

from prettylisavpn.account_messages.domain import (
    Acknowledgement,
    MessageContext,
    MessagesResponse,
    Receipt,
)
from prettylisavpn.account_messages.service import (
    AccountMessagesService,
    MessageNotFoundError,
    MessagesUnavailableError,
)
from prettylisavpn.auth.router import bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.main_errors import error_response


class PrivateRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError:
                response = error_response("validation_error", 422)
            except (InvalidAccessTokenError, InvalidSessionError):
                response = error_response("invalid_session", 401)
            except (BlockedUserError, RevokedDeviceError):
                response = error_response("account_unavailable", 403)
            except (AuthServiceUnavailableError, MessagesUnavailableError):
                response = error_response("MESSAGES_UNAVAILABLE", 503)
            except MessageNotFoundError:
                response = error_response("MESSAGE_NOT_FOUND", 404)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization"
            return response

        return private


router = APIRouter(prefix="/messages", tags=["messages"], route_class=PrivateRoute)


@router.get("", response_model=MessagesResponse)
async def messages(
    request: Request,
    context: Annotated[MessageContext, Query()],
    token: Annotated[str | None, Depends(bearer_token)],
) -> Response:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(AccountMessagesService, request.app.state.account_messages)
    result = await service.list_messages(token, context)
    return JSONResponse(result.model_dump(mode="json"))


@router.post("/{message_id}/acknowledgements", response_model=Receipt)
async def acknowledge(
    message_id: UUID,
    body: Acknowledgement,
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> Response:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(AccountMessagesService, request.app.state.account_messages)
    result = await service.acknowledge(token, message_id, body.revision)
    return JSONResponse(result.model_dump(mode="json"))
