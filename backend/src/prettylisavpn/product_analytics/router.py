"""Read-only aggregate API behind the existing monitor credential."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.fleet.router import authorize
from prettylisavpn.product_analytics.service import ProductAnalyticsService

router = APIRouter(prefix="/admin/monitoring", tags=["product-analytics"])


def reader(
    request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> ProductAnalyticsService:
    authorize(request, token, write=False)
    return cast(ProductAnalyticsService, request.app.state.product_analytics)


@router.get("/product-analytics")
async def analytics(service: Annotated[ProductAnalyticsService, Depends(reader)]) -> dict[str, Any]:
    return await service.latest()
