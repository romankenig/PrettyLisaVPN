"""PostgreSQL-owned issue/revoke lifecycle across the remote node boundary."""

import asyncio
import os
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete
from test_vpn_sessions_integration import clean_up, create_dependencies, make_session

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_nodes.agent import ManagedNodeProfile, NodeAgentUnavailableError
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.managed import (
    ManagedVpnNotFound,
    ManagedVpnService,
    ManagedVpnUnavailable,
)
from prettylisavpn.vpn_sessions.model import ManagedVpnLeaseRecord
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository
from prettylisavpn.vpn_sessions.termination import (
    VpnSessionReconciler,
    VpnSessionTerminationService,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def context():
    pg = Postgres(Settings())
    user, device, node = await create_dependencies(pg)
    vpn = replace(make_session(user, device, node), status=VpnSessionStatus.ACTIVE)
    async with pg.session() as db:
        await VpnSessionRepository(db).add(vpn)
        await db.commit()
    auth = AsyncMock()
    auth.authenticate.return_value = AccessIdentity(
        user_id=user, device_id=device, session_id=uuid4()
    )
    agent = AsyncMock()
    agent.issue_managed = AsyncMock()
    agent.remove_managed = AsyncMock()
    agent.issue_managed.return_value = ManagedNodeProfile(
        port=18443, public_key="a" * 43, server_name="api.prettylisavpn.com", short_id="ab"
    )
    settings = Settings(environment="test", vpn_managed_nodes=[node], vpn_managed_secret="x" * 32)
    service = ManagedVpnService(pg, auth, agent, settings)
    try:
        yield pg, vpn, service, auth, agent, settings
    finally:
        async with pg.session() as db:
            await db.execute(
                delete(ManagedVpnLeaseRecord).where(ManagedVpnLeaseRecord.session_id == vpn.id)
            )
            await db.commit()
        await clean_up(pg, user, node)
        await pg.close()


async def test_retries_share_lease_then_revoke_requires_node_ack(context):
    pg, vpn, service, auth, agent, _ = context
    replies = await asyncio.gather(*(service.issue("token", vpn.id) for _ in range(3)))
    assert all(
        r.profile == replies[0].profile and r.expires_at == replies[0].expires_at for r in replies
    )
    async with pg.session() as db:
        stored = await VpnSessionRepository(db).get(vpn.id)
        assert stored.expires_at == replies[0].expires_at
    terminator = VpnSessionTerminationService(pg, auth, agent)
    agent.remove_managed.side_effect = NodeAgentUnavailableError
    assert not (await terminator.disconnect("token", vpn.id)).cleanup_confirmed
    agent.remove_peer.assert_not_awaited()
    async with pg.session() as db:
        lease = await db.get(ManagedVpnLeaseRecord, vpn.id)
        assert lease.revoked_at is not None and lease.node_removed_at is None
    agent.remove_managed.side_effect = None
    assert (await terminator.disconnect("token", vpn.id)).cleanup_confirmed
    agent.remove_peer.assert_awaited_once()
    with pytest.raises(ManagedVpnNotFound):
        await service.issue("token", vpn.id)


async def test_unknown_issue_outcome_is_durable_and_compensated(context):
    pg, vpn, service, auth, agent, _ = context
    agent.issue_managed.side_effect = NodeAgentUnavailableError
    with pytest.raises(ManagedVpnUnavailable):
        await service.issue("token", vpn.id)
    async with pg.session() as db:
        lease = await db.get(ManagedVpnLeaseRecord, vpn.id)
        assert lease is not None and lease.issued_at is None
    assert (
        await VpnSessionTerminationService(pg, auth, agent).disconnect("token", vpn.id)
    ).cleanup_confirmed
    agent.remove_managed.assert_awaited_once()


async def test_missing_wireguard_peer_does_not_ack_managed_removal(context):
    pg, vpn, service, _, agent, settings = context
    await service.issue("token", vpn.id)
    reconciler = VpnSessionReconciler(pg, agent, settings)
    await reconciler._mark_missing(vpn.id)
    async with pg.session() as db:
        stored = await VpnSessionRepository(db).get(vpn.id)
        assert stored.status == VpnSessionStatus.FAILED and stored.peer_removed_at is None


async def test_foreign_session_and_disabled_node_never_issue(context):
    _, vpn, service, auth, agent, _ = context
    auth.authenticate.return_value = AccessIdentity(
        user_id=uuid4(), device_id=vpn.device_id, session_id=uuid4()
    )
    with pytest.raises(ManagedVpnNotFound):
        await service.issue("token", vpn.id)
    agent.issue_managed.assert_not_awaited()
    auth.authenticate.return_value = AccessIdentity(
        user_id=vpn.user_id, device_id=vpn.device_id, session_id=uuid4()
    )
    service.nodes.clear()
    with pytest.raises(ManagedVpnUnavailable):
        await service.issue("token", vpn.id)
    agent.issue_managed.assert_not_awaited()
