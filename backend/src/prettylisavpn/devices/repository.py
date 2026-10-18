"""Async persistence operations for devices."""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.devices.domain import Device, DeviceStatus
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.users.model import UserRecord


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: UUID) -> bool:
        statement = select(UserRecord.id).where(UserRecord.id == user_id).with_for_update()
        return await self._session.scalar(statement) is not None

    async def get_by_installation_for_update(
        self, user_id: UUID, installation_id: UUID
    ) -> Device | None:
        statement = (
            select(DeviceRecord)
            .where(
                DeviceRecord.user_id == user_id,
                DeviceRecord.installation_id == installation_id,
            )
            .with_for_update()
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def get_for_update(self, device_id: UUID) -> Device | None:
        statement = select(DeviceRecord).where(DeviceRecord.id == device_id).with_for_update()
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def get(self, device_id: UUID) -> Device | None:
        record = await self._session.get(DeviceRecord, device_id)
        return self._to_domain(record) if record is not None else None

    async def list_by_user(self, user_id: UUID) -> list[Device]:
        records = await self._session.scalars(
            select(DeviceRecord)
            .where(DeviceRecord.user_id == user_id)
            .order_by(DeviceRecord.created_at, DeviceRecord.id)
        )
        return [self._to_domain(record) for record in records]

    async def count_active(self, user_id: UUID) -> int:
        statement = select(func.count(DeviceRecord.id)).where(
            DeviceRecord.user_id == user_id,
            DeviceRecord.status == DeviceStatus.ACTIVE,
        )
        return await self._session.scalar(statement) or 0

    async def add(self, device: Device) -> Device:
        record = DeviceRecord(
            id=device.id,
            user_id=device.user_id,
            installation_id=device.installation_id,
            platform=device.platform,
            device_name=device.device_name,
            status=device.status,
            created_at=device.created_at,
            updated_at=device.updated_at,
            revoked_at=device.revoked_at,
            last_login_at=device.last_login_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def update(self, device: Device) -> Device:
        await self._session.execute(
            update(DeviceRecord)
            .where(DeviceRecord.id == device.id)
            .values(
                platform=device.platform,
                device_name=device.device_name,
                status=device.status,
                updated_at=device.updated_at,
                revoked_at=device.revoked_at,
                last_login_at=device.last_login_at,
            )
        )
        return device

    @staticmethod
    def _to_domain(record: DeviceRecord) -> Device:
        return Device(
            id=record.id,
            user_id=record.user_id,
            installation_id=record.installation_id,
            platform=record.platform,
            device_name=record.device_name,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            revoked_at=record.revoked_at,
            last_login_at=record.last_login_at,
        )

