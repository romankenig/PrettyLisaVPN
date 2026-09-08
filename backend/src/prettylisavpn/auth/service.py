"""Request-OTP orchestration independent of HTTP and provider infrastructure."""

from typing import Protocol

from prettylisavpn.emailing.domain import EmailDeliveryError, EmailProvider
from prettylisavpn.emailing.service import VerificationEmailService
from prettylisavpn.otp import IssuedOtp, OtpServiceUnavailableError
from prettylisavpn.product_events.domain import ProductEventName
from prettylisavpn.users.domain import normalize_email


class OtpIssuer(Protocol):
    async def request(self, email: str, client_ip: str) -> IssuedOtp | None: ...

    async def discard(self, email: str) -> None: ...


class ProductEventSink(Protocol):
    async def record(self, event_name: ProductEventName) -> None: ...


class OtpRateLimitedError(RuntimeError):
    """OTP request cooldown or request limit was reached."""


class OtpStorageUnavailableError(RuntimeError):
    """OTP state could not be stored safely."""


class OtpDeliveryUnavailableError(RuntimeError):
    """Verification email could not be delivered safely."""


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
