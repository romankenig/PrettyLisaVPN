"""Thin HTTP transport for passwordless authentication requests."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.responses import JSONResponse

from prettylisavpn.auth.service import (
    BlockedUserError,
    InvalidOtpError,
    LoginHandler,
    LoginPersistenceError,
    OtpDeliveryUnavailableError,
    OtpIssuer,
    OtpRateLimitedError,
    OtpStorageUnavailableError,
    ProductEventSink,
    RequestOtpService,
)
from prettylisavpn.devices.domain import DeviceLimitReachedError, DevicePlatform, DeviceStatus
from prettylisavpn.emailing.domain import EmailProvider
from prettylisavpn.main_errors import error_response
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus

router = APIRouter(prefix="/auth", tags=["auth"])


class RequestOtpBody(BaseModel):
    email: EmailStr


class RequestOtpResponse(BaseModel):
    status: Literal["accepted"] = "accepted"


class ErrorDetail(BaseModel):
    code: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class VerifyOtpBody(BaseModel):
    email: EmailStr
    code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]
    installation_id: UUID
    platform: DevicePlatform
    device_name: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("device_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("device_name must not be empty")
        return normalized


class LoginUserResponse(BaseModel):
    id: UUID


class LoginDeviceResponse(BaseModel):
    id: UUID
    installation_id: UUID
    status: DeviceStatus


class LoginSubscriptionResponse(BaseModel):
    plan: SubscriptionPlan
    status: SubscriptionStatus


class VerifyOtpResponse(BaseModel):
    token_type: Literal["bearer"] = "bearer"
    access_token: str
    access_token_expires_in: int
    refresh_token: str
    refresh_token_expires_at: datetime
    session_id: UUID
    user: LoginUserResponse
    device: LoginDeviceResponse
    subscription: LoginSubscriptionResponse


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


@router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    responses={
        401: {"model": ErrorResponse, "description": "OTP invalid, expired, or consumed"},
        403: {"model": ErrorResponse, "description": "User is blocked"},
        409: {"model": ErrorResponse, "description": "Active device limit reached"},
        503: {"model": ErrorResponse, "description": "Authentication service unavailable"},
    },
)
async def verify_otp(body: VerifyOtpBody, request: Request) -> VerifyOtpResponse | JSONResponse:
    service = cast(LoginHandler, request.app.state.login_service)
    try:
        result = await service.verify_otp(
            str(body.email),
            body.code,
            body.installation_id,
            body.platform,
            body.device_name,
        )
    except InvalidOtpError:
        return error_response("otp_invalid_or_expired", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except DeviceLimitReachedError:
        return error_response("device_limit_reached", 409)
    except OtpStorageUnavailableError:
        return error_response("otp_service_unavailable", 503)
    except LoginPersistenceError:
        return error_response("login_service_unavailable", 503)

    return VerifyOtpResponse(
        access_token=result.access_token.token,
        access_token_expires_in=result.access_token.expires_in_seconds,
        refresh_token=result.auth_session.refresh_token,
        refresh_token_expires_at=result.auth_session.session.expires_at,
        session_id=result.auth_session.session.id,
        user=LoginUserResponse(id=result.user.id),
        device=LoginDeviceResponse(
            id=result.device.id,
            installation_id=result.device.installation_id,
            status=result.device.status,
        ),
        subscription=LoginSubscriptionResponse(
            plan=result.subscription.plan,
            status=result.subscription.status,
        ),
    )
