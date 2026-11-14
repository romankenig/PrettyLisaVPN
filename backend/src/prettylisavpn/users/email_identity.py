"""Only provider-documented shared namespaces; never strip arbitrary domain zones.

Delivery/display use normalize_email, not this lookup key. Sources and deliberately
excluded providers are recorded in docs/email-identities.md.
"""

from prettylisavpn.users.domain import normalize_email

DOMAIN_GROUPS = (
    ("yandex.ru", "yandex.com", "yandex.by", "yandex.kz", "ya.ru"),
    ("gmail.com", "googlemail.com"),
    ("proton.me", "protonmail.com", "protonmail.ch", "pm.me"),
)


class EmailAliasConflictError(Exception):
    """Legacy accounts already occupy this identity; do not merge their data."""


def email_aliases(email: str) -> tuple[str, ...]:
    normalized = normalize_email(email)
    local, separator, domain = normalized.rpartition("@")
    if not separator:
        return (normalized,)
    for domains in DOMAIN_GROUPS:
        if domain in domains:
            return tuple(f"{local}@{item}" for item in domains)
    return (normalized,)


def email_identity(email: str) -> str:
    return email_aliases(email)[0]
