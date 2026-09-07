"""Auth-session persistence tests against local Compose PostgreSQL or CI."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from prettylisavpn.auth_sessions.domain import InvalidAuthSessionError
from prettylisavpn.auth_sessions.model import AuthSessionRecord
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
    ),
]

SESSION_TTL = timedelta(days=30)


async def create_user(postgres: Postgres, email: str):
    async with postgres.session() as session:
        user = await UserService(UserRepository(session), SubscriptionRepository(session)).create(
            email
        )
        await session.commit()
        return user


async def delete_user(postgres: Postgres, user_id):
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.id == user_id))
        await session.commit()


async def test_persists_only_refresh_token_hash_and_rotates_it():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"auth-session-{uuid4()}@example.com")
    try:
        async with postgres.session() as session:
            service = AuthSessionService(AuthSessionRepository(session), SESSION_TTL)
            issued = await service.issue(user.id, uuid4())
            await session.commit()

        async with postgres.session() as session:
            record = await session.get(AuthSessionRecord, issued.session.id)
            assert record is not None
            assert record.refresh_token_hash == service.hash_refresh_token(issued.refresh_token)
            assert issued.refresh_token.encode() not in record.refresh_token_hash

            rotated = await AuthSessionService(AuthSessionRepository(session), SESSION_TTL).rotate(
                issued.session.id, issued.refresh_token
            )
            await session.commit()

        assert rotated.refresh_token != issued.refresh_token
        assert rotated.session.refresh_token_hash != issued.session.refresh_token_hash
    finally:
        await delete_user(postgres, user.id)
        await postgres.close()


async def test_concurrent_rotation_accepts_old_token_once():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"auth-rotation-{uuid4()}@example.com")
    try:
        async with postgres.session() as session:
            issued = await AuthSessionService(AuthSessionRepository(session), SESSION_TTL).issue(
                user.id, uuid4()
            )
            await session.commit()

        async def rotate() -> bool:
            async with postgres.session() as session:
                try:
                    await AuthSessionService(AuthSessionRepository(session), SESSION_TTL).rotate(
                        issued.session.id, issued.refresh_token
                    )
                except InvalidAuthSessionError:
                    return False
                await session.commit()
                return True

        results = await asyncio.gather(rotate(), rotate())
        assert results.count(True) == 1
        assert results.count(False) == 1
    finally:
        await delete_user(postgres, user.id)
        await postgres.close()


async def test_revokes_all_sessions_for_one_device():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"auth-revoke-{uuid4()}@example.com")
    target_device_id = uuid4()
    other_device_id = uuid4()
    try:
        async with postgres.session() as session:
            service = AuthSessionService(AuthSessionRepository(session), SESSION_TTL)
            target_ids = [
                (await service.issue(user.id, target_device_id)).session.id for _ in range(2)
            ]
            other_id = (await service.issue(user.id, other_device_id)).session.id
            assert await service.revoke_device_sessions(target_device_id) == 2
            await session.commit()

        async with postgres.session() as session:
            records = (
                await session.scalars(
                    select(AuthSessionRecord).where(
                        AuthSessionRecord.id.in_([*target_ids, other_id])
                    )
                )
            ).all()
        revoked_by_id = {record.id: record.revoked_at for record in records}
        assert all(revoked_by_id[session_id] is not None for session_id in target_ids)
        assert revoked_by_id[other_id] is None
    finally:
        await delete_user(postgres, user.id)
        await postgres.close()
