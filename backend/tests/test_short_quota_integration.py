"""Concurrent device grants and server cleanup use real transactions, mocked nodes."""
# ruff: noqa: F811

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from test_auth_sessions_integration import create_device
from test_client_vpn_integration import pytestmark, vpn_state  # noqa: F401
from test_fleet_integration import fleet_state  # noqa: F401

from prettylisavpn.auth.session_service import AccessIdentity
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.client_vpn import service as service_module
from prettylisavpn.client_vpn import worker as worker_module
from prettylisavpn.client_vpn.domain import ConnectRequest
from prettylisavpn.client_vpn.model import ClientLeaseRecord
from prettylisavpn.client_vpn.quota import ClientQuotaRepository


async def devices(postgres, service, identity, count):
    identities = {"0": identity}
    for i in range(1, count):
        device = await create_device(postgres, identity.user_id)
        async with postgres.session() as session, session.begin():
            auth = await AuthSessionService(
                AuthSessionRepository(session), timedelta(days=1)
            ).issue(identity.user_id, device.id)
        identities[str(i)] = AccessIdentity(identity.user_id, device.id, auth.session.id)

    async def authenticate(token):
        return identities[token]

    service.auth.authenticate.side_effect = authenticate
    return identities


def freeze(monkeypatch):
    class Clock(datetime):
        value = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)

        @classmethod
        def now(cls, tz=None):
            return cls.value

    monkeypatch.setattr(service_module, "datetime", Clock)
    monkeypatch.setattr(worker_module, "datetime", Clock)
    return Clock


async def start(service, token):
    key = base64.b64encode(bytes([int(token) + 1]) * 32).decode()
    return UUID((await service.connect(token, ConnectRequest(public_key=key), uuid4()))["id"])


async def test_five_devices_share_reservations_without_double_spending(vpn_state, monkeypatch):  # noqa: F811
    pg, service, worker, provider, identity = vpn_state
    clock = freeze(monkeypatch)
    await devices(pg, service, identity, 5)
    identifiers = await asyncio.gather(*(start(service, str(i)) for i in range(5)))
    for _ in identifiers:
        assert await worker.tick()
    for i, identifier in enumerate(identifiers):
        assert (await service.get(str(i), identifier, "probe", "1.1.1.1"))["verified"]
    async with pg.session() as session:
        balance = await ClientQuotaRepository(session).display(identity.user_id, clock.value)
        assert balance.running_sessions == 5 and balance.usable_seconds == 3600
        assert balance.available_seconds == 2700
    clock.value += timedelta(seconds=120)
    for _ in identifiers:
        assert await worker.tick()
    # Beyond the 90-second unverified cutoff, confirmed sleeping devices still
    # renew without HTTP keepalives. Five devices consume 5 * 120 seconds.
    async with pg.session() as session:
        assert (
            await ClientQuotaRepository(session).display(identity.user_id, clock.value)
        ).usable_seconds == 3000
    for i, identifier in enumerate(identifiers):
        await service.get(str(i), identifier, "revoke")
    for _ in identifiers:
        assert await worker.tick()
    async with pg.session() as session:
        quota = ClientQuotaRepository(session)
        balance = await quota.display(identity.user_id, clock.value + timedelta(minutes=10))
        assert balance.running_sessions == 0
        assert balance.available_seconds == balance.usable_seconds == 3000
    assert provider.revoke_access.await_count == 5


async def test_unverified_ready_access_is_revoked_and_failed_removal_retried(
    vpn_state,
    monkeypatch,  # noqa: F811
):  # noqa: F811
    pg, service, worker, provider, identity = vpn_state
    clock = freeze(monkeypatch)
    await devices(pg, service, identity, 1)
    identifier = await start(service, "0")
    assert await worker.tick()
    assert not (await service.get("0", identifier, "probe", "9.9.9.9"))["verified"]
    clock.value += timedelta(seconds=91)
    provider.revoke_access.return_value = False
    assert await worker.tick()
    result = await service.get("0", identifier)
    assert result["status"] == "REVOKING" and result["code"] == "VPN_NODE_UNAVAILABLE"
    async with pg.session() as session:
        row = await session.get(ClientLeaseRecord, identifier)
        assert row.verified_at is None and row.removed_at is None
    provider.revoke_access.return_value = True
    clock.value += timedelta(seconds=11)
    assert await worker.tick()
    assert (await service.get("0", identifier))["status"] == "CLOSED"
    async with pg.session() as session:
        assert (
            await ClientQuotaRepository(session).display(identity.user_id, clock.value)
        ).running_sessions == 0


async def test_expired_node_reservation_is_not_renewed_after_worker_outage(vpn_state, monkeypatch):  # noqa: F811
    pg, service, worker, _, identity = vpn_state
    clock = freeze(monkeypatch)
    await devices(pg, service, identity, 1)
    identifier = await start(service, "0")
    assert await worker.tick()
    await service.get("0", identifier, "probe", "1.1.1.1")
    clock.value += timedelta(seconds=181)
    assert await worker.tick()
    assert (await service.get("0", identifier))["code"] == "VPN_RESERVATION_EXPIRED"
    async with pg.session() as session:
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, clock.value
            )
            == 3420
        )


async def test_legacy_grant_keeps_outstanding_node_deadline_during_upgrade(vpn_state, monkeypatch):  # noqa: F811
    pg, service, worker, _, identity = vpn_state
    clock = freeze(monkeypatch)
    await devices(pg, service, identity, 1)
    identifier = await start(service, "0")
    async with pg.session() as session, session.begin():
        row = await session.get(ClientLeaseRecord, identifier)
        row.quota_reserved_until = None
        row.verified_at = clock.value
    assert await worker.tick()
    async with pg.session() as session:
        row = await session.get(ClientLeaseRecord, identifier)
        assert row.quota_reserved_until == clock.value + timedelta(seconds=180)
        assert (
            await ClientQuotaRepository(session).remaining_free_seconds(
                identity.user_id, clock.value
            )
            == 3420
        )
