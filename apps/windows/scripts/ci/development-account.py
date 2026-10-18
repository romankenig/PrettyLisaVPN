"""Disposable acceptance account; run inside the existing development container.

The sole stdout secret is the short-lived refresh credential, consumed over SSH
by a private runner file. Never upload that file or treat this as an OTP test.
"""

import asyncio
import json
import re
import sys
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete

from prettylisavpn.auth_sessions.repository import AuthSessionRepository
from prettylisavpn.auth_sessions.service import AuthSessionService
from prettylisavpn.auth.tokens import AccessTokenService
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.domain import DevicePlatform
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.devices.service import DeviceService
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


async def main():
    mode, run = sys.argv[1:]
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
            else:
                user = await UserService(UserRepository(session), SubscriptionRepository(session)).create(email)
                devices = DeviceService(DeviceRepository(session))
                current = await devices.register(user.id, uuid4(), DevicePlatform.WINDOWS, "Acceptance Windows")
                await devices.register(user.id, uuid4(), DevicePlatform.WINDOWS, "Acceptance spare")
                issued = await AuthSessionService(AuthSessionRepository(session), timedelta(minutes=20)).issue(user.id, current.id)
                output = {"email": email, "access_token": AccessTokenService(config).issue(user.id, current.id, issued.session.id).token, "credential": {"session_id": str(issued.session.id), "refresh_token": issued.refresh_token, "expires_at": issued.session.expires_at.isoformat()}}
        print(json.dumps(output))
    finally:
        await postgres.close()


asyncio.run(main())
