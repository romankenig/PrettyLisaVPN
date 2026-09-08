"""Timeweb mailbox adapter using the documented SMTP service."""

import asyncio
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal, Protocol

import aiosmtplib
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPException,
    SMTPRecipientsRefused,
    SMTPTimeoutError,
)

from prettylisavpn.config import Settings
from prettylisavpn.emailing.domain import (
    EmailAuthenticationError,
    EmailDeliveryError,
    EmailProviderConfigurationError,
    EmailProviderUnavailableError,
    EmailRecipientRejectedError,
    OutboundEmail,
)

TlsMode = Literal["implicit_tls", "starttls"]


class SmtpTransport(Protocol):
    async def send(self, message: EmailMessage, *, sender: str, recipient: str) -> None: ...


class AiosmtplibTransport:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        tls_mode: TlsMode,
        username: str,
        password: str,
        connection_timeout_seconds: float,
        send_timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._tls_mode = tls_mode
        self._username = username
        self._password = password
        self._connection_timeout_seconds = connection_timeout_seconds
        self._send_timeout_seconds = send_timeout_seconds

    async def send(self, message: EmailMessage, *, sender: str, recipient: str) -> None:
        async with asyncio.timeout(self._send_timeout_seconds):
            await aiosmtplib.send(
                message,
                sender=sender,
                recipients=[recipient],
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                timeout=self._connection_timeout_seconds,
                use_tls=self._tls_mode == "implicit_tls",
                start_tls=self._tls_mode == "starttls",
                validate_certs=True,
            )


class TimewebEmailProvider:
    def __init__(
        self,
        *,
        transport: SmtpTransport,
        from_address: str,
        from_name: str,
    ) -> None:
        self._transport = transport
        self._from_address = from_address
        self._from_name = from_name

    @classmethod
    def from_settings(cls, settings: Settings) -> "TimewebEmailProvider":
        password = settings.email_smtp_password
        if password is None or not password.get_secret_value():
            raise EmailProviderConfigurationError("SMTP credential is not configured")
        return cls(
            transport=AiosmtplibTransport(
                host=settings.email_smtp_host,
                port=settings.email_smtp_port,
                tls_mode=settings.email_smtp_tls_mode,
                username=settings.email_smtp_username,
                password=password.get_secret_value(),
                connection_timeout_seconds=settings.email_connection_timeout_seconds,
                send_timeout_seconds=settings.email_send_timeout_seconds,
            ),
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
        )

    async def send(self, email: OutboundEmail) -> None:
        message = EmailMessage()
        message["From"] = formataddr((self._from_name, self._from_address))
        message["To"] = email.recipient
        message["Subject"] = email.subject
        message.set_content(email.text_body)
        message.add_alternative(email.html_body, subtype="html")

        try:
            await self._transport.send(
                message,
                sender=self._from_address,
                recipient=email.recipient,
            )
        except SMTPAuthenticationError:
            raise EmailAuthenticationError("Email provider authentication failed") from None
        except SMTPRecipientsRefused:
            raise EmailRecipientRejectedError("Email provider rejected the recipient") from None
        except (SMTPTimeoutError, TimeoutError, OSError):
            raise EmailProviderUnavailableError("Email provider is unavailable") from None
        except SMTPException:
            raise EmailDeliveryError("Email provider rejected delivery") from None
