"""Plan entitlements independent of payment-provider details."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan


@dataclass(frozen=True, slots=True)
class PlanEntitlements:
    vpn_session_limit: timedelta | None
    rewarded_ad_required: bool
    country_selection_allowed: bool
    free_nodes_only: bool
    active_device_limit: int = 5
    daily_vpn_limit_seconds: int | None = None


FREE_ENTITLEMENTS = PlanEntitlements(
    vpn_session_limit=timedelta(hours=1),
    rewarded_ad_required=False,
    country_selection_allowed=True,
    free_nodes_only=True,
    daily_vpn_limit_seconds=3600,
)
PREMIUM_ENTITLEMENTS = PlanEntitlements(
    vpn_session_limit=None,
    rewarded_ad_required=False,
    country_selection_allowed=True,
    free_nodes_only=False,
)


def entitlements_for(subscription: Subscription, at: datetime) -> PlanEntitlements:
    return entitlements_for_plan(subscription.effective_plan(at))


def entitlements_for_plan(plan: SubscriptionPlan) -> PlanEntitlements:
    return {
        SubscriptionPlan.FREE: FREE_ENTITLEMENTS,
        SubscriptionPlan.PREMIUM: PREMIUM_ENTITLEMENTS,
        SubscriptionPlan.PLATINUM: PREMIUM_ENTITLEMENTS,
    }[plan]

