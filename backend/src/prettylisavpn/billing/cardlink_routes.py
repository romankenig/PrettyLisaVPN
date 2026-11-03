"""Public Cardlink Result URL: fail closed; successful delivery means durable inbox only."""

import asyncio
from typing import cast

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response

from prettylisavpn.billing.cardlink import MAX_CALLBACK_BYTES, CallbackHandler, CardlinkError
from prettylisavpn.main_errors import error_response

router = APIRouter(prefix="/api/payments/cardlink", tags=["cardlink-notifications"])


@router.api_route("/callback", methods=["GET", "HEAD"], include_in_schema=False)
async def callback_info() -> JSONResponse:
    return JSONResponse(
        {"provider": "cardlink", "notification_method": "POST"},
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


@router.post("/callback")
async def receive_callback(request: Request) -> Response:
    try:
        handler = cast(CallbackHandler | None, request.app.state.cardlink_callbacks)
        if handler is None:
            raise CardlinkError("CARDLINK_NOT_CONFIGURED", 503)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/x-www-form-urlencoded":
            raise CardlinkError("CARDLINK_CONTENT_TYPE_UNSUPPORTED", 415)
        body = bytearray()
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_CALLBACK_BYTES:
                    raise CardlinkError("CARDLINK_BODY_TOO_LARGE", 413)
            await handler.receive(bytes(body))
        response: Response = JSONResponse({"status": "received"})
    except CardlinkError as error:
        response = error_response(error.code, error.status)
    except Exception:
        # Never log request data, API tokens, signatures or SQL/provider exceptions.
        response = error_response("CARDLINK_UNAVAILABLE", 503)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    if response.status_code == 503:
        response.headers["Retry-After"] = "10"
    return response
