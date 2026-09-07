"""Device persistence tests against local Compose PostgreSQL or CI."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import (
    Device,
    DeviceLimitReachedError,
    DevicePlatform,
    DeviceStatus,
)
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import MAX_ACTIVE_DEVICES, DeviceService
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User
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


async def create_user(postgres: Postgres, email: str) -> User:
    async with postgres.session() as session:
        user = await UserService(UserRepository(session), SubscriptionRepository(session)).create(
            email
        )
        await session.commit()
        return user


async def delete_user(postgres: Postgres, user_id) -> None:
    async with postgres.session() as session:
        await session.execute(delete(UserRecord).where(UserRecord.id == user_id))
        await session.commit()


async def test_device_persistence_and_installation_uniqueness():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"device-{uuid4()}@example.com")
    installation_id = uuid4()
    try:
        async with postgres.session() as session:
            created = await DeviceService(DeviceRepository(session)).register(
                user.id, installation_id, DevicePlatform.WINDOWS, "Laptop"
            )
            await session.commit()

        async with postgres.session() as session:
            loaded = await session.get(DeviceRecord, created.id)
            assert loaded is not None
            assert loaded.user_id == user.id
            assert loaded.installation_id == installation_id
            assert loaded.status is DeviceStatus.ACTIVE
            assert loaded.created_at.utcoffset().total_seconds() == 0
            assert loaded.updated_at.utcoffset().total_seconds() == 0

        now = datetime.now(UTC)
        duplicate = Device(
            id=uuid4(),
            user_id=user.id,
            installation_id=installation_id,
            platform=DevicePlatform.LINUX,
            device_name="Other name",
            status=DeviceStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            revoked_at=None,
        )
        with pytest.raises(IntegrityError):
            async with postgres.session() as session:
                await DeviceRepository(session).add(duplicate)
    finally:
        await delete_user(postgres, user.id)
        await postgres.close()


async def test_concurrent_registration_never_exceeds_active_device_limit():
    postgres = Postgres(Settings())
    user = await create_user(postgres, f"device-limit-{uuid4()}@example.com")
    try:
        async with postgres.session() as session:
            service = DeviceService(DeviceRepository(session))
            for number in range(MAX_ACTIVE_DEVICES - 1):
                await service.register(
                    user.id,
                    uuid4(),
                    DevicePlatform.ANDROID,
                    f"Phone {number}",
                )
            await session.commit()

        async def register_one(name: str) -> bool:
            async with postgres.session() as session:
                try:
                    await DeviceService(DeviceRepository(session)).register(
                        user.id, uuid4(), DevicePlatform.IOS, name
                    )
                except DeviceLimitReachedError:
                    return False
                await session.commit()
                return True

        results = await asyncio.gather(register_one("Phone A"), register_one("Phone B"))
        assert results.count(True) == 1
        assert results.count(False) == 1

        async with postgres.session() as session:
            active_count = await session.scalar(
                select(func.count(DeviceRecord.id)).where(
                    DeviceRecord.user_id == user.id,
                    DeviceRecord.status == DeviceStatus.ACTIVE,
                )
            )
        assert active_count == MAX_ACTIVE_DEVICES
    finally:
        await delete_user(postgres, user.id)
        await postgres.close()
