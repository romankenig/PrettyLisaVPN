import asyncio
from datetime import UTC, datetime
from email.message import EmailMessage
from unittest.mock import AsyncMock

import pytest
from aiosmtplib.errors import (
    SMTPAuthenticationError,
    SMTPException,
    SMTPRecipientRefused,
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
from prettylisavpn.emailing.service import VERIFICATION_SUBJECT, VerificationEmailService
from prettylisavpn.emailing.timeweb import AiosmtplibTransport, TimewebEmailProvider


class FakeEmailProvider:
    def __init__(self) -> None:
        self.sent: list[OutboundEmail] = []

    async def send(self, email: OutboundEmail) -> None:
        self.sent.append(email)


async def test_verification_service_builds_plain_and_html_email_without_external_assets():
    provider = FakeEmailProvider()
    service = VerificationEmailService(provider)

    await service.send_code(
        " User@Example.COM ",
        "123456",
        datetime(2026, 9, 8, 12, 5, tzinfo=UTC),
    )

    email = provider.sent[0]
    assert email.recipient == "user@example.com"
    assert email.subject == VERIFICATION_SUBJECT
    assert "123456" in email.text_body
    assert "2026-09-08 12:05:00 UTC" in email.text_body
    assert "safely ignore" in email.text_body
    assert "123456" in email.html_body
    assert "2026-09-08 12:05:00 UTC" in email.html_body
    assert "safely ignore" in email.html_body
    assert "<img" not in email.html_body
    assert "http://" not in email.html_body
    assert "https://" not in email.html_body
    assert "123456" not in repr(email)


async def test_verification_service_requires_aware_expiration():
    with pytest.raises(ValueError, match="timezone-aware"):
        await VerificationEmailService(FakeEmailProvider()).send_code(
            "user@example.com", "123456", datetime(2026, 9, 8, 12, 5)
        )


async def test_timeweb_provider_builds_multipart_message():
    transport = AsyncMock()
    provider = TimewebEmailProvider(
        transport=transport,
        from_address="auth@prettylisavpn.com",
        from_name="PrettyLisaVPN",
    )
    email = OutboundEmail(
        recipient="user@example.com",
        subject=VERIFICATION_SUBJECT,
        text_body="plain 123456",
        html_body="<p>html 123456</p>",
    )

    await provider.send(email)

    transport.send.assert_awaited_once()
    message: EmailMessage = transport.send.await_args.args[0]
    assert message["From"] == "PrettyLisaVPN <auth@prettylisavpn.com>"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == VERIFICATION_SUBJECT
    assert message.is_multipart()
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "plain 123456"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>html 123456</p>"
    assert transport.send.await_args.kwargs == {
        "sender": "auth@prettylisavpn.com",
        "recipient": "user@example.com",
    }


@pytest.mark.parametrize(
    ("provider_error", "application_error"),
    [
        (SMTPAuthenticationError(535, "sensitive-provider-detail"), EmailAuthenticationError),
        (
            SMTPRecipientsRefused(
                [SMTPRecipientRefused(550, "sensitive-provider-detail", "user@example.com")]
            ),
            EmailRecipientRejectedError,
        ),
        (SMTPTimeoutError("timeout"), EmailProviderUnavailableError),
        (OSError("network"), EmailProviderUnavailableError),
        (SMTPException("failure"), EmailDeliveryError),
    ],
)
async def test_timeweb_provider_maps_failures_without_retry(provider_error, application_error):
    transport = AsyncMock()
    transport.send.side_effect = provider_error
    provider = TimewebEmailProvider(
        transport=transport,
        from_address="auth@prettylisavpn.com",
        from_name="PrettyLisaVPN",
    )
    email = OutboundEmail(
        recipient="user@example.com",
        subject=VERIFICATION_SUBJECT,
        text_body="plain",
        html_body="<p>html</p>",
    )

    with pytest.raises(application_error) as captured:
        await provider.send(email)

    transport.send.assert_awaited_once()
    assert captured.value.__cause__ is None
    assert "sensitive-provider-detail" not in str(captured.value)


def test_timeweb_provider_requires_smtp_credential():
    with pytest.raises(EmailProviderConfigurationError, match="not configured"):
        TimewebEmailProvider.from_settings(Settings(_env_file=None, email_smtp_password=None))


@pytest.mark.parametrize(
    ("tls_mode", "use_tls", "start_tls"),
    [("implicit_tls", True, False), ("starttls", False, True)],
)
async def test_aiosmtplib_transport_uses_explicit_tls_mode(
    monkeypatch, tls_mode, use_tls, start_tls
):
    send = AsyncMock()
    monkeypatch.setattr("prettylisavpn.emailing.timeweb.aiosmtplib.send", send)
    transport = AiosmtplibTransport(
        host="smtp.timeweb.ru",
        port=465 if use_tls else 587,
        tls_mode=tls_mode,
        username="auth@prettylisavpn.com",
        password="private-password",
        connection_timeout_seconds=3,
        send_timeout_seconds=7,
    )

    await transport.send(EmailMessage(), sender="sender@example.com", recipient="user@example.com")

    assert send.await_args.kwargs["hostname"] == "smtp.timeweb.ru"
    assert send.await_args.kwargs["use_tls"] is use_tls
    assert send.await_args.kwargs["start_tls"] is start_tls
    assert send.await_args.kwargs["validate_certs"] is True
    assert send.await_args.kwargs["timeout"] == 3


async def test_transport_enforces_total_send_timeout(monkeypatch):
    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr("prettylisavpn.emailing.timeweb.aiosmtplib.send", never_finishes)
    transport = AiosmtplibTransport(
        host="smtp.timeweb.ru",
        port=465,
        tls_mode="implicit_tls",
        username="auth@prettylisavpn.com",
        password="private-password",
        connection_timeout_seconds=1,
        send_timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError):
        await transport.send(
            EmailMessage(), sender="sender@example.com", recipient="user@example.com"
        )
