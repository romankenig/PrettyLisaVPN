"""Concurrent aliases reuse an existing account without rewriting its address/history."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from test_users_integration import pytestmark  # noqa: F401

from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.subscriptions.repository import SubscriptionRepository
from prettylisavpn.users.email_identity import DOMAIN_GROUPS, EmailAliasConflictError, email_aliases
from prettylisavpn.users.model import UserRecord
from prettylisavpn.users.repository import UserRepository
from prettylisavpn.users.service import UserService


@pytest.mark.parametrize("domains", DOMAIN_GROUPS)
@pytest.mark.parametrize("existing", [True, False])
async def test_first_address_and_one_account_survive_concurrent_alias_logins(domains, existing):
    pg = Postgres(Settings())
    local = f"alias-{uuid4().hex}"
    first_email = f"{local}@{domains[-1]}"

    async def login(email):
        async with pg.session() as session, session.begin():
            return await UserService(
                UserRepository(session), SubscriptionRepository(session)
            ).find_or_create_with_subscription(email)

    try:
        if existing:
            first, subscription, created = await login(first_email)
            assert created
        results = await asyncio.gather(*(login(f"{local.upper()}@{d}") for d in domains))
        if not existing:
            first, subscription, _ = next(result for result in results if result[2])
            first_email = first.email
        assert all(user.id == first.id and user.email == first_email for user, _, _ in results)
        assert all(sub.id == subscription.id for _, sub, _ in results)
        assert sum(new for _, _, new in results) == (0 if existing else 1)
        async with pg.session() as session:
            users = list(
                await session.scalars(
                    select(UserRecord).where(UserRecord.email.in_(email_aliases(first_email)))
                )
            )
            assert len(users) == 1
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(
                delete(UserRecord).where(UserRecord.email.in_(email_aliases(first_email)))
            )
        await pg.close()


async def test_legacy_duplicates_keep_exact_access_but_cannot_spawn_a_third_account():
    pg = Postgres(Settings())
    local = f"legacy-{uuid4().hex}"
    emails = [f"{local}@yandex.com", f"{local}@yandex.ru"]
    try:
        async with pg.session() as session, session.begin():
            session.add_all([UserRecord(email=email) for email in emails])
        async with pg.session() as session, session.begin():
            repo = UserRepository(session)
            first = await repo.get_by_email_for_update(emails[0])
            second = await repo.get_by_email_for_update(emails[1])
            assert first.id != second.id
            assert first.email == emails[0] and second.email == emails[1]
            with pytest.raises(EmailAliasConflictError):
                await UserService(
                    repo, SubscriptionRepository(session)
                ).find_or_create_with_subscription(f"{local}@ya.ru")
    finally:
        async with pg.session() as session, session.begin():
            await session.execute(delete(UserRecord).where(UserRecord.email.in_(emails)))
        await pg.close()
