"""User persistence tests against local Compose PostgreSQL or CI."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
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


async def test_user_persists_with_utc_timestamps():
    postgres = Postgres(Settings())
    email = f"persistence-{uuid4()}@example.com"
    try:
        async with postgres.session() as session:
            created = await UserService(UserRepository(session)).create(email)
            await session.commit()

        async with postgres.session() as session:
            loaded = await UserRepository(session).get_by_email(f"  {email.upper()} ")

        assert loaded == created
        assert loaded is not None
        assert loaded.created_at.utcoffset().total_seconds() == 0
        assert loaded.updated_at.utcoffset().total_seconds() == 0
    finally:
        async with postgres.session() as session:
            await session.execute(delete(UserRecord).where(UserRecord.email == email))
            await session.commit()
        await postgres.close()


async def test_normalized_email_is_unique():
    postgres = Postgres(Settings())
    local_part = f"unique-{uuid4()}"
    normalized_email = f"{local_part}@example.com"
    try:
        async with postgres.session() as session:
            await UserService(UserRepository(session)).create(f"  {local_part}@EXAMPLE.COM ")
            await session.commit()

        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                await UserService(UserRepository(session)).create(normalized_email)
    finally:
        async with postgres.session() as session:
            await session.execute(delete(UserRecord).where(UserRecord.email == normalized_email))
            await session.commit()
        await postgres.close()
