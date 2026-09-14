"""Plan entitlements independent of payment-provider details."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan


@dataclass(frozen=True, slots=True)
class PlanEntitlements:
    vpn_session_limit: timedelta | None
    rewarded_ad_required: bool
    country_selection_allowed: bool


FREE_ENTITLEMENTS = PlanEntitlements(
    vpn_session_limit=timedelta(minutes=15),
    rewarded_ad_required=True,
    country_selection_allowed=True,
)
PREMIUM_ENTITLEMENTS = PlanEntitlements(
    vpn_session_limit=None,
    rewarded_ad_required=False,
    country_selection_allowed=True,
)


def entitlements_for(subscription: Subscription, at: datetime) -> PlanEntitlements:
    if not subscription.is_active(at) or subscription.plan is SubscriptionPlan.FREE:
        return FREE_ENTITLEMENTS
    return PREMIUM_ENTITLEMENTS
