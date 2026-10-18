"""Application factory and thin operational HTTP endpoints."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
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
from prettylisavpn.billing.router import router as billing_router
from prettylisavpn.billing.service import BillingOverviewPort, BillingOverviewService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey
from prettylisavpn.devices.management import DeviceManagementHandler, DeviceManagementService
from prettylisavpn.devices.router import router as devices_router
from prettylisavpn.emailing.domain import EmailProvider, EmailProviderConfigurationError
from prettylisavpn.emailing.timeweb import TimewebEmailProvider
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
from prettylisavpn.vpn_nodes.agent import HttpNodeAgentClient, NodeAgentPort
from prettylisavpn.vpn_nodes.countries import (
    DatabaseVpnCountryCatalog,
    VpnCountryAvailabilityHandler,
    VpnCountryAvailabilityService,
)
from prettylisavpn.vpn_nodes.monitor import NodeHealthMonitorPort, VpnNodeHealthMonitor
from prettylisavpn.vpn_nodes.router import router as vpn_router
from prettylisavpn.vpn_sessions.connection import (
    UnavailableVpnConnectionService,
    VpnConnectionHandler,
    VpnConnectionService,
)
from prettylisavpn.vpn_sessions.status import VpnSessionStatusHandler, VpnSessionStatusService
from prettylisavpn.vpn_sessions.termination import (
    UnavailableVpnTerminationService,
    VpnSessionReconciler,
    VpnSessionReconcilerPort,
    VpnSessionTerminationService,
    VpnTerminationHandler,
)

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
    node_health_monitor: NodeHealthMonitorPort | None = None,
    vpn_country_availability: VpnCountryAvailabilityHandler | None = None,
    vpn_connection: VpnConnectionHandler | None = None,
    vpn_session_status: VpnSessionStatusHandler | None = None,
    node_agent: NodeAgentPort | None = None,
    vpn_termination: VpnTerminationHandler | None = None,
    vpn_session_reconciler: VpnSessionReconcilerPort | None = None,
    support_mailer: SupportMailPort | None = None,
    support_worker: SupportWorkerPort | None = None,
    billing: BillingOverviewPort | None = None,
) -> FastAPI:
    config = settings if settings is not None else Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pg = postgres if postgres is not None else Postgres(config)
        try:
            cache = valkey if valkey is not None else Valkey(config)
            try:
                app.state.postgres = pg
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
                app.state.billing = billing or BillingOverviewService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                )
                app.state.support = SupportService(
                    cast(Postgres, pg),
                    cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                )
                active_support_worker = support_worker or SupportWorker(
                    cast(Postgres, pg), support_mailer or SupportSmtpMailer.from_settings(config)
                )
                app.state.support_worker = active_support_worker
                app.state.vpn_country_availability = (
                    vpn_country_availability
                    if vpn_country_availability is not None
                    else VpnCountryAvailabilityService(
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        DatabaseVpnCountryCatalog(
                            cast(Postgres, pg),
                            timedelta(seconds=config.vpn_node_stale_timeout_seconds),
                        ),
                    )
                )
                app.state.readiness = Readiness(pg, cache, config.dependency_timeout_seconds)
                monitor = node_health_monitor
                agent_client: HttpNodeAgentClient | None = None
                active_agent = node_agent
                if active_agent is None and config.vpn_node_agent_is_configured():
                    agent_client = HttpNodeAgentClient.from_settings(config)
                    active_agent = agent_client
                app.state.device_management = (
                    device_management
                    if device_management is not None
                    else DeviceManagementService(
                        cast(Postgres, pg),
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        cast(ProductEventSink, app.state.product_events),
                        config,
                        active_agent,
                    )
                )
                if monitor is None and active_agent is not None:
                    monitor = VpnNodeHealthMonitor(cast(Postgres, pg), active_agent, config)
                app.state.vpn_connection = (
                    vpn_connection
                    if vpn_connection is not None
                    else VpnConnectionService(
                        cast(Postgres, pg),
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        active_agent,
                        config,
                    )
                    if active_agent is not None
                    else UnavailableVpnConnectionService(
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions)
                    )
                )
                app.state.vpn_session_status = (
                    vpn_session_status
                    if vpn_session_status is not None
                    else VpnSessionStatusService(
                        cast(Postgres, pg),
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        config,
                    )
                )
                app.state.vpn_termination = (
                    vpn_termination
                    if vpn_termination is not None
                    else VpnSessionTerminationService(
                        cast(Postgres, pg),
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions),
                        active_agent,
                    )
                    if active_agent is not None
                    else UnavailableVpnTerminationService(
                        cast(AuthenticatedSessionHandler, app.state.authenticated_sessions)
                    )
                )
                reconciler = vpn_session_reconciler
                if reconciler is None and active_agent is not None:
                    reconciler = VpnSessionReconciler(cast(Postgres, pg), active_agent, config)
                monitor_stop = asyncio.Event()
                monitor_task = (
                    asyncio.create_task(monitor.run(monitor_stop)) if monitor is not None else None
                )
                reconciler_task = (
                    asyncio.create_task(reconciler.run(monitor_stop))
                    if reconciler is not None
                    else None
                )
                support_task = (
                    asyncio.create_task(active_support_worker.run(monitor_stop))
                    if isinstance(pg, Postgres)
                    else None
                )
                logger.info("application_started")
                try:
                    yield
                finally:
                    monitor_stop.set()
                    if support_task is not None:
                        await support_task
                    if monitor_task is not None:
                        monitor_stop.set()
                        await monitor_task
                    if reconciler_task is not None:
                        monitor_stop.set()
                        await reconciler_task
                    if agent_client is not None:
                        await agent_client.close()
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
    app.include_router(account_router)
    app.include_router(devices_router)
    app.include_router(vpn_router)
    app.include_router(messages_router)
    app.include_router(support_router)
    app.include_router(billing_router)

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
