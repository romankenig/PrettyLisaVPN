"""Anonymous device identity is never an email account or an upgrade credential."""

import hashlib
import hmac

DEMO_EMAIL_DOMAIN = "demo.prettylisavpn.com"
DEMO_SECONDS = 900


class RegistrationRequiredError(Exception):
    """This operation requires a verified email account."""


class DemoUnavailableError(Exception):
    """Guest admission could not be completed safely."""


class DemoRateLimitedError(Exception):
    """Anonymous admission is rate limited, independently from OTP."""


def identity_digest(secret: str, device_key: str) -> bytes:
    return hmac.digest(
        secret.encode(), b"PrettyLisaVPN/demo/v1\0" + device_key.encode(), hashlib.sha256
    )


def is_demo_email(email: str) -> bool:
    return email.strip().lower().endswith("@" + DEMO_EMAIL_DOMAIN)
