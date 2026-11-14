"""Async persistence operations for users."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.users.domain import User, normalize_email
from prettylisavpn.users.email_identity import (
    EmailAliasConflictError,
    email_aliases,
    email_identity,
)
from prettylisavpn.users.model import UserRecord


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        record = UserRecord(
            id=user.id,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def get_by_email(self, email: str) -> User | None:
        return await self._find_email(email, for_update=False)

    async def _find_email(self, email: str, *, for_update: bool) -> User | None:
        statement = (
            select(UserRecord)
            .where(UserRecord.email.in_(email_aliases(email)))
            .order_by(UserRecord.created_at, UserRecord.id)
        )
        if for_update:
            statement = statement.with_for_update()
        records = list(await self._session.scalars(statement))
        if len(records) > 1:
            # Preserve access to legacy accounts and all billing/quota history.
            # A third alias cannot select an arbitrary account or create another.
            exact = next((row for row in records if row.email == normalize_email(email)), None)
            if exact is None:
                raise EmailAliasConflictError
            return self._to_domain(exact)
        return self._to_domain(records[0]) if records else None

    async def get_by_id(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(UserRecord).where(UserRecord.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def lock_identity(self, email: str) -> None:
        """Serialize all equivalent addresses, including concurrent first logins."""
        normalized_email = email_identity(email)
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(normalized_email, 0)))
        )

    async def get_by_email_for_update(self, email: str) -> User | None:
        return await self._find_email(email, for_update=True)

    @staticmethod
    def _to_domain(record: UserRecord) -> User:
        return User(
            id=record.id,
            email=record.email,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
