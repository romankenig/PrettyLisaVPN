"""Application factory and thin operational HTTP endpoints."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres, Valkey
from prettylisavpn.logging import configure_logging
from prettylisavpn.readiness import Dependency, Readiness

logger = logging.getLogger(__name__)


def error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status_code)


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
                app.state.readiness = Readiness(pg, cache, config.dependency_timeout_seconds)
                logger.info("application_started")
                yield
            finally:
                await cache.close()
        finally:
            await pg.close()
            logger.info("application_stopped")

    app = FastAPI(
        title=config.application_name, version=config.application_version, lifespan=lifespan
    )
    app.add_middleware(SafeExceptionMiddleware)

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
