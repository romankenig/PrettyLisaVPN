"""Read-only aggregate API behind the existing monitor credential."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request

from prettylisavpn.auth.router import bearer_token
from prettylisavpn.fleet.router import authorize
from prettylisavpn.product_analytics.app_versions import AppVersionAnalytics
from prettylisavpn.product_analytics.report_filters import ReportPlanQuery
from prettylisavpn.product_analytics.service import ProductAnalyticsService

router = APIRouter(prefix="/admin/monitoring", tags=["product-analytics"])


def reader(
    request: Request, token: Annotated[str | None, Depends(bearer_token)]
) -> ProductAnalyticsService:
    authorize(request, token, write=False)
    return cast(ProductAnalyticsService, request.app.state.product_analytics)


@router.get("/product-analytics")
async def analytics(
    service: Annotated[ProductAnalyticsService, Depends(reader)], plan: ReportPlanQuery
) -> dict[str, Any]:
    return await service.latest(plan=plan)


@router.get("/app-versions")
async def app_versions(
    request: Request, token: Annotated[str | None, Depends(bearer_token)], plan: ReportPlanQuery
) -> dict[str, Any]:
    authorize(request, token, write=False)
    return await cast(AppVersionAnalytics, request.app.state.app_versions).latest(plan=plan)
