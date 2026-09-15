"""Provider-independent VPN client address allocation tests."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network

import pytest
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.vpn_sessions.address_allocation import (
    AddressPoolExhaustedError,
    VpnClientAddressAllocator,
)

NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


class FakeAllocationRepository:
    def __init__(self, live: set[IPv4Address] | None = None) -> None:
        self.live = live or set()
        self.expired: set[IPv4Address] = set()
        self.lock_calls = 0
        self.expire_calls: list[datetime] = []

    async def acquire_address_allocation_lock(self) -> None:
        self.lock_calls += 1

    async def expire_allocations(self, at: datetime) -> None:
        self.expire_calls.append(at)
        self.live.difference_update(self.expired)

    async def list_live_allocated_ipv4(self, at: datetime) -> set[IPv4Address]:
        return set(self.live)


async def test_allocates_first_free_address_and_reserves_gateway():
    repository = FakeAllocationRepository()
    allocator = VpnClientAddressAllocator(
        repository, IPv4Network("10.77.0.0/29"), {IPv4Address("10.77.0.1")}
    )

    allocated = await allocator.allocate(NOW)

    assert allocated == IPv4Address("10.77.0.2")
    assert repository.lock_calls == 1
    assert repository.expire_calls == [NOW]


async def test_skips_live_allocations():
    repository = FakeAllocationRepository({IPv4Address("10.77.0.2"), IPv4Address("10.77.0.3")})
    allocator = VpnClientAddressAllocator(
        repository, IPv4Network("10.77.0.0/29"), {IPv4Address("10.77.0.1")}
    )

    assert await allocator.allocate(NOW) == IPv4Address("10.77.0.4")


async def test_reuses_address_after_release_or_expiry():
    repository = FakeAllocationRepository({IPv4Address("10.77.0.2")})
    allocator = VpnClientAddressAllocator(
        repository, IPv4Network("10.77.0.0/30"), {IPv4Address("10.77.0.1")}
    )
    repository.expired.add(IPv4Address("10.77.0.2"))

    assert await allocator.allocate(NOW + timedelta(minutes=16)) == IPv4Address("10.77.0.2")


async def test_pool_exhaustion_is_explicit():
    repository = FakeAllocationRepository({IPv4Address("10.77.0.2")})
    allocator = VpnClientAddressAllocator(
        repository, IPv4Network("10.77.0.0/30"), {IPv4Address("10.77.0.1")}
    )

    with pytest.raises(AddressPoolExhaustedError, match="10.77.0.0/30"):
        await allocator.allocate(NOW)


def test_rejects_reserved_address_outside_pool():
    with pytest.raises(ValueError, match="reserved addresses"):
        VpnClientAddressAllocator(
            FakeAllocationRepository(),
            IPv4Network("10.77.0.0/24"),
            {IPv4Address("10.88.0.1")},
        )


def test_client_subnet_and_gateway_are_configurable_and_consistent():
    settings = Settings(
        _env_file=None,
        vpn_client_subnet="10.99.0.0/24",
        vpn_client_gateway_ipv4="10.99.0.1",
    )

    assert settings.vpn_client_subnet == IPv4Network("10.99.0.0/24")
    assert settings.vpn_client_gateway_ipv4 == IPv4Address("10.99.0.1")

    with pytest.raises(ValidationError, match="usable address"):
        Settings(
            _env_file=None,
            vpn_client_subnet="10.99.0.0/24",
            vpn_client_gateway_ipv4="10.88.0.1",
        )
