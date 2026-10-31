"""Bounded authenticated catalog, independent of any VPN transport."""

import re
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from prettylisavpn.auth.session_service import AuthenticatedSessionHandler
from prettylisavpn.connections import Postgres
from prettylisavpn.traffic.model import TrafficServiceRecord


class TrafficService(BaseModel):
    id: UUID
    slug: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    icon: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
    category: Literal["popular", "whitelist"] = "popular"
    domains: Annotated[list[str], Field(min_length=1, max_length=64)]

    @field_validator("domains")
    @classmethod
    def valid_domains(cls, values: list[str]) -> list[str]:
        for value in values:
            host = value.removeprefix("*.")
            if (
                len(host) > 253
                or "." not in host
                or not re.fullmatch(r"[a-z0-9.-]+", host)
                or not re.search(r"[a-z]", host.rsplit(".", 1)[1])
                or any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in host.split(".")
                )
            ):
                raise ValueError("Invalid service domain mask")
        return list(dict.fromkeys(values))


class TrafficCatalog(BaseModel):
    services: Annotated[list[TrafficService], Field(max_length=64)]


class CatalogRepository(Protocol):
    async def list_enabled(self) -> list[TrafficService]: ...


class DatabaseCatalog:
    def __init__(self, postgres: Postgres) -> None:
        self.postgres = postgres

    async def list_enabled(self) -> list[TrafficService]:
        async with self.postgres.session() as session:
            rows = await session.scalars(
                select(TrafficServiceRecord)
                .where(TrafficServiceRecord.enabled.is_(True))
                .order_by(TrafficServiceRecord.slug)
                .limit(65)
            )
            return [TrafficService.model_validate(row, from_attributes=True) for row in rows]


class TrafficCatalogService:
    def __init__(self, repository: CatalogRepository, auth: AuthenticatedSessionHandler) -> None:
        self.repository, self.auth = repository, auth

    async def catalog(self, token: str) -> TrafficCatalog:
        await self.auth.authenticate(token)
        return TrafficCatalog(services=await self.repository.list_enabled())
