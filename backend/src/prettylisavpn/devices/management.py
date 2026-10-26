"""Authenticated device-management application service."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.service import ProductEventSink
from prettylisavpn.auth.session_service import AccessIdentity, AuthenticatedSessionHandler
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import Device
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.product_events.domain import ProductEventName


class DeviceNotFoundError(Exception):
    """The requested device does not belong to the authenticated user."""


class DeviceManagementUnavailableError(RuntimeError):
    """Persistent device state is unavailable."""


@dataclass(frozen=True, slots=True)
class ManagedDevice:
    device: Device
    is_current: bool


class DeviceManagementHandler(Protocol):
    async def list_devices(self, access_token: str) -> list[ManagedDevice]: ...

    async def revoke_device(self, access_token: str, device_id: UUID) -> ManagedDevice: ...


class DeviceManagementService:
    def __init__(
        self,
        postgres: Postgres,
        authenticated_sessions: AuthenticatedSessionHandler,
        events: ProductEventSink,
        settings: Settings,
    ) -> None:
        self._postgres = postgres
        self._authenticated_sessions = authenticated_sessions
        self._events = events
        self._refresh_token_ttl = timedelta(seconds=settings.refresh_token_ttl_seconds)

    async def list_devices(self, access_token: str) -> list[ManagedDevice]:
        identity = await self._authenticated_sessions.authenticate(access_token)
        try:
            async with self._postgres.session() as session:
                devices = await DeviceRepository(session).list_by_user(identity.user_id)
        except SQLAlchemyError:
            raise DeviceManagementUnavailableError("Device storage is unavailable") from None
        return [self._managed(device, identity) for device in devices]

    async def revoke_device(self, access_token: str, device_id: UUID) -> ManagedDevice:
        identity = await self._authenticated_sessions.authenticate(access_token)
        transitioned = False
        try:
            async with self._postgres.session() as session:
                async with session.begin():
                    repository = DeviceRepository(session)
                    if not await repository.lock_user(identity.user_id):
                        raise DeviceNotFoundError
                    device = await repository.get_for_update(device_id)
                    if device is None or device.user_id != identity.user_id:
                        raise DeviceNotFoundError
                    if device.is_active():
                        transitioned = await DeviceService(repository).revoke(device.id)
                        if not transitioned:
                            raise DeviceManagementUnavailableError(
                                "Active device could not be revoked"
                            )
                        device = await repository.get_for_update(device.id)
                        if device is None:
                            raise DeviceManagementUnavailableError("Revoked device disappeared")
                    await AuthSessionService(
                        AuthSessionRepository(session), self._refresh_token_ttl
                    ).revoke_device_sessions(device.id)
        except (DeviceNotFoundError, DeviceManagementUnavailableError):
            raise
        except SQLAlchemyError:
            raise DeviceManagementUnavailableError("Device storage is unavailable") from None

        if transitioned:
            await self._events.record(
                ProductEventName.DEVICE_REVOKED,
                user_id=identity.user_id,
                device_id=device.id,
            )
        return self._managed(device, identity)

    @staticmethod
    def _managed(device: Device, identity: AccessIdentity) -> ManagedDevice:
        return ManagedDevice(device=device, is_current=device.id == identity.device_id)
