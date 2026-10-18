"""Device login timestamps and revocation/peer races against real PostgreSQL."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from test_vpn_sessions_integration import clean_up, create_dependencies, public_key

from prettylisavpn.auth.service import InvalidOtpError, LoginService
from prettylisavpn.auth.session_service import AccessIdentity, AuthenticatedSessionService
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform, DeviceStatus
from prettylisavpn.devices.management import DeviceManagementService, DeviceNotFoundError
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.main import create_app
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.users.model import UserRecord
from prettylisavpn.vpn_nodes.agent import NodeAgentUnavailableError
from prettylisavpn.vpn_nodes.selection import NodeSelectionRequest
from prettylisavpn.vpn_sessions.connection import (
    VpnConnectionService,
    VpnSetupFailedError,
    VpnUnavailableError,
)
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.service import DeviceAlreadyHasLiveVpnSessionError
from prettylisavpn.vpn_sessions.termination import VpnSessionReconciler

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Needs PostgreSQL"),
]


@pytest.fixture
async def state():
    config = Settings(_env_file=None)
    postgres = Postgres(config)
    user_id, current_id, node_id = await create_dependencies(postgres)
    async with postgres.session() as session:
        target = await DeviceService(DeviceRepository(session)).register(
            user_id, uuid4(), DevicePlatform.ANDROID, "Target"
        )
        await session.commit()
    auth = AsyncMock()
    auth.authenticate.return_value = AccessIdentity(user_id, current_id, uuid4())
    agent = AsyncMock()
    agent.peer_exists.return_value = True
    events = AsyncMock()
    management = DeviceManagementService(postgres, auth, events, config, agent)
    try:
        yield (
            postgres,
            config,
            user_id,
            current_id,
            node_id,
            target,
            auth,
            agent,
            events,
            management,
        )
    finally:
        await clean_up(postgres, user_id, node_id)
        await postgres.close()


async def connect_target(state, key=71):
    postgres, config, user_id, _, _, target, _, agent, _, _ = state
    auth = AsyncMock()
    auth.authenticate.return_value = AccessIdentity(user_id, target.id, uuid4())
    connection = VpnConnectionService(postgres, auth, agent, config)
    return connection, await connection.connect(
        "target", NodeSelectionRequest.auto(), public_key(key)
    )


async def persisted(postgres, session_id):
    async with postgres.session() as session:
        return await VpnSessionRepository(session).get(session_id)


async def test_duplicate_connect_preserves_live_session_and_conflict(state):
    _, _, _, _, _, _, _, agent, _, _ = state
    connection, transport = await connect_target(state, 78)
    for key in (78, 80):
        with pytest.raises(DeviceAlreadyHasLiveVpnSessionError):
            await connection.connect("target", NodeSelectionRequest.auto(), public_key(key))
    assert (await persisted(state[0], transport.session_id)).status is VpnSessionStatus.ACTIVE
    agent.add_peer.assert_awaited_once()
    agent.remove_peer.assert_not_awaited()


async def test_record_device_api_evidence_with_simulated_otp(state):
    """Capture actual HTTP responses; only the CI runner may export the test email."""
    postgres, config, user_id, current_id, _, target, _, agent, _, _ = state
    evidence_path = os.getenv("DEVICE_BACKEND_EVIDENCE_PATH")
    if evidence_path:
        assert os.getenv("GITHUB_ACTIONS") == "true"
        assert "127.0.0.1" in config.postgres_url.get_secret_value()
    email = "kenromka@yandex.com" if evidence_path else f"evidence-{uuid4()}@example.com"
    async with postgres.session() as session:
        user = await session.get(UserRecord, user_id)
        user.email = email
        devices = DeviceService(DeviceRepository(session))
        current = await DeviceRepository(session).get(current_id)
        await devices.register(user_id, target.installation_id, target.platform, "Android phone")
        await session.commit()
    _, vpn = await connect_target(state, 79)
    otp = AsyncMock()
    otp.verify.return_value = True
    cache = AsyncMock()
    app = create_app(
        config,
        postgres=postgres,
        valkey=cache,
        otp_service=otp,
        product_events=AsyncMock(),
        node_agent=agent,
        node_health_monitor=AsyncMock(),
        vpn_session_reconciler=AsyncMock(),
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = {
                "email": email,
                "code": "123456",
                "installation_id": str(current.installation_id),
                "platform": "WINDOWS",
                "device_name": "Windows device",
            }
            first = await client.post("/auth/verify-otp", json=body)
            second = await client.post("/auth/verify-otp", json=body)
            assert first.status_code == second.status_code == 200
            assert (
                second.json()["device"]["last_login_at"] > first.json()["device"]["last_login_at"]
            )
            headers = {"Authorization": "Bearer " + second.json()["access_token"]}
            before = await client.get("/devices", headers=headers)
            assert before.status_code == 200
            rows = before.json()
            assert next(row for row in rows if row["is_current"])["last_login_at"] is not None
            assert next(row for row in rows if not row["is_current"])["last_login_at"] is None
            revoked = await client.delete(f"/devices/{target.id}", headers=headers)
            repeat = await client.delete(f"/devices/{target.id}", headers=headers)
            assert revoked.status_code == repeat.status_code == 200
            assert revoked.json() == repeat.json()
            row = await persisted(postgres, vpn.session_id)
            assert row.status is VpnSessionStatus.DISCONNECTED and row.peer_removed_at is not None
            after = await client.get("/devices", headers=headers)
            version = await client.get("/version")
            assert after.status_code == version.status_code == 200
            if evidence_path:
                path = Path(evidence_path)
                await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
                await asyncio.to_thread(
                    path.write_text,
                    json.dumps(
                        {
                            "source_sha": os.getenv("PR_HEAD_SHA", os.getenv("GITHUB_SHA")),
                            "provenance": (
                                "Actual ASGI HTTP responses and PostgreSQL "
                                "in disposable CI database"
                            ),
                            "auth_simulated": True,
                            "node_agent_simulated": True,
                            "live_account_accessed": False,
                            "account_email": email,
                            "user_id": str(user_id),
                            "devices": rows,
                            "revoked_response": revoked.json(),
                            "after_revoke": after.json(),
                            "vpn_disconnected": True,
                            "peer_removal_acknowledged": True,
                            "version": version.json(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )


async def test_successful_otp_is_the_only_login_timestamp_update(state):
    postgres, config, user_id, _, _, target, _, _, _, _ = state
    async with postgres.session() as session:
        from prettylisavpn.users.repository import UserRepository

        user = await UserRepository(session).get_by_id(user_id)
    otp = AsyncMock()
    otp.verify.return_value = True
    login = LoginService(otp, postgres, AsyncMock(), config)
    first = await login.verify_otp(
        user.email, "123456", target.installation_id, target.platform, target.device_name
    )
    assert first.device.last_login_at == first.auth_session.session.created_at
    second = await login.verify_otp(
        user.email, "123456", target.installation_id, target.platform, target.device_name
    )
    assert second.device.last_login_at > first.device.last_login_at
    assert second.device.created_at == target.created_at
    auth = AuthenticatedSessionService(postgres, AsyncMock(), config)
    await auth.refresh(second.auth_session.session.id, second.auth_session.refresh_token)
    otp.verify.return_value = False
    with pytest.raises(InvalidOtpError):
        await login.verify_otp(
            user.email, "000000", target.installation_id, target.platform, "Rename attempt"
        )
    async with postgres.session() as session:
        devices = DeviceService(DeviceRepository(session))
        renamed = await devices.register(
            user_id, target.installation_id, target.platform, "Renamed"
        )
        await session.commit()
    assert renamed.last_login_at == second.device.last_login_at


async def test_login_timestamp_rolls_back_if_transaction_cannot_commit(state, monkeypatch):
    postgres, config, user_id, _, _, target, _, _, _, _ = state
    from prettylisavpn.auth.service import LoginPersistenceError
    from prettylisavpn.users.repository import UserRepository

    async with postgres.session() as session:
        user = await UserRepository(session).get_by_id(user_id)
    original = DeviceRepository.update

    async def fail_after_update(self, device):
        await original(self, device)
        raise SQLAlchemyError("simulated persistence failure")

    monkeypatch.setattr(DeviceRepository, "update", fail_after_update)
    otp = AsyncMock()
    otp.verify.return_value = True
    with pytest.raises(LoginPersistenceError):
        await LoginService(otp, postgres, AsyncMock(), config).verify_otp(
            user.email, "123456", target.installation_id, target.platform, target.device_name
        )
    async with postgres.session() as session:
        device = await DeviceRepository(session).get(target.id)
    assert device.last_login_at is None


async def test_repeated_concurrent_revoke_terminates_vpn_and_auth_once(state):
    postgres, config, user_id, _, _, target, _, agent, events, management = state
    _, transport = await connect_target(state)
    async with postgres.session() as session:
        for _ in range(2):
            await AuthSessionService(AuthSessionRepository(session), timedelta(days=1)).issue(
                user_id, target.id
            )
        await session.commit()
    first, duplicate = await asyncio.gather(
        management.revoke_device("current", target.id),
        management.revoke_device("current", target.id),
    )
    assert first.device.revoked_at == duplicate.device.revoked_at
    assert first.device.status is DeviceStatus.REVOKED
    row = await persisted(postgres, transport.session_id)
    assert row.status is VpnSessionStatus.DISCONNECTED
    assert row.peer_removed_at is not None
    agent.remove_peer.assert_awaited_once()
    events.record.assert_awaited_once_with(
        ProductEventName.DEVICE_REVOKED, user_id=user_id, device_id=target.id
    )
    async with postgres.session() as session:
        sessions = list(
            await session.scalars(
                select(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id)
            )
        )
    assert all(item.revoked_at is not None for item in sessions if item.device_id == target.id)


async def test_node_outage_keeps_cleanup_and_address_until_reconciler_recovers(state):
    postgres, config, user_id, _, _, target, _, agent, _, management = state
    _, transport = await connect_target(state)
    agent.remove_peer.side_effect = NodeAgentUnavailableError
    result = await management.revoke_device("current", target.id)
    assert result.device.status is DeviceStatus.REVOKED
    row = await persisted(postgres, transport.session_id)
    assert row.status is VpnSessionStatus.DISCONNECTED and row.peer_removed_at is None
    async with postgres.session() as session:
        assert row.allocated_client_ipv4 in await VpnSessionRepository(
            session
        ).list_live_allocated_ipv4(datetime.now(UTC))
        await DeviceService(DeviceRepository(session)).register(
            user_id, target.installation_id, target.platform, target.device_name
        )
        await session.commit()
    auth = AsyncMock()
    auth.authenticate.return_value = AccessIdentity(user_id, target.id, uuid4())
    connection = VpnConnectionService(postgres, auth, agent, config)
    with pytest.raises(VpnUnavailableError):
        await connection.connect("reauthenticated", NodeSelectionRequest.auto(), public_key(71))
    agent.remove_peer.side_effect = None
    await VpnSessionReconciler(postgres, agent, config).run_once()
    row = await persisted(postgres, transport.session_id)
    assert row.peer_removed_at is not None
    count = agent.remove_peer.await_count
    await VpnSessionReconciler(postgres, agent, config).run_once()
    assert agent.remove_peer.await_count == count
    await connection.connect("reauthenticated", NodeSelectionRequest.auto(), public_key(71))


async def test_foreign_or_unknown_device_never_changes_vpn_or_calls_node(state):
    postgres, _, _, _, _, target, auth, agent, _, management = state
    _, transport = await connect_target(state)
    agent.remove_peer.reset_mock()
    from prettylisavpn.subscriptions.repository import SubscriptionRepository
    from prettylisavpn.users.repository import UserRepository
    from prettylisavpn.users.service import UserService

    async with postgres.session() as session:
        other = await UserService(UserRepository(session), SubscriptionRepository(session)).create(
            f"foreign-{uuid4()}@example.com"
        )
        other_user, other_device, other_node = other.id, uuid4(), uuid4()
        await session.commit()
    auth.authenticate.return_value = AccessIdentity(other_user, other_device, uuid4())
    try:
        for device_id in (target.id, uuid4()):
            with pytest.raises(DeviceNotFoundError):
                await management.revoke_device("foreign", device_id)
        assert (await persisted(postgres, transport.session_id)).status is VpnSessionStatus.ACTIVE
        agent.remove_peer.assert_not_awaited()
    finally:
        await clean_up(postgres, other_user, other_node)


async def test_revoke_waits_for_inflight_node_add_then_removes_peer(state):
    postgres, _, _, _, _, target, _, agent, _, management = state
    entered, release = asyncio.Event(), asyncio.Event()

    async def add(*args):
        entered.set()
        await release.wait()

    agent.add_peer.side_effect = add
    connect = asyncio.create_task(connect_target(state, 72))
    await asyncio.wait_for(entered.wait(), 2)
    revoke = asyncio.create_task(management.revoke_device("current", target.id))
    await asyncio.sleep(0.05)
    assert not revoke.done()
    release.set()
    _, transport = await connect
    await revoke
    row = await persisted(postgres, transport.session_id)
    assert row.status is VpnSessionStatus.DISCONNECTED and row.peer_removed_at is not None
    agent.remove_peer.assert_awaited_once()


async def test_revoke_before_activation_does_not_add_or_resurrect_peer(state, monkeypatch):
    postgres, _, _, _, _, target, _, agent, _, management = state
    entered, release = asyncio.Event(), asyncio.Event()
    activate = VpnConnectionService._activate

    async def paused(self, pending, node):
        entered.set()
        await release.wait()
        return await activate(self, pending, node)

    monkeypatch.setattr(VpnConnectionService, "_activate", paused)
    connect = asyncio.create_task(connect_target(state, 73))
    await asyncio.wait_for(entered.wait(), 2)
    await management.revoke_device("current", target.id)
    release.set()
    with pytest.raises(VpnSetupFailedError):
        await connect
    agent.add_peer.assert_not_awaited()
    async with postgres.session() as session:
        rows = await VpnSessionRepository(session).list_by_user(target.user_id)
    assert all(row.status is VpnSessionStatus.DISCONNECTED for row in rows)


async def test_cleanup_retries_when_remote_delete_succeeds_but_ack_write_fails(state, monkeypatch):
    postgres, config, _, _, _, target, _, agent, _, management = state
    _, transport = await connect_target(state, 74)
    original = VpnSessionRepository.update

    async def fail_ack(self, row):
        if row.peer_removed_at is not None:
            raise SQLAlchemyError("simulated acknowledgement failure")
        return await original(self, row)

    with monkeypatch.context() as patch:
        patch.setattr(VpnSessionRepository, "update", fail_ack)
        await management.revoke_device("current", target.id)
    row = await persisted(postgres, transport.session_id)
    assert row.peer_removed_at is None
    await VpnSessionReconciler(postgres, agent, config).run_once()
    assert (await persisted(postgres, transport.session_id)).peer_removed_at is not None
    assert agent.remove_peer.await_count == 2
