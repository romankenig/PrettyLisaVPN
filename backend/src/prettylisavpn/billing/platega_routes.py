"""Public callback transport with no request-body logging or business settlement."""

from typing import cast

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from prettylisavpn.billing.platega_callbacks import InvalidPlategaCallback, PlategaCallbacks
from prettylisavpn.main_errors import error_response

router = APIRouter(tags=["billing"])


@router.post("/api/payments/platega/callback")
async def callback(request: Request) -> Response:
    handler = cast(PlategaCallbacks | None, getattr(request.app.state, "platega_callbacks", None))
    if handler is None:
        return error_response("PAYMENT_PROVIDER_DISABLED", 503)
    if not handler.authenticated(
        request.headers.get("X-MerchantId", ""), request.headers.get("X-Secret", "")
    ):
        return error_response("PAYMENT_CALLBACK_UNAUTHORIZED", 401)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        return error_response("PAYMENT_CALLBACK_INVALID", 415)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 16_384:
            return error_response("PAYMENT_CALLBACK_INVALID", 413)
    try:
        await handler.accept(bytes(content))
    except InvalidPlategaCallback:
        return error_response("PAYMENT_CALLBACK_INVALID", 400)
    except SQLAlchemyError:
        return error_response("PAYMENT_CALLBACK_UNAVAILABLE", 503)
    return Response(status_code=200, headers={"Cache-Control": "no-store"})
