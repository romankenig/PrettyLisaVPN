"""Application factory and thin operational HTTP endpoints."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from prettylisavpn.account_messages.router import router as messages_router
from prettylisavpn.account_messages.service import AccountMessagesService
from prettylisavpn.auth.events import DatabaseProductEventSink
from prettylisavpn.auth.router import account_router
from prettylisavpn.auth.router import router as auth_router
from prettylisavpn.auth.service import (
    LoginHandler,
    LoginService,
    OtpIssuer,
    OtpVerifier,
    ProductEventSink,
)
from prettylisavpn.auth.session_service import (
    AuthenticatedSessionHandler,
    AuthenticatedSessionService,
)
from prettylisavpn.billing.operations import BillingOperationsService
from prettylisavpn.billing.provider import BillingProvider, validate_provider
from prettylisavpn.billing.router import router as billing_router
from prettylisavpn.billing.sandbox import SandboxBillingProvider
from prettylisavpn.billing.service import BillingOverviewPort, BillingOverviewService
from prettylisavpn.billing.worker import BillingWorkerPort
from prettylisavpn.client_vpn.router import router as client_vpn_router
from prettylisavpn.client_vpn.service import ClientVpnService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey
from prettylisavpn.devices.management import DeviceManagementHandler, DeviceManagementService
from prettylisavpn.devices.router import router as devices_router
from prettylisavpn.emailing.domain import EmailProvider, EmailProviderConfigurationError
from prettylisavpn.emailing.timeweb import TimewebEmailProvider
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.fleet.router import router as fleet_router
from prettylisavpn.fleet.service import FleetService
from prettylisavpn.locations import router as locations_router
from prettylisavpn.logging import configure_logging
from prettylisavpn.main_errors import error_response
from prettylisavpn.readiness import Dependency, Readiness
from prettylisavpn.support.delivery import (
    SupportMailPort,
    SupportSmtpMailer,
    SupportWorker,
    SupportWorkerPort,
)
from prettylisavpn.support.router import router as support_router
from prettylisavpn.support.service import SupportService

logger = logging.getLogger(__name__)


class SafeExceptionMiddleware:
    """Contain unexpected errors before Uvicorn can log sensitive tracebacks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            logger.error("request_failed")
            if not started:
                await error_response("internal_error", 500)(scope, receive, send)


class HealthResponse(BaseModel):
    status: str = "ok"


class VersionResponse(BaseModel):
    application_name: str
    application_version: str
    environment: str


class ReadyResponse(BaseModel):
    status: str
    dependencies: dict[str, bool]


