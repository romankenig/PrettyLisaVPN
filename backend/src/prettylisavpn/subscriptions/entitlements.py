"""Plan entitlements independent of payment-provider details."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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


def free_quota_resets_at(at: datetime) -> datetime:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    return at.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def free_session_duration(at: datetime, remaining_seconds: int) -> timedelta:
    if not 0 < remaining_seconds <= 3600:
        raise ValueError("remaining_seconds must be within the daily budget")
    return min(timedelta(seconds=remaining_seconds), free_quota_resets_at(at) - at)
