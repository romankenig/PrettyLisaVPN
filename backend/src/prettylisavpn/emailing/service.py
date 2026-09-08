"""Provider-independent verification email composition."""

from datetime import UTC, datetime
from html import escape

from prettylisavpn.emailing.domain import EmailProvider, OutboundEmail
from prettylisavpn.users.domain import normalize_email

VERIFICATION_SUBJECT = "Your PrettyLisaVPN verification code"


class VerificationEmailService:
    def __init__(self, provider: EmailProvider) -> None:
        self._provider = provider

    async def send_code(self, recipient: str, code: str, expires_at: datetime) -> None:
        if expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")

        normalized_recipient = normalize_email(recipient)
        expiration = expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        text_body = (
            "Your PrettyLisaVPN verification code is:\n\n"
            f"{code}\n\n"
            f"This code expires at {expiration}.\n"
            "If you did not request this code, you can safely ignore this email."
        )
        html_body = (
            '<!doctype html><html lang="en"><body>'
            "<p>Your PrettyLisaVPN verification code is:</p>"
            f"<p><strong>{escape(code)}</strong></p>"
            f"<p>This code expires at {escape(expiration)}.</p>"
            "<p>If you did not request this code, you can safely ignore this email.</p>"
            "</body></html>"
        )
        await self._provider.send(
            OutboundEmail(
                recipient=normalized_recipient,
                subject=VERIFICATION_SUBJECT,
                text_body=text_body,
                html_body=html_body,
            )
        )
