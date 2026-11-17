"""Shared transport validation for private report tariff selections."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query

from prettylisavpn.product_analytics.domain import PlanFilter, parse_plan_filter


def report_plan(plan: Annotated[list[str] | None, Query(max_length=10)] = None) -> PlanFilter:
    try:
        return parse_plan_filter(",".join(plan) if plan is not None else None)
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "invalid_report_tariffs"}) from None


ReportPlanQuery = Annotated[PlanFilter, Depends(report_plan)]
