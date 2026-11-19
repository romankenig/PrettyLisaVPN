"""Fixed, disjoint resources for the explicitly enrolled secondary controller."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface
from uuid import UUID, uuid4

from prettylisavpn.fleet.domain import FleetError

# The owner's first-free allocator with capacity <= 100 cannot allocate these ranges.
# Daily managed probes use 49900..49999; relay probes allocate from 29999 downwards.
OWNER_CAPACITY_LIMIT = 100
ADDRESS_START, ADDRESS_END = 128, 192
MANAGED_START, MANAGED_END = 48000, 48500
RELAY_START, RELAY_END = 28000, 28500
LEASE_PREFIX = "74657374"
SNAPSHOT_TTL = timedelta(seconds=120)


def lease_id(shared: bool) -> UUID:
    value = uuid4()
    return UUID(LEASE_PREFIX + value.hex[8:]) if shared else value


def owns_lease(identifier: UUID) -> bool:
    return identifier.hex.startswith(LEASE_PREFIX)


def snapshot_fresh(configuration: dict[str, object], now: datetime | None = None) -> bool:
    try:
        stamp = datetime.fromisoformat(str(configuration["shared_snapshot_at"]))
        current = now or datetime.now(UTC)
        return stamp.tzinfo is not None and timedelta(0) <= current - stamp < SNAPSHOT_TTL
    except (KeyError, ValueError, TypeError):
        return False


def allocate_shared_address(configuration: dict[str, object], used: set[str]) -> str:
    subnet = IPv4Interface(str(configuration["address"])).network
    if subnet.prefixlen != 24:
        raise FleetError("VPN_SHARED_SUBNET_UNSUPPORTED", 503)
    for offset in range(ADDRESS_START, ADDRESS_END):
        address = f"{subnet.network_address + offset}/32"
        if address not in used:
            return address
    raise FleetError("VPN_NODE_FULL", 503)
