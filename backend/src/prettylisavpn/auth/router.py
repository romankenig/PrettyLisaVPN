"""Thin HTTP transport for passwordless authentication requests."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
from prettylisavpn.auth.session_service import (
    AuthenticatedSessionHandler,
    AuthServiceUnavailableError,
    InvalidRefreshTokenError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.devices.domain import DeviceLimitReachedError, DevicePlatform, DeviceStatus
from prettylisavpn.emailing.domain import EmailProvider
from prettylisavpn.main_errors import error_response
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.entitlements import entitlements_for_plan

router = APIRouter(prefix="/auth", tags=["auth"])
account_router = APIRouter(tags=["account"])
bearer_scheme = HTTPBearer(auto_error=False)


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
    last_login_at: datetime | None


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


class RefreshBody(BaseModel):
    session_id: UUID
    refresh_token: Annotated[str, Field(min_length=1, max_length=512)]


class RefreshResponse(BaseModel):
    token_type: Literal["bearer"] = "bearer"
    access_token: str
    access_token_expires_in: int
    refresh_token: str
    refresh_token_expires_at: datetime
    session_id: UUID


class SubscriptionAccessResponse(BaseModel):
    plan: SubscriptionPlan
    status: str
    auto_renew: bool
    paid_until: datetime | None


class EntitlementsResponse(BaseModel):
    vpn_session_limit_seconds: int | None
    rewarded_ad_required: bool
    country_selection_allowed: bool
    free_nodes_only: bool
    active_device_limit: int
    daily_vpn_limit_seconds: int | None
    free_seconds_remaining: int | None
    free_quota_resets_at: datetime | None
    free_seconds_usable: int | None = None
    free_running_sessions: int | None = None
    quota_observed_at: datetime | None = None


class MeResponse(BaseModel):
    id: UUID
    email: EmailStr
    plan: SubscriptionPlan
    active_device_count: int
    subscription: SubscriptionAccessResponse | None = None
    entitlements: EntitlementsResponse | None = None


class LogoutResponse(BaseModel):
    status: Literal["logged_out"] = "logged_out"


def bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str | None:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        return None
    return credentials.credentials


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
            last_login_at=result.device.last_login_at,
        ),
        subscription=LoginSubscriptionResponse(
            plan=result.subscription.plan,
            status=result.subscription.status,
        ),
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Refresh credentials are unusable"},
        403: {"model": ErrorResponse, "description": "User or device is blocked"},
        503: {"model": ErrorResponse, "description": "Authentication service unavailable"},
    },
)
async def refresh(body: RefreshBody, request: Request) -> RefreshResponse | JSONResponse:
    service = cast(AuthenticatedSessionHandler, request.app.state.authenticated_sessions)
    try:
        result = await service.refresh(body.session_id, body.refresh_token)
    except InvalidRefreshTokenError:
        return error_response("invalid_refresh_token", 401)
    except BlockedUserError:
        return error_response("user_blocked", 403)
    except RevokedDeviceError:
        return error_response("device_revoked", 403)
    except AuthServiceUnavailableError:
        return error_response("auth_service_unavailable", 503)
    return RefreshResponse(
        access_token=result.access_token.token,
        access_token_expires_in=result.access_token.expires_in_seconds,
        refresh_token=result.auth_session.refresh_token,
        refresh_token_expires_at=result.auth_session.session.expires_at,
        session_id=result.auth_session.session.id,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or device is blocked"},
        503: {"model": ErrorResponse, "description": "Authentication service unavailable"},
    },
)
async def logout(
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> LogoutResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(AuthenticatedSessionHandler, request.app.state.authenticated_sessions)
    try:
        await service.logout(token)
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
    return LogoutResponse()


@account_router.get(
    "/me",
    response_model=MeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or device is blocked"},
        503: {"model": ErrorResponse, "description": "Authentication service unavailable"},
    },
)
async def me(
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> MeResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(AuthenticatedSessionHandler, request.app.state.authenticated_sessions)
    try:
        result = await service.me(token)
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
    rights = entitlements_for_plan(result.plan)
    return MeResponse(
        id=result.user_id,
        email=result.email,
        plan=result.plan,
        active_device_count=result.active_device_count,
        subscription=None
        if result.subscription is None
        else SubscriptionAccessResponse(
            plan=result.subscription.plan,
            status=result.subscription.status,
            auto_renew=result.subscription.auto_renew,
            paid_until=(
                result.subscription.current_period_end
                if result.subscription.plan is not SubscriptionPlan.FREE
                else None
            ),
        ),
        entitlements=EntitlementsResponse(
            vpn_session_limit_seconds=(
                int(rights.vpn_session_limit.total_seconds()) if rights.vpn_session_limit else None
            ),
            rewarded_ad_required=rights.rewarded_ad_required,
            country_selection_allowed=rights.country_selection_allowed,
            free_nodes_only=rights.free_nodes_only,
            active_device_limit=rights.active_device_limit,
            daily_vpn_limit_seconds=(
                result.daily_vpn_limit_seconds
                if result.daily_vpn_limit_seconds is not None
                else rights.daily_vpn_limit_seconds
            ),
            free_seconds_remaining=result.free_seconds_remaining,
            free_quota_resets_at=result.free_quota_resets_at,
            free_seconds_usable=result.free_seconds_usable,
            free_running_sessions=result.free_running_sessions,
            quota_observed_at=result.quota_observed_at,
        ),
    )
