"""Opt-in managed transport issuance, owned by an existing authenticated VPN session."""

import hashlib
import hmac
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.config import Settings
from prettylisavpn.connections import Postgres
from prettylisavpn.devices.repository import DeviceRepository
from prettylisavpn.vpn_nodes.agent import (
    ManagedNodeCandidate,
    ManagedNodePort,
    NodeAgentUnavailableError,
)
from prettylisavpn.vpn_nodes.repository import VpnNodeRepository
from prettylisavpn.vpn_sessions.domain import VpnSessionStatus
from prettylisavpn.vpn_sessions.model import ManagedVpnLeaseRecord
from prettylisavpn.vpn_sessions.repository import VpnSessionRepository


class ManagedVpnUnavailable(RuntimeError):
    pass


class ManagedVpnNotFound(LookupError):
    pass


class ManagedProfileResponse(BaseModel):
    version: Literal[1] = 1
    session: UUID
    country: Literal["DE", "US"]
    method: Literal["VLESS_REALITY"] = "VLESS_REALITY"
    server: IPv4Address
    port: int
    secret: str = Field(repr=False)
    server_name: str
    public_key: str
    short_id: str


class ManagedVpnResponse(BaseModel):
    profile: ManagedProfileResponse = Field(repr=False)
    expires_at: datetime
    server_time: datetime


class ManagedPlanProfile(ManagedNodeCandidate):
    version: Literal[1] = 1
    session: UUID
    country: Literal["DE", "US"]
    server: IPv4Address


class ManagedPlanResponse(BaseModel):
    profiles: list[ManagedPlanProfile] = Field(repr=False)
    expires_at: datetime
    server_time: datetime


class ManagedVpnPort(Protocol):
    async def issue(self, access_token: str, session_id: UUID) -> ManagedVpnResponse: ...
    async def issue_plan(self, access_token: str, session_id: UUID) -> ManagedPlanResponse: ...


def credential(secret: str, session_id: UUID, node_id: UUID) -> str:
    # Separate purpose/domain; neither public session IDs nor WG public keys are credentials.
    digest = hmac.digest(
        secret.encode(),
        b"PrettyLisaVPN/managed/v1\0" + session_id.bytes + node_id.bytes,
        hashlib.sha256,
    )
    return str(UUID(bytes=digest[:16], version=4))


def lease_deadline(now: datetime, session_expiry: datetime | None) -> datetime:
    end = now + timedelta(minutes=15)
    return min(end, session_expiry) if session_expiry is not None else end


class ManagedVpnService:
    def __init__(
        self,
        postgres: Postgres,
        auth: AuthenticatedSessionHandler,
        agent: ManagedNodePort | None,
        settings: Settings,
    ) -> None:
        self.pg = postgres
        self.auth = auth
        self.agent = agent
        self.nodes = set(settings.vpn_managed_nodes)
        self.secret = settings.vpn_managed_secret

    async def issue(self, access_token: str, session_id: UUID) -> ManagedVpnResponse:
        result = await self._issue(access_token, session_id, plan=False)
        assert isinstance(result, ManagedVpnResponse)
        return result

    async def issue_plan(self, access_token: str, session_id: UUID) -> ManagedPlanResponse:
        result = await self._issue(access_token, session_id, plan=True)
        assert isinstance(result, ManagedPlanResponse)
        return result

    async def _issue(
        self, access_token: str, session_id: UUID, *, plan: bool
    ) -> ManagedVpnResponse | ManagedPlanResponse:
        identity = await self.auth.authenticate(access_token)
        if self.agent is None or self.secret is None or not self.nodes:
            raise ManagedVpnUnavailable
        try:
            # Persist intent BEFORE touching the node, so lost replies/DB failures are recoverable.
            async with self.pg.session() as db:
                async with db.begin():
                    device = await DeviceRepository(db).get_for_update(identity.device_id)
                    if device is None or not device.is_active():
                        raise ManagedVpnNotFound
                    repo = VpnSessionRepository(db)
                    await repo.reconcile_paid_access(datetime.now(UTC), identity.user_id)
                    session = await repo.get_owned_for_update(
                        session_id, identity.user_id, identity.device_id
                    )
                    now = datetime.now(UTC)
                    if session is None or session.status is not VpnSessionStatus.ACTIVE:
                        raise ManagedVpnNotFound
                    if session.expires_at is not None and session.expires_at <= now:
                        raise ManagedVpnUnavailable
                    node = await VpnNodeRepository(db).get(session.vpn_node_id)
                    if (
                        node is None
                        or node.id not in self.nodes
                        or node.country_code not in ("DE", "US")
                    ):
                        raise ManagedVpnUnavailable
                    lease = await db.get(ManagedVpnLeaseRecord, session.id, with_for_update=True)
                    if lease is None:
                        expires = lease_deadline(now, session.expires_at)
                        lease = ManagedVpnLeaseRecord(
                            session_id=session.id, created_at=now, expires_at=expires
                        )
                        db.add(lease)
                        # Bound both node and control plane; repeated POST never extends the lease.
                        await repo.update(replace(session, expires_at=expires, updated_at=now))
                    if lease.revoked_at is not None or lease.expires_at <= now:
                        raise ManagedVpnUnavailable
                    expires = lease.expires_at
            async with self.pg.session() as db:
                async with db.begin():
                    device = await DeviceRepository(db).get_for_update(identity.device_id)
                    session = await VpnSessionRepository(db).get_owned_for_update(
                        session_id, identity.user_id, identity.device_id
                    )
                    lease = await db.get(ManagedVpnLeaseRecord, session_id, with_for_update=True)
                    now = datetime.now(UTC)
                    if (
                        device is None
                        or not device.is_active()
                        or session is None
                        or session.status is not VpnSessionStatus.ACTIVE
                        or (session.expires_at is not None and session.expires_at <= now)
                        or lease is None
                        or lease.revoked_at is not None
                        or lease.expires_at <= now
                    ):
                        raise ManagedVpnUnavailable
                    password = credential(self.secret.get_secret_value(), session.id, node.id)
                    # Same session lock as revoke; a late create cannot pass a confirmed removal.
                    if plan:
                        candidates = await self.agent.issue_managed_plan(
                            node, session.id, password, expires
                        )
                    else:
                        result = await self.agent.issue_managed(node, session.id, password, expires)
                    lease.issued_at = now
                if plan:
                    return ManagedPlanResponse(
                        expires_at=expires,
                        server_time=datetime.now(UTC),
                        profiles=[
                            ManagedPlanProfile(
                                session=session.id,
                                country=node.country_code,
                                server=node.public_ipv4,
                                **p.model_dump(),
                            )
                            for p in candidates.profiles
                        ],
                    )
                return ManagedVpnResponse(
                    expires_at=expires,
                    server_time=datetime.now(UTC),
                    profile=ManagedProfileResponse(
                        session=session.id,
                        country=node.country_code,
                        server=node.public_ipv4,
                        secret=password,
                        **result.model_dump(),
                    ),
                )
        except (SQLAlchemyError, NodeAgentUnavailableError):
            raise ManagedVpnUnavailable from None
