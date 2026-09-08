"""Passwordless authentication orchestration independent of HTTP."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.tokens import AccessTokenService, IssuedAccessToken
from prettylisavpn.auth_sessions.domain import IssuedAuthSession
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import Device, DeviceLimitReachedError, DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.emailing.domain import EmailDeliveryError, EmailProvider
from prettylisavpn.emailing.service import VerificationEmailService
from prettylisavpn.otp import IssuedOtp, OtpServiceUnavailableError
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.subscriptions.domain import Subscription
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.domain import User, UserStatus, normalize_email
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


class OtpIssuer(Protocol):
    async def request(self, email: str, client_ip: str) -> IssuedOtp | None: ...

    async def discard(self, email: str) -> None: ...


class OtpVerifier(Protocol):
    async def verify(self, email: str, code: str) -> bool: ...


class ProductEventSink(Protocol):
    async def record(
        self,
        event_name: ProductEventName,
        *,
        user_id: UUID | None = None,
        device_id: UUID | None = None,
        properties: Mapping[str, object] | None = None,
    ) -> None: ...


class LoginHandler(Protocol):
    async def verify_otp(
        self,
        email: str,
        code: str,
        installation_id: UUID,
        platform: DevicePlatform,
        device_name: str,
    ) -> "LoginResult": ...


class OtpRateLimitedError(RuntimeError):
    """OTP request cooldown or request limit was reached."""


class OtpStorageUnavailableError(RuntimeError):
    """OTP state could not be stored safely."""


class OtpDeliveryUnavailableError(RuntimeError):
    """Verification email could not be delivered safely."""


class InvalidOtpError(Exception):
    """The OTP is invalid, expired, or already consumed."""


class BlockedUserError(Exception):
    """The user is not allowed to log in."""


class LoginPersistenceError(RuntimeError):
    """Persistent login state could not be created safely."""


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    subscription: Subscription
    device: Device
    auth_session: IssuedAuthSession
    access_token: IssuedAccessToken


class RequestOtpService:
    def __init__(
        self,
        otp: OtpIssuer,
        email_provider: EmailProvider | None,
        events: ProductEventSink,
    ) -> None:
        self._otp = otp
        self._email = (
            VerificationEmailService(email_provider) if email_provider is not None else None
        )
        self._events = events

    async def request(self, email: str, client_ip: str) -> None:
        normalized_email = normalize_email(email)
        await self._events.record(ProductEventName.OTP_REQUESTED)
        if self._email is None:
            raise OtpDeliveryUnavailableError("Email delivery is not configured")

        try:
            issued = await self._otp.request(normalized_email, client_ip)
        except OtpServiceUnavailableError:
            raise OtpStorageUnavailableError("OTP storage is unavailable") from None
        if issued is None:
            raise OtpRateLimitedError("OTP request limit reached")

        try:
            await self._email.send_code(normalized_email, issued.code, issued.expires_at)
        except EmailDeliveryError:
            try:
                await self._otp.discard(normalized_email)
            except OtpServiceUnavailableError:
                pass
            raise OtpDeliveryUnavailableError("Email delivery is unavailable") from None

        await self._events.record(ProductEventName.OTP_SENT)


class LoginService:
    def __init__(
        self,
        otp: OtpVerifier,
        postgres: Postgres,
        events: ProductEventSink,
        settings: Settings,
    ) -> None:
        self._otp = otp
        self._postgres = postgres
        self._events = events
        self._access_tokens = AccessTokenService(settings)
        self._refresh_token_ttl = timedelta(seconds=settings.refresh_token_ttl_seconds)

    async def verify_otp(
        self,
        email: str,
        code: str,
        installation_id: UUID,
        platform: DevicePlatform,
        device_name: str,
    ) -> LoginResult:
        normalized_email = normalize_email(email)
        try:
            verified = await self._otp.verify(normalized_email, code)
        except OtpServiceUnavailableError:
            raise OtpStorageUnavailableError("OTP storage is unavailable") from None
        if not verified:
            await self._events.record(
                ProductEventName.LOGIN_FAILED,
                properties={"reason": "invalid_otp"},
            )
            raise InvalidOtpError

        await self._events.record(ProductEventName.OTP_VERIFIED)

        user: User | None = None
        try:
            async with self._postgres.session() as session:
                async with session.begin():
                    user, subscription, _ = await UserService(
                        UserRepository(session), SubscriptionRepository(session)
                    ).find_or_create_with_subscription(normalized_email)
                    if user.status is UserStatus.BLOCKED:
                        raise BlockedUserError

                    device, device_registered = await DeviceService(
                        DeviceRepository(session)
                    ).register_with_result(
                        user.id,
                        installation_id,
                        platform,
                        device_name,
                    )
                    auth_session = await AuthSessionService(
                        AuthSessionRepository(session), self._refresh_token_ttl
                    ).issue(user.id, device.id)
                    access_token = self._access_tokens.issue(
                        user.id, device.id, auth_session.session.id
                    )
        except BlockedUserError:
            await self._events.record(
                ProductEventName.LOGIN_FAILED,
                user_id=user.id if user is not None else None,
                properties={"reason": "user_blocked"},
            )
            raise
        except DeviceLimitReachedError:
            await self._events.record(
                ProductEventName.LOGIN_FAILED,
                user_id=user.id if user is not None else None,
                properties={"reason": "device_limit"},
            )
            raise
        except SQLAlchemyError:
            raise LoginPersistenceError("Login persistence is unavailable") from None

        if device_registered:
            await self._events.record(
                ProductEventName.DEVICE_REGISTERED,
                user_id=user.id,
                device_id=device.id,
                properties={"platform": platform.value},
            )
        await self._events.record(
            ProductEventName.LOGIN_SUCCEEDED,
            user_id=user.id,
            device_id=device.id,
        )
        return LoginResult(
            user=user,
            subscription=subscription,
            device=device,
            auth_session=auth_session,
            access_token=access_token,
        )
