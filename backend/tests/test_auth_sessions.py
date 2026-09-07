from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from prettylisavpn.auth_sessions.domain import AuthSession, InvalidAuthSessionError
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService


def auth_session(*, expires_at: datetime, revoked_at: datetime | None = None) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        id=uuid4(),
        user_id=uuid4(),
        device_id=uuid4(),
        refresh_token_hash=AuthSessionService.hash_refresh_token("current-token"),
        expires_at=expires_at,
        revoked_at=revoked_at,
        created_at=now,
        updated_at=now,
    )


def test_auth_session_requires_sha256_digest():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="SHA-256 digest"):
        AuthSession(
            id=uuid4(),
            user_id=uuid4(),
            device_id=uuid4(),
            refresh_token_hash=b"raw-refresh-token",
            expires_at=now + timedelta(days=1),
            revoked_at=None,
            created_at=now,
            updated_at=now,
        )


async def test_issue_returns_raw_token_once_and_persists_only_hash():
    repository = AsyncMock(spec=AuthSessionRepository)
    repository.add.side_effect = lambda session: session
    service = AuthSessionService(repository, timedelta(days=30))

    issued = await service.issue(uuid4(), uuid4())

    persisted = repository.add.await_args.args[0]
    assert issued.session == persisted
    assert persisted.refresh_token_hash == service.hash_refresh_token(issued.refresh_token)
    assert issued.refresh_token.encode() not in persisted.refresh_token_hash
    assert issued.refresh_token not in repr(issued)


async def test_rotate_replaces_hash_and_expiration():
    repository = AsyncMock(spec=AuthSessionRepository)
    current = auth_session(expires_at=datetime.now(UTC) + timedelta(days=1))
    repository.get_for_update.return_value = current
    service = AuthSessionService(repository, timedelta(days=30))

    rotated = await service.rotate(current.id, "current-token")

    assert rotated.refresh_token != "current-token"
    assert rotated.session.refresh_token_hash == service.hash_refresh_token(rotated.refresh_token)
    assert rotated.session.expires_at > current.expires_at
    repository.rotate.assert_awaited_once_with(
        current.id,
        rotated.session.refresh_token_hash,
        rotated.session.expires_at,
        rotated.session.updated_at,
    )


@pytest.mark.parametrize(
    "session,refresh_token",
    [
        (
            auth_session(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
            "current-token",
        ),
        (
            auth_session(
                expires_at=datetime.now(UTC) + timedelta(days=1),
                revoked_at=datetime.now(UTC),
            ),
            "current-token",
        ),
        (auth_session(expires_at=datetime.now(UTC) + timedelta(days=1)), "wrong-token"),
    ],
)
async def test_rotate_rejects_unusable_session_or_token(session, refresh_token):
    repository = AsyncMock(spec=AuthSessionRepository)
    repository.get_for_update.return_value = session

    with pytest.raises(InvalidAuthSessionError):
        await AuthSessionService(repository, timedelta(days=30)).rotate(session.id, refresh_token)

    repository.rotate.assert_not_awaited()


async def test_revoke_all_sessions_for_device():
    repository = AsyncMock(spec=AuthSessionRepository)
    repository.revoke_for_device.return_value = 3
    device_id = uuid4()

    count = await AuthSessionService(repository, timedelta(days=30)).revoke_device_sessions(
        device_id
    )

    assert count == 3
    assert repository.revoke_for_device.await_args.args[0] == device_id
    assert repository.revoke_for_device.await_args.args[1].tzinfo is UTC


async def test_revoke_session():
    repository = AsyncMock(spec=AuthSessionRepository)
    repository.revoke.return_value = True
    session_id = uuid4()

    revoked = await AuthSessionService(repository, timedelta(days=30)).revoke(session_id)

    assert revoked
    assert repository.revoke.await_args.args[0] == session_id
    assert repository.revoke.await_args.args[1].tzinfo is UTC
