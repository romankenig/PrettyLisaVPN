"""Real PostgreSQL contract checks; node operations are explicitly mocked."""

import os
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from prettylisavpn.auth.session_service import AuthenticatedSessionService
from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan, SubscriptionStatus
from prettylisavpn.subscriptions.model import SubscriptionRecord
from prettylisavpn.vpn_nodes.agent import NodeAgentUnavailableError
from prettylisavpn.vpn_nodes.model import VpnNodeRecord
from prettylisavpn.vpn_nodes.selection import NodeSelectionRequest
from prettylisavpn.vpn_sessions.connection import FreeDailyLimitReachedError, VpnConnectionService, VpnSetupFailedError
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.termination import VpnSessionReconciler, VpnSessionTerminationService
from uuid import uuid4
from test_vpn_sessions_integration import clean_up, create_dependencies, public_key

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL")]


@pytest.fixture
async def access_state():
    config = Settings(_env_file=None, otp_hmac_secret="subscription-access-integration-secret-32-characters")
    postgres = Postgres(config)
    user_id, device_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session, session.begin():
        issued = await AuthSessionService(AuthSessionRepository(session), timedelta(days=1)).issue(user_id, device_id)
    token = AccessTokenService(config).issue(user_id, device_id, issued.session.id).token
    auth = AuthenticatedSessionService(postgres, AsyncMock(), config)
    agent = AsyncMock()
    agent.peer_exists.return_value = True
    try:
        yield config, postgres, user_id, device_id, node_id, token, auth, agent
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def set_paid(postgres, user_id, end, *, status=SubscriptionStatus.ACTIVE, auto_renew=False):
    async with postgres.session() as session, session.begin():
        await session.execute(update(SubscriptionRecord).where(SubscriptionRecord.user_id == user_id).values(plan=SubscriptionPlan.PREMIUM, status=status, auto_renew=auto_renew, current_period_start=datetime.now(UTC) - timedelta(days=1), current_period_end=end))


@pytest.mark.parametrize("status", [SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELED])
@pytest.mark.parametrize("plan", [SubscriptionPlan.PREMIUM, SubscriptionPlan.PLATINUM])
async def test_me_countries_and_vpn_share_paid_access_and_expiry(access_state, status, plan):
    config, postgres, user_id, device_id, node_id, token, auth, agent = access_state
    end = datetime.now(UTC) + timedelta(days=1)
    await set_paid(postgres, user_id, end, status=status)
    async with postgres.session() as session, session.begin():
        await session.execute(update(SubscriptionRecord).where(SubscriptionRecord.user_id == user_id).values(plan=plan))
    async with postgres.session() as session, session.begin():
        await session.execute(update(VpnNodeRecord).where(VpnNodeRecord.id == node_id).values(is_available_for_free=False))
    dependency = AsyncMock()
    dependency.ping.return_value = True
    app = create_app(config, postgres=postgres, valkey=dependency, product_events=AsyncMock(), node_agent=agent, node_health_monitor=AsyncMock(), vpn_session_reconciler=AsyncMock(), support_worker=AsyncMock())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + token}) as client:
            me = (await client.get("/me")).json()
            assert me["plan"] == plan.value
            assert me["subscription"]["auto_renew"] is False
            assert me["subscription"]["paid_until"] is not None
            assert me["entitlements"]["vpn_session_limit_seconds"] is None
            assert me["entitlements"]["free_nodes_only"] is False
            assert (await client.get("/vpn/countries")).json()["autopilot"]["available"]
            created = await client.post("/vpn/sessions", json={"mode": "AUTO", "public_key": public_key(80)})
            assert created.status_code == 200, created.text
            assert created.json()["expires_at"] is not None
            expired_at = datetime.now(UTC) - timedelta(microseconds=1)
            await set_paid(postgres, user_id, expired_at, status=status)
            assert (await client.get("/me")).json()["plan"] == "FREE"
            assert not (await client.get("/vpn/countries")).json()["autopilot"]["available"]
            assert (await client.get("/vpn/sessions/current")).json()["session"] is None
            denied = await client.post("/vpn/sessions", json={"mode": "COUNTRY", "country_code": "DE", "public_key": public_key(81)})
            assert denied.status_code == 409
            assert denied.json()["error"]["code"] == "COUNTRY_UNAVAILABLE"
    async with postgres.session() as session:
        current = (await VpnSessionRepository(session).list_by_user(user_id))[0]
    assert current.status is VpnSessionStatus.EXPIRED
    assert current.peer_removed_at is None
    agent.remove_peer.side_effect = NodeAgentUnavailableError
    await VpnSessionReconciler(postgres, agent, config).run_once()
    async with postgres.session() as session:
        assert (await VpnSessionRepository(session).get(current.id)).peer_removed_at is None
    agent.remove_peer.side_effect = None
    await VpnSessionReconciler(postgres, agent, config).run_once()
    await VpnSessionReconciler(postgres, agent, config).run_once()
    assert agent.remove_peer.await_count == 2
    async with postgres.session() as session:
        assert (await VpnSessionRepository(session).get(current.id)).peer_removed_at is not None


