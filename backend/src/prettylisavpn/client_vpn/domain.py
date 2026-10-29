"""Small, independently testable allocation and entitlement rules."""

import base64
import math
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface

from pydantic import Field, field_validator

from prettylisavpn.client_vpn.methods import METHODS
from prettylisavpn.fleet.domain import FleetError, Value
from prettylisavpn.subscriptions.domain import Subscription, SubscriptionPlan

HEARTBEAT_SECONDS = 30
SETUP_TIMEOUT_SECONDS = 90
NODE_TTL_SECONDS = 180


class ConnectRequest(Value):
    public_key: str = Field(pattern=r"^[A-Za-z0-9+/]{43}=$")
    country: str = Field(default="AUTO", pattern=r"^(AUTO|[A-Z]{2})$")
    method: str = "wireguard"

    @field_validator("method")
    @classmethod
    def supported_method(cls, value: str) -> str:
        if value not in METHODS:
            raise ValueError("Unsupported VPN method")
        return value

    @field_validator("public_key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32 or raw == bytes(32) or base64.b64encode(raw).decode() != value:
            raise ValueError("Invalid public key")
        return value


def deadline(subscription: Subscription, now: datetime, remaining: int) -> tuple[bool, datetime]:
    if subscription.effective_plan(now) != SubscriptionPlan.FREE:
        assert subscription.current_period_end is not None
        return False, subscription.current_period_end
    if remaining <= 0:
        raise FleetError("FREE_QUOTA_EXHAUSTED", 403)
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    return True, min(now + timedelta(seconds=remaining), midnight)


def allocate_address(configuration: dict[str, object], used: set[str]) -> str:
    subnet = IPv4Interface(str(configuration["address"])).network
    # First usable address is the server; last usable address is reserved for monitoring.
    for offset in range(2, subnet.num_addresses - 2):
        address = str(subnet.network_address + offset) + "/32"
        if address not in used:
            return address
    raise FleetError("VPN_NODE_FULL", 503)


def reserved_seconds(
    created: datetime, expires: datetime, activated: datetime | None, removed: datetime | None
) -> int:
    if removed is None:
        return math.ceil((expires - created).total_seconds())
    if activated is None:
        return 0
    return max(0, math.ceil((min(removed, expires) - max(activated, created)).total_seconds()))
