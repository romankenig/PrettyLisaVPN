"""Real PostgreSQL/Valkey web sessions are account-scoped, short-lived and revocable."""

import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from test_subscription_access_integration import access_state as _access_state

from prettylisavpn.auth.service import BlockedUserError, InvalidOtpError
from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.billing.web_sessions import BillingWebSessions, RedisWebTokens, key
from prettylisavpn.devices.model import DeviceRecord
from prettylisavpn.users.domain import UserStatus
from prettylisavpn.users.model import UserRecord

access_state = _access_state
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires PostgreSQL/Valkey"
    ),
]


async def test_handoff_is_single_use_and_session_rechecks_blocked_account(access_state):
    _, pg, user, *_ = access_state
    async with Redis.from_url(os.environ["VALKEY_URL"], decode_responses=True) as redis:
        tokens = RedisWebTokens(redis)
        service = BillingWebSessions(pg, AsyncMock(), tokens)
        url = await service.handoff(user)
        handoff = url.split("#handoff=")[1]
        assert handoff not in key("handoff", handoff)
        results = await asyncio.gather(
            service.exchange(handoff), service.exchange(handoff), return_exceptions=True
        )
        assert sum(isinstance(value, InvalidSessionError) for value in results) == 1
        token = next(value for value in results if isinstance(value, str))
        assert await service.authenticate(token) == user
        async with pg.session() as session, session.begin():
            row = await session.get(UserRecord, user)
            row.status = UserStatus.BLOCKED
        with pytest.raises(BlockedUserError):
            await service.authenticate(token)
        await tokens.revoke(token)
        with pytest.raises(InvalidSessionError):
            await service.authenticate(token)


async def test_web_otp_does_not_register_a_vpn_device(access_state):
    _, pg, user, *_ = access_state
    async with pg.session() as session:
        email = (await session.get(UserRecord, user)).email
        before = await session.scalar(
            select(func.count()).select_from(DeviceRecord).where(DeviceRecord.user_id == user)
        )
    async with Redis.from_url(os.environ["VALKEY_URL"], decode_responses=True) as redis:
        otp = AsyncMock()
        otp.verify.return_value = False
        service = BillingWebSessions(pg, otp, RedisWebTokens(redis))
        with pytest.raises(InvalidOtpError):
            await service.login(email, "000000")
        otp.verify.return_value = True
        token = await service.login(email, "123456")
        assert await service.authenticate(token) == user
        assert 0 < await redis.ttl(key("session", token)) <= 7200
        await service.tokens.revoke(token)
    async with pg.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(DeviceRecord).where(DeviceRecord.user_id == user)
            )
            == before
        )