async def test_renewal_extends_existing_and_legacy_sessions_without_resurrecting_terminal_rows(access_state):
    config, postgres, user_id, device_id, node_id, token, auth, agent = access_state
    end = datetime.now(UTC) + timedelta(days=1)
    await set_paid(postgres, user_id, end)
    active = await VpnConnectionService(postgres, auth, agent, config).connect(token, NodeSelectionRequest.auto(), public_key(82))
    async with postgres.session() as session, session.begin():
        repository = VpnSessionRepository(session)
        row = await repository.get(active.session_id)
        await repository.update(replace(row, expires_at=None))
    new_end = end + timedelta(days=30)
    await set_paid(postgres, user_id, new_end, auto_renew=True)
    await VpnSessionReconciler(postgres, agent, config).run_once()
    async with postgres.session() as session, session.begin():
        repository = VpnSessionRepository(session)
        current = await repository.get(active.session_id)
        assert current.expires_at == new_end
        assert current.status is VpnSessionStatus.ACTIVE
        await repository.update(replace(current, status=VpnSessionStatus.FAILED))
    await VpnSessionReconciler(postgres, agent, config).run_once()
    async with postgres.session() as session:
        assert (await VpnSessionRepository(session).get(active.session_id)).status is VpnSessionStatus.FAILED


async def test_expiration_during_provisioning_compensates_peer(access_state):
    config, postgres, user_id, device_id, node_id, token, auth, agent = access_state
    end = datetime.now(UTC) + timedelta(days=1)
    await set_paid(postgres, user_id, end)
    service = VpnConnectionService(postgres, auth, agent, config)
    original = service._activate
    async def expire_before_activate(pending, node):
        await set_paid(postgres, user_id, datetime.now(UTC) - timedelta(microseconds=1))
        return await original(pending, node)
    service._activate = expire_before_activate
    with pytest.raises(VpnSetupFailedError):
        await service.connect(token, NodeSelectionRequest.auto(), public_key(83))
    agent.add_peer.assert_not_awaited()
    agent.remove_peer.assert_awaited_once()


async def test_canceled_renewal_constraint_preserves_period(access_state):
    _, postgres, user_id, _, _, _, _, _ = access_state
    with pytest.raises(IntegrityError):
        await set_paid(postgres, user_id, datetime.now(UTC) + timedelta(days=1), status=SubscriptionStatus.CANCELED, auto_renew=True)


async def test_free_hour_is_reserved_across_devices_and_unused_time_returns_after_disconnect(access_state):
    config, postgres, user_id, device_id, node_id, token, auth, agent = access_state
    async with postgres.session() as session, session.begin():
        second = await DeviceService(DeviceRepository(session)).register(user_id, uuid4(), DevicePlatform.ANDROID, "Daily quota device")
    other_auth = AsyncMock()
    other_auth.authenticate.return_value = AccessIdentity(user_id, second.id, uuid4())
    first_service = VpnConnectionService(postgres, auth, agent, config)
    second_service = VpnConnectionService(postgres, other_auth, agent, config)
    results = await asyncio.gather(first_service.connect(token, NodeSelectionRequest.auto(), public_key(85)), second_service.connect("other", NodeSelectionRequest.auto(), public_key(86)), return_exceptions=True)
    assert sum(isinstance(r, FreeDailyLimitReachedError) for r in results) == 1
    winner = next(r for r in results if not isinstance(r, Exception))
    winner_auth = auth if results[0] is winner else other_auth
    assert winner.expires_at is not None
    now = datetime.now(UTC)
    assert 0 < (winner.expires_at - now).total_seconds() <= 3600
    assert winner.expires_at <= now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    async with postgres.session() as session:
        assert await VpnSessionRepository(session).remaining_free_seconds(user_id, now) <= 0
    termination = VpnSessionTerminationService(postgres, winner_auth, agent)
    await termination.disconnect(token, winner.session_id)
    await termination.disconnect(token, winner.session_id)
    async with postgres.session() as session:
        assert await VpnSessionRepository(session).remaining_free_seconds(user_id, datetime.now(UTC)) >= 3590
        tomorrow = now + timedelta(days=1)
        assert await VpnSessionRepository(session).remaining_free_seconds(user_id, tomorrow) == 3600


async def test_failed_free_provisioning_does_not_spend_daily_budget(access_state):
    config, postgres, user_id, _, _, token, auth, agent = access_state
    agent.add_peer.side_effect = NodeAgentUnavailableError
    with pytest.raises(VpnSetupFailedError):
        await VpnConnectionService(postgres, auth, agent, config).connect(token, NodeSelectionRequest.auto(), public_key(87))
    async with postgres.session() as session:
        assert await VpnSessionRepository(session).remaining_free_seconds(user_id, datetime.now(UTC)) == 3600
