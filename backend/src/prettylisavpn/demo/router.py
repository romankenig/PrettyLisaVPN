"""Bounded guest admission; Android sends an app-scoped hash, never a hardware ID."""

from typing import Annotated, cast

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from prettylisavpn.auth.router import (
    LoginDeviceResponse,
    LoginSubscriptionResponse,
    LoginUserResponse,
    VerifyOtpResponse,
)
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.demo.domain import DemoRateLimitedError, DemoUnavailableError
from prettylisavpn.demo.service import DemoService
from prettylisavpn.main_errors import error_response

router = APIRouter(prefix="/auth", tags=["auth"])


def private_error(code: str, status: int) -> JSONResponse:
    response = error_response(code, status)
    response.headers["Cache-Control"] = "no-store"
    return response


class DemoLoginBody(BaseModel):
    device_key: Annotated[
        str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$", repr=False)
    ]


@router.post("/demo", response_model=VerifyOtpResponse)
async def demo_login(
    body: DemoLoginBody, request: Request, response: Response
) -> VerifyOtpResponse | JSONResponse:
    response.headers["Cache-Control"] = "no-store"
    service = cast(DemoService | None, request.app.state.demo)
    if service is None:
        return private_error("DEMO_UNAVAILABLE", 503)
    try:
        result = await service.login(
            body.device_key, request.client.host if request.client else "unknown"
        )
    except DemoRateLimitedError:
        return private_error("DEMO_RATE_LIMITED", 429)
    except DemoUnavailableError:
        return private_error("DEMO_UNAVAILABLE", 503)
    except BlockedUserError:
        return private_error("user_blocked", 403)
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
            plan=result.subscription.plan, status=result.subscription.status
        ),
    )
