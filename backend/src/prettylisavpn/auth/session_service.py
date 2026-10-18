"""Authenticated-session application services."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.auth.service import BlockedUserError, ProductEventSink
from prettylisavpn.auth.tokens import AccessTokenService, InvalidAccessTokenError, IssuedAccessToken
from prettylisavpn.auth_sessions.domain import (
    AuthSession,
    InvalidAuthSessionError,
    IssuedAuthSession,
)
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import Device, DeviceStatus
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.subscriptions.entitlements import free_quota_resets_at
from prettylisavpn.users.domain import User, UserStatus
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository


class InvalidSessionError(Exception):
    """The access token refers to an unusable session."""


class InvalidRefreshTokenError(Exception):
    """The refresh credentials are invalid, expired, revoked, or replayed."""


class RevokedDeviceError(Exception):
    """The session device is no longer active."""


class AuthServiceUnavailableError(RuntimeError):
    """Persistent authenticated-session state is unavailable."""


@dataclass(frozen=True, slots=True)
class AccessIdentity:
    user_id: UUID
    device_id: UUID
    session_id: UUID


@dataclass(frozen=True, slots=True)
class RefreshedTokens:
    auth_session: IssuedAuthSession
    access_token: IssuedAccessToken


@dataclass(frozen=True, slots=True)
class MeSummary:
    user_id: UUID
    email: str
    plan: SubscriptionPlan
    active_device_count: int
    subscription: Subscription | None = None
    free_seconds_remaining: int | None = None
    free_quota_resets_at: datetime | None = None


class AuthenticatedSessionHandler(Protocol):
    async def authenticate(self, access_token: str) -> AccessIdentity: ...

    async def refresh(self, session_id: UUID, refresh_token: str) -> RefreshedTokens: ...

    async def logout(self, access_token: str) -> None: ...

    async def me(self, access_token: str) -> MeSummary: ...


class AuthenticatedSessionService:
    def __init__(
        self,
        postgres: Postgres,
        events: ProductEventSink,
        settings: Settings,
    ) -> None:
        self._postgres = postgres
        self._events = events
        self._access_tokens = AccessTokenService(settings)
        self._refresh_token_ttl = timedelta(seconds=settings.refresh_token_ttl_seconds)

    async def authenticate(self, access_token: str) -> AccessIdentity:
        identity = self._decode_identity(access_token)
        try:
            async with self._postgres.session() as session:
                auth_session = await AuthSessionRepository(session).get(identity.session_id)
                auth_session = self._require_session(auth_session, identity)
                await self._load_principals(session, auth_session)
        except (InvalidSessionError, BlockedUserError, RevokedDeviceError):
            raise
        except SQLAlchemyError:
            raise AuthServiceUnavailableError("Authentication storage is unavailable") from None
        return identity

    async def refresh(self, session_id: UUID, refresh_token: str) -> RefreshedTokens:
        try:
            async with self._postgres.session() as session:
                async with session.begin():
                    repository = AuthSessionRepository(session)
                    candidate = await repository.get(session_id)
                    now = datetime.now(UTC)
                    session_service = AuthSessionService(repository, self._refresh_token_ttl)
                    if candidate is None or not session_service.is_refresh_token_usable(
                        candidate, refresh_token, now
                    ):
                        raise InvalidRefreshTokenError

                    await self._load_principals(session, candidate, for_update=True)
                    try:
                        locked = await session_service.validate_refresh_token(
                            session_id, refresh_token
                        )
                    except InvalidAuthSessionError:
                        raise InvalidRefreshTokenError from None
                    rotated = await session_service.rotate_validated(locked)
                    access_token = self._access_tokens.issue(
                        rotated.session.user_id,
                        rotated.session.device_id,
                        rotated.session.id,
                    )
        except (InvalidRefreshTokenError, BlockedUserError, RevokedDeviceError):
            raise
        except SQLAlchemyError:
            raise AuthServiceUnavailableError("Authentication storage is unavailable") from None

        await self._events.record(
            ProductEventName.TOKEN_REFRESHED,
            user_id=rotated.session.user_id,
            device_id=rotated.session.device_id,
        )
        return RefreshedTokens(auth_session=rotated, access_token=access_token)

    async def logout(self, access_token: str) -> None:
        identity = self._decode_identity(access_token)
        try:
            async with self._postgres.session() as session:
                async with session.begin():
                    repository = AuthSessionRepository(session)
                    candidate = await repository.get(identity.session_id)
                    candidate = self._require_session(candidate, identity)
                    await self._load_principals(session, candidate, for_update=True)
                    locked = await repository.get_for_update(identity.session_id)
                    self._require_session(locked, identity)
                    if not await AuthSessionService(repository, self._refresh_token_ttl).revoke(
                        identity.session_id
                    ):
                        raise InvalidSessionError
        except (InvalidSessionError, BlockedUserError, RevokedDeviceError):
            raise
        except SQLAlchemyError:
            raise AuthServiceUnavailableError("Authentication storage is unavailable") from None

        await self._events.record(
            ProductEventName.LOGOUT,
            user_id=identity.user_id,
            device_id=identity.device_id,
            properties={"scope": "session"},
        )

    async def me(self, access_token: str) -> MeSummary:
        identity = self._decode_identity(access_token)
        try:
            async with self._postgres.session() as session:
                repository = AuthSessionRepository(session)
                auth_session = await repository.get(identity.session_id)
                auth_session = self._require_session(auth_session, identity)
                user, _ = await self._load_principals(session, auth_session)
                subscription = await SubscriptionRepository(session).get_by_user_id(user.id)
                if subscription is None:
                    raise AuthServiceUnavailableError("Subscription state is unavailable")
                now = datetime.now(UTC)
                plan = subscription.effective_plan(now)
                active_device_count = await DeviceRepository(session).count_active(user.id)
                remaining = None
                resets_at = None
                if plan is SubscriptionPlan.FREE:
                    remaining = await VpnSessionRepository(session).remaining_free_seconds(user.id, now)
                    resets_at = free_quota_resets_at(now)
                await session.commit()
        except (
            InvalidSessionError,
            BlockedUserError,
            RevokedDeviceError,
            AuthServiceUnavailableError,
        ):
            raise
        except SQLAlchemyError:
            raise AuthServiceUnavailableError("Authentication storage is unavailable") from None

        return MeSummary(
            user_id=user.id,
            email=user.email,
            plan=plan,
            active_device_count=active_device_count,
            subscription=subscription,
            free_seconds_remaining=remaining,
            free_quota_resets_at=resets_at,
        )

    def _decode_identity(self, access_token: str) -> AccessIdentity:
        try:
            claims = self._access_tokens.decode(access_token)
            return AccessIdentity(
                user_id=UUID(str(claims["sub"])),
                device_id=UUID(str(claims["device_id"])),
                session_id=UUID(str(claims["session_id"])),
            )
        except (InvalidAccessTokenError, KeyError, TypeError, ValueError):
            raise InvalidAccessTokenError from None

    @staticmethod
    def _require_session(auth_session: AuthSession | None, identity: AccessIdentity) -> AuthSession:
        if (
            auth_session is None
            or not auth_session.is_active(datetime.now(UTC))
            or auth_session.user_id != identity.user_id
            or auth_session.device_id != identity.device_id
        ):
            raise InvalidSessionError
        return auth_session

    @staticmethod
    async def _load_principals(
        session: AsyncSession,
        auth_session: AuthSession,
        *,
        for_update: bool = False,
    ) -> tuple[User, Device]:
        user = await UserRepository(session).get_by_id(auth_session.user_id, for_update=for_update)
        if user is None:
            raise InvalidSessionError
        if user.status is UserStatus.BLOCKED:
            raise BlockedUserError

        device_repository = DeviceRepository(session)
        device = (
            await device_repository.get_for_update(auth_session.device_id)
            if for_update
            else await device_repository.get(auth_session.device_id)
        )
        if device is None or device.user_id != user.id:
            raise InvalidSessionError
        if device.status is DeviceStatus.REVOKED:
            raise RevokedDeviceError
        return user, device

