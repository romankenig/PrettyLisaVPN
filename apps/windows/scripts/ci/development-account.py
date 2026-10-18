"""Disposable acceptance account; run inside the existing development container.

Short-lived acceptance credentials on stdout are consumed over SSH
by a private runner file. Never upload that file or treat this as an OTP test.
"""

import asyncio
import json
import re
import smtplib
import ssl
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


def smtp_observations(config):
    result = {}
    for name, username, password in (
        ("otp", config.email_smtp_username, config.email_smtp_password),
        ("support", "app-helper@prettylisavpn.com", config.support_smtp_password),
    ):
        if password is None:
            result[name] = "not configured"
            continue
        try:
            client = (
                smtplib.SMTP_SSL
                if config.email_smtp_tls_mode == "implicit_tls"
                else smtplib.SMTP
            )
            with client(config.email_smtp_host, config.email_smtp_port, timeout=5) as smtp:
                if config.email_smtp_tls_mode == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(username, password.get_secret_value())
            result[name] = "authenticated; no message sent"
        except smtplib.SMTPAuthenticationError:
            result[name] = "authentication failed"
        except (OSError, smtplib.SMTPException):
            result[name] = "unavailable"
    return result


async def main():
    mode, run = sys.argv[1:3]
    installation = UUID(sys.argv[3]) if len(sys.argv) == 4 else None
    if mode not in ("create", "cleanup") or not re.fullmatch(r"[0-9]+-[0-9]+", run):
        raise SystemExit("Invalid acceptance scope")
    config = Settings()
    if config.environment != "development" or config.billing_provider != "disabled":
        raise SystemExit("Expected development with payments disabled")
    email = f"windows-acceptance-{run}@example.com"
    postgres = Postgres(config)
    try:
        async with postgres.session() as session, session.begin():
            if mode == "cleanup":
                result = await session.execute(delete(UserRecord).where(UserRecord.email == email))
                output = {"cleanup": "passed", "deleted_accounts": result.rowcount}
                if installation is not None:
                    device = await session.scalar(
                        select(DeviceRecord)
                        .join(UserRecord, UserRecord.id == DeviceRecord.user_id)
                        .where(DeviceRecord.installation_id == installation)
                        .where(UserRecord.email == "kenromka@yandex.com")
                    )
                    if device is not None:
                        await DeviceService(DeviceRepository(session)).revoke(device.id)
                        await AuthSessionRepository(session).revoke_for_device(
                            device.id, datetime.now(UTC)
                        )
                    output["otp_runner_device_revoked"] = device is not None
            else:
                user = await UserService(
                    UserRepository(session), SubscriptionRepository(session)
                ).create(email)
                devices = DeviceService(DeviceRepository(session))
                current = await devices.register(
                    user.id, uuid4(), DevicePlatform.WINDOWS, "Acceptance Windows"
                )
                await devices.register(user.id, uuid4(), DevicePlatform.WINDOWS, "Acceptance spare")
                issued = await AuthSessionService(
                    AuthSessionRepository(session), timedelta(minutes=20)
                ).issue(user.id, current.id)
                output = {
                    "email": email,
                    "access_token": AccessTokenService(config)
                    .issue(user.id, current.id, issued.session.id)
                    .token,
                    "credential": {
                        "session_id": str(issued.session.id),
                        "refresh_token": issued.refresh_token,
                        "expires_at": issued.session.expires_at.isoformat(),
                    },
                }
        if mode == "create":
            output["smtp_authentication"] = await asyncio.to_thread(smtp_observations, config)
        print(json.dumps(output))
    finally:
        await postgres.close()


asyncio.run(main())
