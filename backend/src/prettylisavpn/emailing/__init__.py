"""Provider-independent email delivery."""

from prettylisavpn.emailing.domain import EmailProvider, OutboundEmail
from prettylisavpn.emailing.service import VerificationEmailService

__all__ = ["EmailProvider", "OutboundEmail", "VerificationEmailService"]
