"""Application service for device lifecycle operations."""

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
        if not await self._repository.lock_user(user_id):
            raise DeviceUserNotFoundError

        normalized_name = normalize_device_name(device_name)
        existing = await self._repository.get_by_installation_for_update(user_id, installation_id)
        if existing is not None and existing.is_active():
            if existing.platform is platform and existing.device_name == normalized_name:
                return existing
            return await self._repository.update(
                self._with_active_metadata(existing, platform, normalized_name)
            )

        if await self._repository.count_active(user_id) >= MAX_ACTIVE_DEVICES:
            raise DeviceLimitReachedError

        if existing is not None:
            return await self._repository.update(
                self._with_active_metadata(existing, platform, normalized_name)
            )

        now = datetime.now(UTC)
        return await self._repository.add(
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
        )

    async def revoke(self, device_id: UUID) -> bool:
        device = await self._repository.get_for_update(device_id)
        if device is None or not device.is_active():
            return False
        now = datetime.now(UTC)
        await self._repository.update(
            Device(
                id=device.id,
                user_id=device.user_id,
                installation_id=device.installation_id,
                platform=device.platform,
                device_name=device.device_name,
                status=DeviceStatus.REVOKED,
                created_at=device.created_at,
                updated_at=now,
                revoked_at=now,
            )
        )
        return True

    @staticmethod
    def _with_active_metadata(device: Device, platform: DevicePlatform, device_name: str) -> Device:
        return Device(
            id=device.id,
            user_id=device.user_id,
            installation_id=device.installation_id,
            platform=platform,
            device_name=device_name,
            status=DeviceStatus.ACTIVE,
            created_at=device.created_at,
            updated_at=datetime.now(UTC),
            revoked_at=None,
        )
