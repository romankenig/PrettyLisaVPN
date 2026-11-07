"""Guest admission, private identity, fail-closed configuration and transport."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError

from prettylisavpn.auth.router import MeResponse, account_router
from prettylisavpn.auth.service import InvalidOtpError, LoginService, RequestOtpService
from prettylisavpn.auth.session_service import AccessIdentity, MeSummary
from prettylisavpn.client_vpn.domain import deadline
from prettylisavpn.config import Settings
from prettylisavpn.demo.domain import (
    DemoRateLimitedError,
    DemoUnavailableError,
    RegistrationRequiredError,
    identity_digest,
)
from prettylisavpn.demo.router import router
from prettylisavpn.demo.service import DemoService, RedisAdmissionLimit
from prettylisavpn.fleet.domain import FleetError
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan
from prettylisavpn.subscriptions.entitlements import entitlements_for_plan

NOW = datetime(2026, 11, 7, 23, 55, tzinfo=UTC)
KEY = "a" * 64


def test_demo_rights_never_become_free_and_expire_at_utc_midnight():
    demo = replace(Subscription.new_free(uuid4(), NOW), plan=SubscriptionPlan.DEMO)
    rights = entitlements_for_plan(demo.effective_plan(NOW - timedelta(days=1)))
    assert rights.daily_vpn_limit_seconds == 900
    assert rights.active_device_limit == 1 and rights.free_nodes_only
    assert not rights.country_selection_allowed and not rights.split_tunneling_allowed
    assert deadline(demo, NOW, 900) == (True, NOW + timedelta(minutes=5))
    with pytest.raises(FleetError, match="DEMO_QUOTA_EXHAUSTED"):
        deadline(demo, NOW, 0)
    with pytest.raises(ValueError, match="DEMO subscriptions cannot auto-renew"):
        replace(demo, auto_renew=True)
    assert entitlements_for_plan(SubscriptionPlan.FREE).daily_vpn_limit_seconds == 3600


def test_device_digest_is_stable_keyed_and_domain_separated():
    first = identity_digest("secret-a", KEY)
    assert len(first) == 32 and first == identity_digest("secret-a", KEY)
    assert first != identity_digest("secret-b", KEY)
    assert first != identity_digest("secret-a", "ip:" + KEY)
    AccessIdentity(uuid4(), uuid4(), uuid4()).require_registered()
    with pytest.raises(RegistrationRequiredError):
        AccessIdentity(uuid4(), uuid4(), uuid4(), True).require_registered()


def test_demo_requires_independent_stable_key():
    with pytest.raises(ValidationError):
        Settings(demo_enabled=True)
    settings = Settings()
    with pytest.raises(ValidationError):
        Settings(demo_enabled=True, demo_identity_secret=settings.otp_hmac_secret)


async def test_disabled_guest_never_calls_database_or_limiter():
    postgres, limit = AsyncMock(), AsyncMock()
    with pytest.raises(DemoUnavailableError):
        await DemoService(postgres, Settings(), limit).login(KEY, "1.2.3.4")
    assert not postgres.mock_calls and not limit.mock_calls


async def test_guest_limiter_fails_closed_and_uses_only_digests():
    redis = SimpleNamespace(eval=AsyncMock(return_value=1))
    limiter = RedisAdmissionLimit(redis)
    await limiter.admit("ip-digest", "device-digest")
    assert redis.eval.await_args.args[2:4] == ("demo:ip:ip-digest", "demo:device:device-digest")
    redis.eval.return_value = 0
    with pytest.raises(DemoRateLimitedError):
        await limiter.admit("ip", "device")
    redis.eval.side_effect = ConnectionError("private connection message")
    with pytest.raises(DemoUnavailableError):
        await limiter.admit("ip", "device")


async def test_reserved_guest_addresses_cannot_receive_otp_or_register():
    otp, events, mail = AsyncMock(), AsyncMock(), AsyncMock()
    email = "guest@demo.prettylisavpn.com"
    await RequestOtpService(otp, mail, events).request(email, "1.2.3.4")
    assert not otp.mock_calls and not mail.mock_calls
    with pytest.raises(InvalidOtpError):
        await LoginService(otp, AsyncMock(), events, Settings()).verify_otp(
            email, "123456", uuid4(), None, "phone"
        )
    otp.verify.assert_not_awaited()


@pytest.mark.parametrize(
    "error,status,code",
    [
        (DemoUnavailableError, 503, "DEMO_UNAVAILABLE"),
        (DemoRateLimitedError, 429, "DEMO_RATE_LIMITED"),
    ],
)
def test_guest_endpoint_has_stable_errors_and_bounded_identity(error, status, code):
    app = FastAPI()
    app.include_router(router)
    app.state.demo = SimpleNamespace(login=AsyncMock(side_effect=error))
    with TestClient(app) as client:
        response = client.post("/auth/demo", json={"device_key": KEY})
        assert response.status_code == status and response.json() == {"error": {"code": code}}
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/auth/demo", json={"device_key": "not-an-id"}).status_code == 422
        assert client.post("/auth/demo", json={"device_key": KEY * 100}).status_code == 422


def test_guest_profile_does_not_expose_synthetic_email_and_reports_900_seconds():
    app = FastAPI()
    app.include_router(account_router)
    app.state.authenticated_sessions = SimpleNamespace(
        me=AsyncMock(
            return_value=MeSummary(
                uuid4(),
                "private@demo.prettylisavpn.com",
                SubscriptionPlan.DEMO,
                1,
                free_seconds_remaining=900,
                free_seconds_usable=900,
                free_running_sessions=0,
                free_quota_resets_at=NOW + timedelta(minutes=5),
                daily_vpn_limit_seconds=900,
            )
        )
    )
    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer guest"})
    value = MeResponse.model_validate(response.json())
    assert value.email is None and "private" not in response.text
    assert value.plan is SubscriptionPlan.DEMO and value.entitlements.active_device_limit == 1
    assert value.entitlements.daily_vpn_limit_seconds == 900
    assert not value.entitlements.country_selection_allowed
    assert not value.entitlements.split_tunneling_allowed
