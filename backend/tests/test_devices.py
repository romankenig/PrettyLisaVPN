from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from prettylisavpn.devices.domain import (
    Device,
    DeviceLimitReachedError,
    DevicePlatform,
    DeviceStatus,
    DeviceUserNotFoundError,
)
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import MAX_ACTIVE_DEVICES, DeviceService


def device(*, status: DeviceStatus = DeviceStatus.ACTIVE) -> Device:
    now = datetime.now(UTC)
    return Device(
        id=uuid4(),
        user_id=uuid4(),
        installation_id=uuid4(),
        platform=DevicePlatform.WINDOWS,
        device_name="Laptop",
        status=status,
        created_at=now,
        updated_at=now,
        revoked_at=now if status is DeviceStatus.REVOKED else None,
    )


def test_device_model_contains_no_hardware_identifiers():
    assert set(DeviceRecord.__table__.columns.keys()) == {
        "id",
        "user_id",
        "installation_id",
        "platform",
        "device_name",
        "status",
        "created_at",
        "updated_at",
        "revoked_at",
        "last_login_at",
    }


async def test_registers_normalized_active_device():
    repository = AsyncMock(spec=DeviceRepository)
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = None
    repository.count_active.return_value = 0
    repository.add.side_effect = lambda value: value

    registered = await DeviceService(repository).register(
        uuid4(), uuid4(), DevicePlatform.LINUX, "  Work laptop  "
    )

    assert registered.device_name == "Work laptop"
    assert registered.status is DeviceStatus.ACTIVE
    assert registered.revoked_at is None
    repository.add.assert_awaited_once_with(registered)


async def test_rejects_registration_for_missing_user():
    repository = AsyncMock(spec=DeviceRepository)
    repository.lock_user.return_value = False

    with pytest.raises(DeviceUserNotFoundError):
        await DeviceService(repository).register(uuid4(), uuid4(), DevicePlatform.ANDROID, "Phone")

    repository.count_active.assert_not_awaited()
    repository.add.assert_not_awaited()


async def test_rejects_sixth_active_device():
    repository = AsyncMock(spec=DeviceRepository)
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = None
    repository.count_active.return_value = MAX_ACTIVE_DEVICES

    with pytest.raises(DeviceLimitReachedError):
        await DeviceService(repository).register(uuid4(), uuid4(), DevicePlatform.IOS, "Phone")

    repository.add.assert_not_awaited()


async def test_existing_active_installation_is_idempotent():
    repository = AsyncMock(spec=DeviceRepository)
    existing = device()
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = existing

    registered = await DeviceService(repository).register(
        existing.user_id,
        existing.installation_id,
        existing.platform,
        existing.device_name,
    )

    assert registered == existing
    repository.count_active.assert_not_awaited()
    repository.add.assert_not_awaited()
    repository.update.assert_not_awaited()


async def test_revoked_installation_can_be_reactivated_below_limit():
    repository = AsyncMock(spec=DeviceRepository)
    existing = device(status=DeviceStatus.REVOKED)
    repository.lock_user.return_value = True
    repository.get_by_installation_for_update.return_value = existing
    repository.count_active.return_value = MAX_ACTIVE_DEVICES - 1
    repository.update.side_effect = lambda value: value

    registered = await DeviceService(repository).register(
        existing.user_id,
        existing.installation_id,
        DevicePlatform.MACOS,
        "MacBook",
    )

    assert registered.id == existing.id
    assert registered.status is DeviceStatus.ACTIVE
    assert registered.revoked_at is None
    assert registered.platform is DevicePlatform.MACOS


async def test_revoke_marks_device_revoked():
    repository = AsyncMock(spec=DeviceRepository)
    existing = device()
    repository.get_for_update.return_value = existing
    repository.update.side_effect = lambda value: value

    assert await DeviceService(repository).revoke(existing.id)

    revoked = repository.update.await_args.args[0]
    assert revoked.status is DeviceStatus.REVOKED
    assert revoked.revoked_at == revoked.updated_at


def test_login_timestamp_requires_timezone_and_normalizes_utc():
    from dataclasses import replace
    from datetime import timedelta, timezone

    value = device()
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(value, last_login_at=datetime(2026, 10, 18))
    local = datetime(2026, 10, 18, 12, tzinfo=timezone(timedelta(hours=3)))
    assert replace(value, last_login_at=local).last_login_at == datetime(
        2026, 10, 18, 9, tzinfo=UTC
    )


async def test_revocation_preserves_known_login_timestamp():
    from dataclasses import replace

    existing = device()
    existing = replace(existing, last_login_at=existing.created_at)
    repository = AsyncMock(spec=DeviceRepository)
    repository.get_for_update.return_value = existing
    repository.update.side_effect = lambda value: value
    await DeviceService(repository).revoke(existing.id)
    assert repository.update.call_args.args[0].last_login_at == existing.last_login_at
