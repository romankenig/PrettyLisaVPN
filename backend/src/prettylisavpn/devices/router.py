"""HTTP transport for authenticated device management."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from prettylisavpn.auth.router import ErrorResponse, bearer_token
from prettylisavpn.auth.service import BlockedUserError
from prettylisavpn.auth.session_service import (
    AuthServiceUnavailableError,
    InvalidSessionError,
    RevokedDeviceError,
)
from prettylisavpn.auth.tokens import InvalidAccessTokenError
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.devices.management import (
    DeviceManagementHandler,
    DeviceManagementUnavailableError,
    DeviceNotFoundError,
    ManagedDevice,
)
from prettylisavpn.main_errors import error_response

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceResponse(BaseModel):
    id: UUID
    installation_id: UUID
    device_name: str
    platform: DevicePlatform
    status: DeviceStatus
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None
    is_current: bool


class RevokeDeviceResponse(BaseModel):
    status: Literal["revoked"] = "revoked"
    device: DeviceResponse


def _response(managed: ManagedDevice) -> DeviceResponse:
    device = managed.device
    return DeviceResponse(
        id=device.id,
        installation_id=device.installation_id,
        device_name=device.device_name,
        platform=device.platform,
        status=device.status,
        created_at=device.created_at,
        updated_at=device.updated_at,
        revoked_at=device.revoked_at,
        is_current=managed.is_current,
    )


def _authentication_error(error: Exception) -> JSONResponse:
    if isinstance(error, InvalidAccessTokenError):
        return error_response("invalid_access_token", 401)
    if isinstance(error, InvalidSessionError):
        return error_response("invalid_session", 401)
    if isinstance(error, BlockedUserError):
        return error_response("user_blocked", 403)
    if isinstance(error, RevokedDeviceError):
        return error_response("device_revoked", 403)
    if isinstance(error, AuthServiceUnavailableError):
        return error_response("auth_service_unavailable", 503)
    return error_response("device_service_unavailable", 503)


@router.get(
    "",
    response_model=list[DeviceResponse],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        503: {"model": ErrorResponse, "description": "Device service unavailable"},
    },
)
async def list_devices(
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> list[DeviceResponse] | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(DeviceManagementHandler, request.app.state.device_management)
    try:
        devices = await service.list_devices(token)
    except (
        InvalidAccessTokenError,
        InvalidSessionError,
        BlockedUserError,
        RevokedDeviceError,
        AuthServiceUnavailableError,
        DeviceManagementUnavailableError,
    ) as error:
        return _authentication_error(error)
    return [_response(device) for device in devices]


@router.delete(
    "/{device_id}",
    response_model=RevokeDeviceResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication is required or invalid"},
        403: {"model": ErrorResponse, "description": "User or current device is blocked"},
        404: {"model": ErrorResponse, "description": "Owned device not found"},
        503: {"model": ErrorResponse, "description": "Device service unavailable"},
    },
)
async def revoke_device(
    device_id: UUID,
    request: Request,
    token: Annotated[str | None, Depends(bearer_token)],
) -> RevokeDeviceResponse | JSONResponse:
    if token is None:
        return error_response("authentication_required", 401)
    service = cast(DeviceManagementHandler, request.app.state.device_management)
    try:
        device = await service.revoke_device(token, device_id)
    except DeviceNotFoundError:
        return error_response("device_not_found", 404)
    except (
        InvalidAccessTokenError,
        InvalidSessionError,
        BlockedUserError,
        RevokedDeviceError,
        AuthServiceUnavailableError,
        DeviceManagementUnavailableError,
    ) as error:
        return _authentication_error(error)
    return RevokeDeviceResponse(device=_response(device))
