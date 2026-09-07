"""Async persistence operations for users."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.users.domain import User, normalize_email
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
        statement = select(UserRecord).where(UserRecord.email == normalize_email(email))
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    @staticmethod
    def _to_domain(record: UserRecord) -> User:
        return User(
            id=record.id,
            email=record.email,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
