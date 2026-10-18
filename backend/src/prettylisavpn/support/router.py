"""Bounded multipart transport. No client filenames, bodies or parser errors are logged."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.main_errors import error_response
from prettylisavpn.support.domain import Receipt, Report, SupportError
from prettylisavpn.support.images import FILE_BYTES, TOTAL_BYTES, clean_image
from prettylisavpn.support.service import SupportService, fingerprint

logger = logging.getLogger(__name__)


class SupportRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private(request: Request) -> Response:
            try:
                response = await handler(request)
            except SupportError as error:
                response = error_response(error.code, error.status)
            except (
                RequestValidationError,
                ValidationError,
                HTTPException,
                ValueError,
                UnicodeError,
            ):
                response = error_response("INVALID_REQUEST", 422)
            except (
                InvalidAccessTokenError,
                InvalidSessionError,
                BlockedUserError,
                RevokedDeviceError,
            ):
                response = error_response("AUTH_INVALID", 401)
            except AuthServiceUnavailableError:
                response = error_response("SUPPORT_UNAVAILABLE", 503)
            except Exception:
                logger.warning("support_request_unavailable")
                response = error_response("SUPPORT_UNAVAILABLE", 503)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization"
            if response.status_code == 429:
                response.headers["Retry-After"] = "3600"
            return response

        return private


router = APIRouter(prefix="/support/requests", tags=["support"], route_class=SupportRoute)


@router.post(
    "",
    response_model=Receipt,
    status_code=202,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["report"],
                        "additionalProperties": False,
                        "properties": {
                            "report": {
                                "type": "string",
                                "description": "JSON Report; see docs/support-ui.md",
                            },
                            "screenshots": {
                                "type": "array",
                                "maxItems": 3,
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                    }
                }
            },
        },
    },
)
async def submit(request: Request, token: Annotated[str | None, Depends(bearer_token)]) -> Response:
    if token is None:
        raise SupportError("AUTH_INVALID", 401)
    service = cast(SupportService, request.app.state.support)
    identity = await service.auth.authenticate(token)
    if not request.headers.get("content-type", "").startswith("multipart/form-data;"):
        raise SupportError("INVALID_REQUEST", 422)
    async with asyncio.timeout(30), service.upload_slots:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > TOTAL_BYTES + 65536:
                raise SupportError("ATTACHMENT_REJECTED", 413)
        request._body = bytes(raw)
        async with request.form(max_files=3, max_fields=1, max_part_size=32768) as form:
            if set(form.keys()) - {"report", "screenshots"} or len(form.getlist("report")) != 1:
                raise SupportError("INVALID_REQUEST", 422)
            report_json = form["report"]
            if not isinstance(report_json, str):
                raise SupportError("INVALID_REQUEST", 422)
            report = Report.model_validate_json(report_json)
            incoming: list[tuple[bytes, str]] = []
            for file in form.getlist("screenshots"):
                if not isinstance(file, UploadFile):
                    raise SupportError("ATTACHMENT_REJECTED", 422)
                data = await file.read(FILE_BYTES + 1)
                if len(data) > FILE_BYTES:
                    raise SupportError("ATTACHMENT_REJECTED", 422)
                incoming.append((data, file.content_type or ""))
            if sum(len(data) for data, _ in incoming) > TOTAL_BYTES:
                raise SupportError("ATTACHMENT_REJECTED", 422)
            files = [await run_in_threadpool(clean_image, data, media) for data, media in incoming]
    result = await service.accept(identity, report, fingerprint(report, incoming), files)
    return JSONResponse(result.model_dump(mode="json"), status_code=202)


@router.get("/{request_id}", response_model=Receipt)
async def status(
    request_id: UUID, request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> Response:
    if token is None:
        raise SupportError("AUTH_INVALID", 401)
    service = cast(SupportService, request.app.state.support)
    identity = await service.auth.authenticate(token)
    result = await service.get(identity, request_id)
    return JSONResponse(result.model_dump(mode="json"))
