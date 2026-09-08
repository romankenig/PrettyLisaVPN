"""Thin HTTP transport for passwordless authentication requests."""

from typing import Literal, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr
from starlette.responses import JSONResponse

from prettylisavpn.auth.service import (
    OtpDeliveryUnavailableError,
    OtpIssuer,
    OtpRateLimitedError,
    OtpStorageUnavailableError,
    ProductEventSink,
    RequestOtpService,
)
from prettylisavpn.emailing.domain import EmailProvider
from prettylisavpn.main_errors import error_response

router = APIRouter(prefix="/auth", tags=["auth"])


class RequestOtpBody(BaseModel):
    email: EmailStr


class RequestOtpResponse(BaseModel):
    status: Literal["accepted"] = "accepted"


@router.post(
    "/request-otp",
    response_model=RequestOtpResponse,
    status_code=202,
    responses={
        429: {"description": "OTP request rate limited"},
        503: {"description": "OTP service unavailable"},
    },
)
async def request_otp(body: RequestOtpBody, request: Request) -> RequestOtpResponse | JSONResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    service = RequestOtpService(
        cast(OtpIssuer, request.app.state.otp_service),
        cast(EmailProvider | None, request.app.state.email_provider),
        cast(ProductEventSink, request.app.state.product_events),
    )
    try:
        await service.request(str(body.email), client_ip)
    except OtpRateLimitedError:
        return error_response("otp_rate_limited", 429)
    except OtpStorageUnavailableError:
        return error_response("otp_service_unavailable", 503)
    except OtpDeliveryUnavailableError:
        return error_response("email_service_unavailable", 503)
    return RequestOtpResponse()
