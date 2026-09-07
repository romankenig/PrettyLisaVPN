from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from prettylisavpn.subscriptions.domain import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from prettylisavpn.subscriptions.entitlements import (
    FREE_ENTITLEMENTS,
    PREMIUM_ENTITLEMENTS,
    entitlements_for,
)


def subscription(
    *,
    plan: SubscriptionPlan,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    period_end: datetime | None = None,
    auto_renew: bool = False,
) -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan=plan,
        status=status,
        current_period_start=now - timedelta(days=1),
        current_period_end=period_end,
        auto_renew=auto_renew,
        created_at=now,
        updated_at=now,
    )


def test_new_free_subscription_defaults():
    now = datetime.now(UTC)

    created = Subscription.new_free(uuid4(), now)

    assert created.plan is SubscriptionPlan.FREE
    assert created.status is SubscriptionStatus.ACTIVE
    assert created.current_period_start == now
    assert created.current_period_end is None
    assert not created.auto_renew


def test_plan_entitlements_are_provider_independent():
    now = datetime.now(UTC)
    free = subscription(plan=SubscriptionPlan.FREE)
    premium = subscription(
        plan=SubscriptionPlan.PREMIUM,
        period_end=now + timedelta(days=30),
        auto_renew=True,
    )

    assert entitlements_for(free, now) == FREE_ENTITLEMENTS
    assert entitlements_for(premium, now) == PREMIUM_ENTITLEMENTS
    assert FREE_ENTITLEMENTS.vpn_session_limit == timedelta(minutes=15)
    assert PREMIUM_ENTITLEMENTS.vpn_session_limit is None


def test_expired_premium_receives_free_entitlements():
    now = datetime.now(UTC)
    expired = subscription(
        plan=SubscriptionPlan.PREMIUM,
        period_end=now - timedelta(seconds=1),
        auto_renew=True,
    )

    assert entitlements_for(expired, now) == FREE_ENTITLEMENTS


def test_subscription_rejects_invalid_period():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="current_period_end"):
        Subscription(
            id=uuid4(),
            user_id=uuid4(),
            plan=SubscriptionPlan.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now,
            auto_renew=True,
            created_at=now,
            updated_at=now,
        )


def test_free_subscription_cannot_auto_renew():
    with pytest.raises(ValueError, match="FREE subscriptions cannot auto-renew"):
        subscription(plan=SubscriptionPlan.FREE, auto_renew=True)
