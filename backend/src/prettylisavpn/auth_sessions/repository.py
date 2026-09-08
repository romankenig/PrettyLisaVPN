"""Async persistence operations for authentication sessions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.auth_sessions.domain import AuthSession
from prettylisavpn.auth_sessions.model import AuthSessionRecord


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, auth_session: AuthSession) -> AuthSession:
        record = AuthSessionRecord(
            id=auth_session.id,
            user_id=auth_session.user_id,
            device_id=auth_session.device_id,
            refresh_token_hash=auth_session.refresh_token_hash,
            expires_at=auth_session.expires_at,
            revoked_at=auth_session.revoked_at,
            created_at=auth_session.created_at,
            updated_at=auth_session.updated_at,
        )
        self._session.add(record)
        await self._session.flush()
        return self._to_domain(record)

    async def get_for_update(self, session_id: UUID) -> AuthSession | None:
        statement = (
            select(AuthSessionRecord).where(AuthSessionRecord.id == session_id).with_for_update()
        )
        record = await self._session.scalar(statement)
        return self._to_domain(record) if record is not None else None

    async def get(self, session_id: UUID) -> AuthSession | None:
        record = await self._session.get(AuthSessionRecord, session_id)
        return self._to_domain(record) if record is not None else None

    async def rotate(
        self,
        session_id: UUID,
        refresh_token_hash: bytes,
        expires_at: datetime,
        updated_at: datetime,
    ) -> None:
        await self._session.execute(
            update(AuthSessionRecord)
            .where(AuthSessionRecord.id == session_id)
            .values(
                refresh_token_hash=refresh_token_hash,
                expires_at=expires_at,
                updated_at=updated_at,
            )
        )

    async def revoke(self, session_id: UUID, revoked_at: datetime) -> bool:
        revoked_id = await self._session.scalar(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.id == session_id,
                AuthSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, updated_at=revoked_at)
            .returning(AuthSessionRecord.id)
        )
        return revoked_id is not None

    async def revoke_for_device(self, device_id: UUID, revoked_at: datetime) -> int:
        revoked_ids = await self._session.scalars(
            update(AuthSessionRecord)
            .where(
                AuthSessionRecord.device_id == device_id,
                AuthSessionRecord.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, updated_at=revoked_at)
            .returning(AuthSessionRecord.id)
        )
        return len(revoked_ids.all())

    @staticmethod
    def _to_domain(record: AuthSessionRecord) -> AuthSession:
        return AuthSession(
            id=record.id,
            user_id=record.user_id,
            device_id=record.device_id,
            refresh_token_hash=record.refresh_token_hash,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
