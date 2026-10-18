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
    free_session_duration,
    free_quota_resets_at,
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
    assert FREE_ENTITLEMENTS.vpn_session_limit == timedelta(hours=1)
    assert FREE_ENTITLEMENTS.daily_vpn_limit_seconds == 3600
    assert FREE_ENTITLEMENTS.rewarded_ad_required is False
    assert PREMIUM_ENTITLEMENTS.vpn_session_limit is None
    assert FREE_ENTITLEMENTS.country_selection_allowed is True
    assert PREMIUM_ENTITLEMENTS.country_selection_allowed is True


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


@pytest.mark.parametrize("status", [SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED])
@pytest.mark.parametrize("offset,expected", [(-1, True), (0, False), (1, False)])
def test_paid_access_uses_exclusive_paid_deadline_independent_of_renewal(status, offset, expected):
    end = datetime.now(UTC) + timedelta(days=1)
    paid = subscription(plan=SubscriptionPlan.PREMIUM, status=status, period_end=end)
    at = end + timedelta(microseconds=offset)
    assert paid.is_active(at) is expected
    assert paid.effective_plan(at) is (SubscriptionPlan.PREMIUM if expected else SubscriptionPlan.FREE)
    assert entitlements_for(paid, at) == (PREMIUM_ENTITLEMENTS if expected else FREE_ENTITLEMENTS)


def test_cancel_renewal_is_idempotent_and_preserves_paid_dates():
    now = datetime.now(UTC)
    paid = subscription(plan=SubscriptionPlan.PREMIUM, period_end=now + timedelta(days=10), auto_renew=True)
    canceled = paid.cancel_auto_renew(now)
    assert canceled.status is SubscriptionStatus.CANCELED
    assert not canceled.auto_renew
    assert canceled.current_period_start == paid.current_period_start
    assert canceled.current_period_end == paid.current_period_end
    assert canceled.effective_plan(now) is SubscriptionPlan.PREMIUM
    assert canceled.cancel_auto_renew(now + timedelta(days=1)) == canceled


def test_missing_paid_deadline_and_explicit_expiration_do_not_grant_premium():
    now = datetime.now(UTC)
    for paid in [subscription(plan=SubscriptionPlan.PREMIUM), subscription(plan=SubscriptionPlan.PREMIUM, status=SubscriptionStatus.EXPIRED, period_end=now + timedelta(days=1))]:
        assert paid.effective_plan(now) is SubscriptionPlan.FREE


def test_future_paid_period_does_not_grant_access_early():
    paid = subscription(plan=SubscriptionPlan.PREMIUM, period_end=datetime.now(UTC) + timedelta(days=10))
    assert not paid.is_active(paid.current_period_start - timedelta(microseconds=1))


def test_canceled_subscription_cannot_claim_auto_renew():
    with pytest.raises(ValueError, match="CANCELED subscriptions cannot auto-renew"):
        subscription(plan=SubscriptionPlan.PREMIUM, status=SubscriptionStatus.CANCELED, auto_renew=True)


def test_manual_platinum_has_exact_premium_capabilities():
    now = datetime.now(UTC)
    platinum = subscription(plan=SubscriptionPlan.PLATINUM, period_end=now + timedelta(days=30))
    assert platinum.effective_plan(now) is SubscriptionPlan.PLATINUM
    assert entitlements_for(platinum, now) == PREMIUM_ENTITLEMENTS
    assert platinum.effective_plan(platinum.current_period_end) is SubscriptionPlan.FREE


def test_free_duration_uses_remaining_budget_and_utc_midnight():
    at = datetime(2026, 10, 16, 23, 50, tzinfo=UTC)
    assert free_session_duration(at, 3600) == timedelta(minutes=10)
    assert free_session_duration(at, 30) == timedelta(seconds=30)
    assert free_quota_resets_at(at) == datetime(2026, 10, 17, tzinfo=UTC)
    assert free_session_duration(datetime(2026, 10, 17, tzinfo=UTC), 3600) == timedelta(hours=1)


@pytest.mark.parametrize("remaining", [0, -1, 3601])
def test_free_duration_rejects_invalid_budget(remaining):
    with pytest.raises(ValueError, match="daily budget"):
        free_session_duration(datetime.now(UTC), remaining)

