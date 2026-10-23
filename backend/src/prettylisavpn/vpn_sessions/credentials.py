"""Transactional credential ledger, not a public issuance/authorization service.

Callers own the transaction and must commit reservations before invoking a signer,
and commit issued results before delivery. Network operations never belong here.
The future authenticated service must validate CSR/certificate and entitlements.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prettylisavpn.vpn_sessions.model import VpnCredentialRecord, VpnSessionRecord


class CredentialLedgerError(ValueError):
    """Closed codes without credential or database content."""


@dataclass(frozen=True)
class CredentialSnapshot:
    id: UUID
    session_id: UUID
    vpn_node_id: UUID
    authority_sha256: str
    request_sha256: str
    expires_at: datetime
    created_at: datetime
    issued_at: datetime | None
    revoked_at: datetime | None
    node_removed_at: datetime | None
    certificate_pem: bytes | None = field(repr=False)


def _snapshot(record: VpnCredentialRecord) -> CredentialSnapshot:
    return CredentialSnapshot(
        record.id,
        record.session_id,
        record.vpn_node_id,
        record.authority_sha256,
        record.request_sha256,
        record.expires_at,
        record.created_at,
        record.issued_at,
        record.revoked_at,
        record.node_removed_at,
        record.certificate_pem,
    )


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise CredentialLedgerError("INVALID_TIME")
    return value.astimezone(UTC)


class VpnCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        credential_id: UUID,
        session_id: UUID,
        authority_sha256: str,
        request_sha256: str,
        expires_at: datetime,
        now: datetime,
    ) -> CredentialSnapshot:
        now, expires_at = _utc(now), _utc(expires_at)
        if (
            not credential_id.int
            or not session_id.int
            or not now < expires_at <= now + timedelta(hours=1)
            or re.fullmatch(r"[0-9a-f]{64}", authority_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None
        ):
            raise CredentialLedgerError("INVALID_RESERVATION")
        vpn = await self._session.get(VpnSessionRecord, session_id)
        if vpn is None:
            raise CredentialLedgerError("SESSION_NOT_FOUND")
        # ON CONFLICT waits for a concurrent reservation's commit/rollback.
        await self._session.execute(
            insert(VpnCredentialRecord)
            .values(
                id=credential_id,
                session_id=session_id,
                vpn_node_id=vpn.vpn_node_id,
                authority_sha256=authority_sha256,
                request_sha256=request_sha256,
                expires_at=expires_at,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        row = await self._locked(credential_id, session_id)
        if (row.authority_sha256, row.request_sha256, row.expires_at, row.vpn_node_id) != (
            authority_sha256,
            request_sha256,
            expires_at,
            vpn.vpn_node_id,
        ):
            raise CredentialLedgerError("CREDENTIAL_REQUEST_CONFLICT")
        return _snapshot(row)

    async def get(self, credential_id: UUID, session_id: UUID) -> CredentialSnapshot | None:
        row = await self._session.scalar(
            select(VpnCredentialRecord).where(
                VpnCredentialRecord.id == credential_id,
                VpnCredentialRecord.session_id == session_id,
            )
        )
        return None if row is None else _snapshot(row)

    async def _locked(self, credential_id: UUID, session_id: UUID) -> VpnCredentialRecord:
        row = await self._session.scalar(
            select(VpnCredentialRecord)
            .where(
                VpnCredentialRecord.id == credential_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.session_id != session_id:
            raise CredentialLedgerError("CREDENTIAL_NOT_FOUND")
        return row

    async def record_issued(
        self,
        credential_id: UUID,
        session_id: UUID,
        *,
        certificate_pem: bytes,
        now: datetime,
    ) -> CredentialSnapshot:
        """Store an already verified signer result; never invoke a signer on retry."""
        now = _utc(now)
        row = await self._locked(credential_id, session_id)
        if row.revoked_at is not None or not row.created_at <= now < row.expires_at:
            raise CredentialLedgerError("CREDENTIAL_NOT_ISSUABLE")
        if not 0 < len(certificate_pem) <= 16384:
            raise CredentialLedgerError("INVALID_CERTIFICATE_SIZE")
        if row.certificate_pem is not None:
            if row.certificate_pem != certificate_pem:
                raise CredentialLedgerError("CREDENTIAL_RESULT_CONFLICT")
            return _snapshot(row)
        row.certificate_pem, row.issued_at = certificate_pem, now
        await self._session.flush()
        return _snapshot(row)

    async def revoke(
        self,
        credential_id: UUID,
        session_id: UUID,
        *,
        now: datetime,
    ) -> CredentialSnapshot:
        now = _utc(now)
        row = await self._locked(credential_id, session_id)
        if now < row.created_at:
            raise CredentialLedgerError("INVALID_TIME")
        if row.revoked_at is None:
            row.revoked_at = now
            await self._session.flush()
        return _snapshot(row)

    async def confirm_removed(
        self,
        credential_id: UUID,
        session_id: UUID,
        *,
        vpn_node_id: UUID,
        authority_sha256: str,
        now: datetime,
    ) -> CredentialSnapshot:
        """Record a validated node ACK for CRL application AND active-client removal.

        The authenticated node adapter is responsible for validating that ACK.
        A timeout, CRL upload alone or an expired certificate is not confirmation.
        """
        now = _utc(now)
        row = await self._locked(credential_id, session_id)
        if (
            row.vpn_node_id != vpn_node_id
            or row.authority_sha256 != authority_sha256
            or row.revoked_at is None
            or now < row.revoked_at
        ):
            raise CredentialLedgerError("INVALID_REMOVAL_ACK")
        if row.node_removed_at is None:
            row.node_removed_at = now
            await self._session.flush()
        return _snapshot(row)

    async def pending_revocations(self, *, limit: int = 100) -> tuple[CredentialSnapshot, ...]:
        if not 1 <= limit <= 1000:
            raise CredentialLedgerError("INVALID_LIMIT")
        rows = await self._session.scalars(
            select(VpnCredentialRecord)
            .where(
                VpnCredentialRecord.revoked_at.is_not(None),
                VpnCredentialRecord.node_removed_at.is_(None),
            )
            .order_by(VpnCredentialRecord.revoked_at, VpnCredentialRecord.id)
            .limit(limit)
        )
        return tuple(_snapshot(row) for row in rows)

    async def revocation_snapshot(
        self,
        vpn_node_id: UUID,
        authority_sha256: str,
    ) -> tuple[CredentialSnapshot, ...]:
        """Full authority-scoped CRL input, including already confirmed removals.

        Publishing workers still need durable CRL sequence/version coordination.
        """
        rows = await self._session.scalars(
            select(VpnCredentialRecord)
            .where(
                VpnCredentialRecord.vpn_node_id == vpn_node_id,
                VpnCredentialRecord.authority_sha256 == authority_sha256,
                VpnCredentialRecord.revoked_at.is_not(None),
            )
            .order_by(VpnCredentialRecord.id)
        )
        return tuple(_snapshot(row) for row in rows)
