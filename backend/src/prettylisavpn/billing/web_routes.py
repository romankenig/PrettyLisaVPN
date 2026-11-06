"""Same-origin cookie transport for the hosted billing portal."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from starlette.responses import JSONResponse, Response

from prettylisavpn.auth.router import RequestOtpBody, bearer_token, request_otp
from prettylisavpn.auth.service import InvalidOtpError
from prettylisavpn.auth.session_service import AuthenticatedSessionHandler, InvalidSessionError
from prettylisavpn.billing.domain import Overview
from prettylisavpn.billing.operations import BillingOperationsService
from prettylisavpn.billing.operations_domain import BillingCommand, BillingOperation
from prettylisavpn.billing.router import BillingRoute
from prettylisavpn.billing.service import BillingOverviewService
from prettylisavpn.billing.web_sessions import COOKIE, SESSION_TTL, WEB_ORIGIN, BillingWebSessions
from prettylisavpn.main_errors import error_response


class WebRoute(BillingRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def protected(request: Request) -> Response:
            response: Response
            # Reject cross-origin requests before reading any authenticated cookie/body.
            if request.method != "GET" and (
                request.headers.get("origin") != WEB_ORIGIN
                or request.headers.get("X-PrettyLisa-Web") != "1"
                or request.headers.get("content-type", "").split(";")[0] != "application/json"
            ):
                response = error_response("WEB_ORIGIN_INVALID", 403)
            else:
                response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Cookie, Origin"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        return protected


router = APIRouter(prefix="/api/web/billing", tags=["billing-web"], route_class=WebRoute)
native_router = APIRouter(prefix="/billing", tags=["billing"], route_class=BillingRoute)


class LoginBody(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")


class ExchangeBody(BaseModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$", repr=False)


class PortalResponse(BaseModel):
    url: str = Field(repr=False)


class WebOverview(BaseModel):
    account_id: UUID
    email: EmailStr
    billing: Overview


def service(request: Request) -> BillingWebSessions:
    return cast(BillingWebSessions, request.app.state.billing_web_sessions)


async def identity(request: Request) -> UUID:
    return await service(request).authenticate(request.cookies.get(COOKIE))


async def accept(request: Request, token: str) -> Response:
    previous = request.cookies.get(COOKIE)
    if previous:
        # Do not preserve a pre-login session (session fixation/account switch).
        try:
            await service(request).tokens.revoke(previous)
        except InvalidSessionError:
            pass
    response = JSONResponse({"status": "authenticated"})
    response.set_cookie(
        COOKIE, token, max_age=SESSION_TTL, secure=True, httponly=True, samesite="strict", path="/"
    )
    return response


@router.post("/request-otp", status_code=202)
async def send_otp(body: RequestOtpBody, request: Request) -> Response:
    result = await request_otp(body, request)
    return result if isinstance(result, Response) else JSONResponse(result.model_dump(), 202)


@router.post("/login")
async def login(body: LoginBody, request: Request) -> Response:
    try:
        token = await service(request).login(str(body.email), body.code)
    except InvalidOtpError:
        return error_response("otp_invalid", 401)
    return await accept(request, token)


@native_router.post("/portal", response_model=PortalResponse)
async def portal(
    request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> PortalResponse | Response:
    if token is None:
        return error_response("AUTH_INVALID", 401)
    account = await cast(
        AuthenticatedSessionHandler, request.app.state.authenticated_sessions
    ).authenticate(token)
    return PortalResponse(url=await service(request).handoff(account.user_id))


@router.post("/exchange")
async def exchange(body: ExchangeBody, request: Request) -> Response:
    return await accept(request, await service(request).exchange(body.token))


@router.post("/logout")
async def logout(request: Request, _: Annotated[UUID, Depends(identity)]) -> Response:
    await service(request).tokens.revoke(request.cookies[COOKIE])
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
    return response


@router.get("/overview", response_model=WebOverview)
async def overview(request: Request, user_id: Annotated[UUID, Depends(identity)]) -> WebOverview:
    billing = await cast(BillingOverviewService, request.app.state.billing).overview_for_account(
        user_id
    )
    return WebOverview(
        account_id=user_id, email=await service(request).email(user_id), billing=billing
    )


@router.post("/operations", response_model=BillingOperation)
async def start(
    request: Request, command: BillingCommand, user_id: Annotated[UUID, Depends(identity)]
) -> BillingOperation:
    return await cast(
        BillingOperationsService, request.app.state.billing_operations
    ).start_for_account(user_id, command)


@router.get("/operations/{operation_id}", response_model=BillingOperation)
async def operation(
    request: Request, operation_id: UUID, user_id: Annotated[UUID, Depends(identity)]
) -> BillingOperation:
    return await cast(
        BillingOperationsService, request.app.state.billing_operations
    ).get_for_account(user_id, operation_id)