def create_app(
    settings: Settings | None = None,
    *,
    postgres: Dependency | None = None,
    valkey: Dependency | None = None,
    otp_service: OtpIssuer | None = None,
    email_provider: EmailProvider | None = None,
    product_events: ProductEventSink | None = None,
    login_service: LoginHandler | None = None,
    authenticated_sessions: AuthenticatedSessionHandler | None = None,
    device_management: DeviceManagementHandler | None = None,
    support_mailer: SupportMailPort | None = None,
    support_worker: SupportWorkerPort | None = None,
    billing: BillingOverviewPort | None = None,
    billing_provider: BillingProvider | None = None,
    billing_worker: BillingWorkerPort | None = None,
    fleet: FleetService | None = None,
    client_vpn: ClientVpnService | None = None,
) -> FastAPI:
    validate_provider(billing_provider)
    config = settings if settings is not None else Settings()
    if billing_provider is not None and config.environment not in ("development", "test"):
        raise ValueError("Sandbox billing requires development or test environment")
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pg = postgres if postgres is not None else Postgres(config)
        try:
            active_billing_provider = billing_provider
            if active_billing_provider is None and config.billing_provider == "sandbox":
                active_billing_provider = SandboxBillingProvider(cast(Postgres, pg), config)
            cache = valkey if valkey is not None else Valkey(config)
            try:
                app.state.postgres = pg
                app.state.fleet_settings = config
                app.state.fleet = fleet or FleetService(cast(Postgres, pg), config)
                app.state.valkey = cache
                app.state.otp_service = (
                    otp_service if otp_service is not None else cast(Valkey, cache).otp
                )
                if email_provider is not None:
                    app.state.email_provider = email_provider
                else:
                    try:
                        app.state.email_provider = TimewebEmailProvider.from_settings(config)
                    except EmailProviderConfigurationError:
                        logger.warning("email_provider_configuration_invalid")
                        app.state.email_provider = None
                app.state.product_events = (
                    product_events
                    if product_events is not None
                    else DatabaseProductEventSink(cast(Postgres, pg))
                )
                app.state.login_service = (
                    login_service
                    if login_service is not None
                    else LoginService(
                        cast(OtpVerifier, app.state.otp_service),
                        cast(Postgres, pg),
                        cast(ProductEventSink, app.state.product_events),
                        config,
                    )
                )
                app.state.authenticated_sessions = (
                    authenticated_sessions
                    if authenticated_sessions is not None
                    else AuthenticatedSessionService(
                        cast(Postgres, pg),
                        cast(ProductEventSink, app.state.product_events),
                        config,
                    )
                )
                app.state.account_messages = AccountMessagesService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                )
                app.state.client_vpn = client_vpn or ClientVpnService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                    config,
                    cast(FleetService, app.state.fleet),
                )
                app.state.billing = billing or BillingOverviewService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                    active_billing_provider,
                )
                app.state.billing_operations = BillingOperationsService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                    active_billing_provider,
                )
                active_billing_worker = billing_worker or app.state.billing_operations.worker
                app.state.support = SupportService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                )
                active_support_worker = support_worker or SupportWorker(
                    cast(Postgres, pg), support_mailer or SupportSmtpMailer.from_settings(config)
                )
                app.state.support_worker = active_support_worker
                app.state.device_management = (
                    device_management
                    if device_management is not None
                    else DeviceManagementService(
                        cast(Postgres, pg),
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        cast(ProductEventSink, app.state.product_events),
                        config,
                    )
                )
                monitor_stop = asyncio.Event()
                app.state.readiness = Readiness(pg, cache, config.dependency_timeout_seconds)
                support_task = (
                    asyncio.create_task(active_support_worker.run(monitor_stop))
                    if isinstance(pg, Postgres)
                    else None
                )
                billing_task = (
                    asyncio.create_task(active_billing_worker.run(monitor_stop))
                    if active_billing_provider is not None and isinstance(pg, Postgres)
                    else None
                )
                logger.info("application_started")
                try:
                    yield
                finally:
                    monitor_stop.set()
                    if billing_task is not None:
                        await billing_task
                    if support_task is not None:
                        await support_task
            finally:
                await cache.close()
        finally:
            await pg.close()
            logger.info("application_stopped")

    app = FastAPI(
        title=config.application_name, version=config.application_version, lifespan=lifespan
    )
    app.add_middleware(SafeExceptionMiddleware)
    app.include_router(auth_router)
    app.include_router(client_vpn_router)
    app.include_router(account_router)
    app.include_router(devices_router)
    app.include_router(locations_router)
    app.include_router(messages_router)
    app.include_router(support_router)
    app.include_router(billing_router)
    app.include_router(fleet_router)

    @app.exception_handler(FleetError)
    async def fleet_error(request: Request, exc: FleetError) -> JSONResponse:
        return error_response(exc.code, exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return error_response(codes.get(exc.status_code, "http_error"), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response("validation_error", 422)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/ready", response_model=ReadyResponse, responses={503: {"description": "Not ready"}})
    async def ready(request: Request) -> ReadyResponse | JSONResponse:
        service: Readiness = request.app.state.readiness
        checks = await service.check()
        if not all(checks.values()):
            return JSONResponse(
                {
                    "status": "not_ready",
                    "dependencies": checks,
                    "error": {"code": "dependencies_unavailable"},
                },
                status_code=503,
            )
        return ReadyResponse(status="ready", dependencies=checks)

    @app.get("/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        return VersionResponse(
            application_name=config.application_name,
            application_version=config.application_version,
            environment=config.environment,
        )

    return app
