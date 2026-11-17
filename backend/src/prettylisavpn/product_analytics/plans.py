"""Historical tariff attribution; never backfill a past event from today's subscription."""

from typing import cast

from sqlalchemy import case, func
from sqlalchemy.sql.elements import ColumnElement

from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.demo.domain import DEMO_EMAIL_DOMAIN, is_demo_email
from prettylisavpn.product_analytics.domain import PLANS, Plan
from prettylisavpn.users.model import UserRecord


def lease_plan(row: ClientLeaseRecord, email: str) -> Plan:
    if row.plan_snapshot in PLANS:
        return cast(Plan, row.plan_snapshot)
    if is_demo_email(email):
        return "DEMO"
    return "FREE" if row.is_free else "UNKNOWN"


def lease_plan_expression() -> ColumnElement[str]:
    """Requires the owning UserRecord join; old paid leases cannot distinguish paid plans."""
    return case(
        (ClientLeaseRecord.plan_snapshot.in_(PLANS), ClientLeaseRecord.plan_snapshot),
        (func.lower(func.trim(UserRecord.email)).like("%@" + DEMO_EMAIL_DOMAIN), "DEMO"),
        (ClientLeaseRecord.is_free.is_(True), "FREE"),
        else_="UNKNOWN",
    )
