"""Thin administrative API. Read-only monitoring credentials cannot configure nodes."""

import hmac
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.config import Settings
from prettylisavpn.fleet.domain import FleetError, NodeInput, NodeUpdate, WireGuardConfig
from prettylisavpn.fleet.service import FleetService

router = APIRouter(prefix="/admin", tags=["fleet"])


def authorize(request: Request, token: str | None, *, write: bool) -> None:
    settings = cast(Settings, request.app.state.fleet_settings)
    if not settings.fleet_enabled:
        raise FleetError("fleet_disabled", 503)
    admin = settings.fleet_admin_token
    reader = settings.fleet_monitor_token
    admin_ok = bool(token and admin and hmac.compare_digest(token, admin.get_secret_value()))
    reader_ok = bool(token and reader and hmac.compare_digest(token, reader.get_secret_value()))
    if not admin_ok and not reader_ok:
        raise FleetError("fleet_authentication_required", 401)
    if write and not admin_ok:
        raise FleetError("fleet_administrator_required", 403)


def admin(request: Request, token: Annotated[str | None, Depends(bearer_token)]) -> FleetService:
    authorize(request, token, write=True)
    return cast(FleetService, request.app.state.fleet)


def reader(request: Request, token: Annotated[str | None, Depends(bearer_token)]) -> FleetService:
    authorize(request, token, write=False)
    return cast(FleetService, request.app.state.fleet)


@router.post("/nodes", status_code=201)
async def register(
    data: NodeInput, service: Annotated[FleetService, Depends(admin)]
) -> dict[str, Any]:
    return await service.register(data)


@router.get("/nodes")
async def nodes(service: Annotated[FleetService, Depends(admin)]) -> list[dict[str, Any]]:
    return await service.nodes()


@router.patch("/nodes/{node_id}")
async def update_node(
    node_id: UUID, data: NodeUpdate, service: Annotated[FleetService, Depends(admin)]
) -> dict[str, Any]:
    return await service.update_node(node_id, data)


@router.post("/nodes/{node_id}/methods/{method}/configuration", status_code=202)
async def configure(
    node_id: UUID,
    method: str,
    data: WireGuardConfig,
    service: Annotated[FleetService, Depends(admin)],
    idempotency_key: Annotated[UUID, Header()],
) -> dict[str, Any]:
    return await service.enqueue(node_id, method, "CONFIGURE", idempotency_key, data)


@router.post("/nodes/{node_id}/methods/{method}/checks", status_code=202)
async def check(
    node_id: UUID,
    method: str,
    service: Annotated[FleetService, Depends(admin)],
    idempotency_key: Annotated[UUID, Header()],
) -> dict[str, Any]:
    return await service.enqueue(node_id, method, "CHECK", idempotency_key)


@router.get("/operations/{operation_id}")
async def operation(
    operation_id: UUID, service: Annotated[FleetService, Depends(admin)]
) -> dict[str, Any]:
    return await service.operation(operation_id)


@router.get("/monitoring/availability")
async def monitoring(
    service: Annotated[FleetService, Depends(reader)],
    node_id: UUID | None = None,
    days: Annotated[int, Query(ge=1, le=7)] = 7,
) -> dict[str, Any]:
    return await service.monitoring(node_id, days)
