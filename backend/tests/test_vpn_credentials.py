from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from prettylisavpn.vpn_sessions.credentials import CredentialLedgerError, VpnCredentialRepository


@pytest.mark.parametrize(
    "kind", ["nil", "naive", "expired", "too-long", "bad-authority", "bad-request"]
)
async def test_invalid_reservation_is_rejected_before_database_access(kind):
    db = AsyncMock()
    now = datetime.now(UTC)
    args = dict(
        credential_id=uuid4(),
        session_id=uuid4(),
        authority_sha256="a" * 64,
        request_sha256="b" * 64,
        now=now,
        expires_at=now + timedelta(minutes=10),
    )
    if kind == "nil":
        args["credential_id"] = UUID(int=0)
    elif kind == "naive":
        args["now"] = now.replace(tzinfo=None)
    elif kind == "expired":
        args["expires_at"] = now
    elif kind == "too-long":
        args["expires_at"] = now + timedelta(hours=2)
    else:
        args["authority_sha256" if kind == "bad-authority" else "request_sha256"] = "bad"
    with pytest.raises(CredentialLedgerError):
        await VpnCredentialRepository(db).reserve(**args)
    assert not db.mock_calls


@pytest.mark.parametrize("limit", [0, -1, 1001])
async def test_recovery_batch_must_be_bounded(limit):
    db = AsyncMock()
    with pytest.raises(CredentialLedgerError, match="INVALID_LIMIT"):
        await VpnCredentialRepository(db).pending_revocations(limit=limit)
    assert not db.mock_calls
