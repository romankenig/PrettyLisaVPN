"""Application service for device lifecycle operations."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from prettylisavpn.devices.domain import (
    Device,
    DeviceLimitReachedError,
    DevicePlatform,
    DeviceStatus,
    DeviceUserNotFoundError,
    normalize_device_name,
)
from prettylisavpn.devices.repository import DeviceRepository

MAX_ACTIVE_DEVICES = 5


class DeviceService:
    def __init__(self, repository: DeviceRepository) -> None:
        self._repository = repository

    async def register(
        self,
        user_id: UUID,
        installation_id: UUID,
        platform: DevicePlatform,
        device_name: str,
    ) -> Device:
        device, _ = await self.register_with_result(user_id, installation_id, platform, device_name)
        return device

    async def register_with_result(
        self,
        user_id: UUID,
        installation_id: UUID,
        platform: DevicePlatform,
        device_name: str,
    ) -> tuple[Device, bool]:
        if not await self._repository.lock_user(user_id):
            raise DeviceUserNotFoundError

        normalized_name = normalize_device_name(device_name)
        existing = await self._repository.get_by_installation_for_update(user_id, installation_id)
        if existing is not None and existing.is_active():
            if existing.platform is platform and existing.device_name == normalized_name:
                return existing, False
            return (
                await self._repository.update(
                    self._with_active_metadata(existing, platform, normalized_name)
                ),
                False,
            )

        if await self._repository.count_active(user_id) >= MAX_ACTIVE_DEVICES:
            raise DeviceLimitReachedError

        if existing is not None:
            return (
                await self._repository.update(
                    self._with_active_metadata(existing, platform, normalized_name)
                ),
                True,
            )

        now = datetime.now(UTC)
        return (
            await self._repository.add(
                Device(
                    id=uuid4(),
                    user_id=user_id,
                    installation_id=installation_id,
                    platform=platform,
                    device_name=normalized_name,
                    status=DeviceStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                    revoked_at=None,
                )
            ),
            True,
        )

    async def revoke(self, device_id: UUID) -> bool:
        device = await self._repository.get_for_update(device_id)
        if device is None or not device.is_active():
            return False
        now = datetime.now(UTC)
        await self._repository.update(
            replace(device, status=DeviceStatus.REVOKED, updated_at=now, revoked_at=now)
        )
        return True

    @staticmethod
    def _with_active_metadata(device: Device, platform: DevicePlatform, device_name: str) -> Device:
        return replace(
            device,
            platform=platform,
            device_name=device_name,
            status=DeviceStatus.ACTIVE,
            updated_at=datetime.now(UTC),
            revoked_at=None,
        )

    async def record_successful_login(self, device: Device, at: datetime) -> Device:
        return await self._repository.update(replace(device, last_login_at=at, updated_at=at))
