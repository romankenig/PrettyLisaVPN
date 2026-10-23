"""Credential ledger crash/retry/concurrency checks on real PostgreSQL."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from test_vpn_sessions_integration import clean_up, create_dependencies, make_session

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.vpn_sessions.credentials import CredentialLedgerError, VpnCredentialRepository
from prettylisavpn.vpn_sessions.model import VpnCredentialRecord, VpnSessionRecord
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL"),
]


@pytest.fixture
async def ledger():
    postgres = Postgres(Settings())
    user, device, node = await create_dependencies(postgres)
    vpn = make_session(user, device, node)
    async with postgres.session() as db:
        await VpnSessionRepository(db).add(vpn)
        await db.commit()
    now = datetime.now(UTC)
    request = dict(
        credential_id=uuid4(),
        session_id=vpn.id,
        authority_sha256="a" * 64,
        request_sha256="b" * 64,
        expires_at=now + timedelta(minutes=10),
        now=now,
    )

    async def call(method, *args, **kwargs):
        async with postgres.session() as db, db.begin():
            return await getattr(VpnCredentialRepository(db), method)(*args, **kwargs)

    try:
        yield postgres, call, request, node
    finally:
        async with postgres.session() as db:
            await db.execute(
                delete(VpnCredentialRecord).where(VpnCredentialRecord.session_id == vpn.id)
            )
            await db.commit()
        await clean_up(postgres, user, node)
        await postgres.close()


async def test_exact_result_survives_reconnect_and_revocation_requires_ack(ledger):
    _, call, request, node = ledger
    reserved = await call("reserve", **request)
    args = (reserved.id, reserved.session_id)
    # The ledger stores already-verified bytes; signer tests separately verify real X.509.
    issued = await call(
        "record_issued", *args, certificate_pem=b"verified-certificate", now=request["now"]
    )
    assert await call("reserve", **request) == issued
    assert await call("get", *args) == issued
    assert "verified-certificate" not in repr(issued)
    assert (
        await call(
            "record_issued", *args, certificate_pem=b"verified-certificate", now=request["now"]
        )
        == issued
    )
    revoked = await call("revoke", *args, now=request["now"])
    assert revoked.node_removed_at is None
    assert reserved.id in {item.id for item in await call("pending_revocations")}
    with pytest.raises(CredentialLedgerError, match="CREDENTIAL_NOT_ISSUABLE"):
        await call(
            "record_issued", *args, certificate_pem=b"verified-certificate", now=request["now"]
        )
    removed = await call(
        "confirm_removed", *args, vpn_node_id=node, authority_sha256="a" * 64, now=request["now"]
    )
    assert removed.node_removed_at is not None
    assert reserved.id not in {item.id for item in await call("pending_revocations")}
    assert await call("revocation_snapshot", node, "a" * 64) == (removed,)
    assert await call("revocation_snapshot", node, "c" * 64) == ()
    assert await call("revoke", *args, now=request["now"] + timedelta(seconds=1)) == removed
    assert (
        await call(
            "confirm_removed",
            *args,
            vpn_node_id=node,
            authority_sha256="a" * 64,
            now=request["now"] + timedelta(seconds=1),
        )
        == removed
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority_sha256", "c" * 64),
        ("request_sha256", "c" * 64),
        ("expires_at", None),
    ],
)
async def test_same_id_cannot_change_signing_request(ledger, field, value):
    _, call, request, _ = ledger
    original = await call("reserve", **request)
    changed = {**request, field: value or request["expires_at"] + timedelta(seconds=1)}
    with pytest.raises(CredentialLedgerError, match="CREDENTIAL_REQUEST_CONFLICT"):
        await call("reserve", **changed)
    assert await call("get", original.id, original.session_id) == original


async def test_parallel_identical_reservations_have_one_identity(ledger):
    _, call, request, _ = ledger
    rows = await asyncio.gather(*(call("reserve", **request) for _ in range(6)))
    assert all(row == rows[0] for row in rows)


async def test_parallel_conflicting_results_do_not_overwrite_certificate(ledger):
    _, call, request, _ = ledger
    reserved = await call("reserve", **request)
    results = await asyncio.gather(
        *(
            call(
                "record_issued",
                reserved.id,
                reserved.session_id,
                certificate_pem=pem,
                now=request["now"],
            )
            for pem in (b"first-result", b"second-result")
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, CredentialLedgerError) for result in results) == 1
    winner = next(result for result in results if not isinstance(result, Exception))
    assert await call("get", reserved.id, reserved.session_id) == winner


async def test_revoking_unknown_signer_outcome_blocks_late_completion(ledger):
    _, call, request, node = ledger
    reserved = await call("reserve", **request)
    args = reserved.id, reserved.session_id
    revoked = await call("revoke", *args, now=request["now"])
    assert revoked.certificate_pem is None
    assert await call("revocation_snapshot", node, "a" * 64) == (revoked,)
    with pytest.raises(CredentialLedgerError, match="CREDENTIAL_NOT_ISSUABLE"):
        await call("record_issued", *args, certificate_pem=b"late-result", now=request["now"])


@pytest.mark.parametrize("kind", ["no-intent", "wrong-node", "wrong-authority", "wrong-session"])
async def test_removal_ack_is_scoped_and_needs_intent(ledger, kind):
    _, call, request, node = ledger
    reserved = await call("reserve", **request)
    if kind != "no-intent":
        await call("revoke", reserved.id, reserved.session_id, now=request["now"])
    with pytest.raises(CredentialLedgerError):
        await call(
            "confirm_removed",
            reserved.id,
            uuid4() if kind == "wrong-session" else reserved.session_id,
            vpn_node_id=uuid4() if kind == "wrong-node" else node,
            authority_sha256="c" * 64 if kind == "wrong-authority" else "a" * 64,
            now=request["now"],
        )
    assert (await call("get", reserved.id, reserved.session_id)).node_removed_at is None


async def test_rollback_does_not_persist_revocation_intent(ledger):
    postgres, call, request, _ = ledger
    reserved = await call("reserve", **request)
    async with postgres.session() as db:
        await VpnCredentialRepository(db).revoke(
            reserved.id, reserved.session_id, now=request["now"]
        )
        await db.rollback()
    assert await call("get", reserved.id, reserved.session_id) == reserved


async def test_expiry_does_not_mean_node_removal(ledger):
    _, call, request, _ = ledger
    reserved = await call("reserve", **request)
    with pytest.raises(CredentialLedgerError, match="CREDENTIAL_NOT_ISSUABLE"):
        await call(
            "record_issued",
            reserved.id,
            reserved.session_id,
            certificate_pem=b"too-late",
            now=reserved.expires_at,
        )
    revoked = await call("revoke", reserved.id, reserved.session_id, now=reserved.expires_at)
    assert revoked.node_removed_at is None
    assert reserved.id in {item.id for item in await call("pending_revocations")}


async def test_database_guards_partial_issuance_and_retains_session(ledger):
    postgres, call, request, _ = ledger
    reserved = await call("reserve", **request)
    async with postgres.session() as db:
        with pytest.raises(IntegrityError):
            await db.execute(
                update(VpnCredentialRecord)
                .where(VpnCredentialRecord.id == reserved.id)
                .values(issued_at=request["now"])
            )
        await db.rollback()
        with pytest.raises(IntegrityError):
            await db.execute(
                delete(VpnSessionRecord).where(VpnSessionRecord.id == reserved.session_id)
            )
        await db.rollback()
