"""Account entitlements survive retirement of the connection implementation."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from legacy_data import clean_up, create_dependencies
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from prettylisavpn.auth.session_service import AuthenticatedSessionService
from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.model import SubscriptionRecord

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def access_state():
    config = Settings(
        _env_file=None, otp_hmac_secret="subscription-access-integration-secret-32-characters"
    )
    postgres = Postgres(config)
    user_id, device_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session, session.begin():
        issued = await AuthSessionService(AuthSessionRepository(session), timedelta(days=1)).issue(
            user_id, device_id
        )
    token = AccessTokenService(config).issue(user_id, device_id, issued.session.id).token
    auth = AuthenticatedSessionService(postgres, AsyncMock(), config)
    try:
        # Last slot retained for existing billing fixtures; no node agent exists.
        yield config, postgres, user_id, device_id, node_id, token, auth, None
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def set_paid(postgres, user_id, end, *, status=SubscriptionStatus.ACTIVE, auto_renew=False):
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user_id)
            .values(
                plan=SubscriptionPlan.PREMIUM,
                status=status,
                auto_renew=auto_renew,
                current_period_start=datetime.now(UTC) - timedelta(days=1),
                current_period_end=end,
            )
        )


@pytest.mark.parametrize("status", [SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED])
@pytest.mark.parametrize("plan", [SubscriptionPlan.PREMIUM, SubscriptionPlan.PLATINUM])
async def test_paid_access_and_expiry_remain_in_me(access_state, status, plan):
    _, postgres, user_id, _, _, token, auth, _ = access_state
    await set_paid(postgres, user_id, datetime.now(UTC) + timedelta(days=1), status=status)
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user_id)
            .values(plan=plan)
        )
    assert (await auth.me(token)).plan is plan
    async with postgres.session() as session, session.begin():
        await session.execute(
            update(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == user_id)
            .values(current_period_end=datetime.now(UTC) - timedelta(seconds=1))
        )
    summary = await auth.me(token)
    assert summary.plan is SubscriptionPlan.FREE
    assert summary.free_seconds_remaining == 3600


async def test_canceled_renewal_constraint_preserves_period(access_state):
    _, postgres, user_id, _, _, _, _, _ = access_state
    with pytest.raises(IntegrityError):
        await set_paid(
            postgres,
            user_id,
            datetime.now(UTC) + timedelta(days=1),
            status=SubscriptionStatus.CANCELED,
            auto_renew=True,
        )
