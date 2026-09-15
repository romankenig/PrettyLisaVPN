"""Provider-independent, transaction-safe VPN client IPv4 allocation."""

from datetime import datetime
from ipaddress import IPv4Address, IPv4Network
from typing import Protocol


class AddressPoolExhaustedError(RuntimeError):
    """No unreserved client address is currently available."""


class VpnClientAddressAllocationPersistence(Protocol):
    async def acquire_address_allocation_lock(self) -> None: ...

    async def expire_allocations(self, at: datetime) -> None: ...

    async def list_live_allocated_ipv4(self, at: datetime) -> set[IPv4Address]: ...


class VpnClientAddressAllocation(Protocol):
    async def allocate(self, at: datetime) -> IPv4Address: ...


class VpnClientAddressAllocator:
    """Allocates the first free host while holding a transaction-scoped lock."""

    def __init__(
        self,
        repository: VpnClientAddressAllocationPersistence,
        subnet: IPv4Network,
        reserved_addresses: set[IPv4Address] | frozenset[IPv4Address],
    ) -> None:
        if subnet.version != 4:
            raise ValueError("VPN client subnet must be IPv4")
        if any(address not in subnet for address in reserved_addresses):
            raise ValueError("reserved addresses must belong to the VPN client subnet")
        self._repository = repository
        self._subnet = subnet
        self._reserved = frozenset(reserved_addresses)

    async def allocate(self, at: datetime) -> IPv4Address:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware")
        await self._repository.acquire_address_allocation_lock()
        await self._repository.expire_allocations(at)
        unavailable = self._reserved | await self._repository.list_live_allocated_ipv4(at)
        for address in self._subnet.hosts():
            if address not in unavailable:
                return address
        raise AddressPoolExhaustedError(str(self._subnet))
