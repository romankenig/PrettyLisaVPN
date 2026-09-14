"""VPN node domain tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv6Address
from uuid import uuid4

import pytest

from prettylisavpn.vpn_nodes.domain import VpnNode, VpnNodeProvider, VpnNodeStatus

PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def make_node(**changes: object) -> VpnNode:
    now = datetime.now(UTC)
    node = VpnNode(
        id=uuid4(),
        name="nyc1-01",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="nyc1",
        country_code="US",
        city="New York",
        public_ipv4=IPv4Address("203.0.113.10"),
        private_ipv4=IPv4Address("10.10.0.5"),
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=100,
        status=VpnNodeStatus.OFFLINE,
        last_seen_at=None,
        created_at=now,
        updated_at=now,
    )
    return replace(node, **changes)


def test_normalizes_provider_agnostic_metadata_and_utc_times():
    offset_time = (datetime.now(UTC) + timedelta(minutes=1)).astimezone(
        timezone(timedelta(hours=3))
    )
    node = make_node(
        name="  nyc1-01  ",
        provider_region="  nyc1  ",
        country_code=" us ",
        city="  New York  ",
        last_seen_at=offset_time,
        updated_at=offset_time,
    )

    assert node.name == "nyc1-01"
    assert node.provider_region == "nyc1"
    assert node.country_code == "US"
    assert node.city == "New York"
    assert node.last_seen_at is not None
    assert node.last_seen_at.tzinfo is UTC


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"name": " "}, "name must not be empty"),
        ({"provider_region": " "}, "provider_region must not be empty"),
        ({"country_code": "USA"}, "country_code must be a two-letter ASCII code"),
        ({"city": " "}, "city must not be empty"),
        ({"public_ipv4": IPv6Address("2001:db8::1")}, "public_ipv4 must be an IPv4 address"),
        ({"private_ipv4": IPv6Address("fd00::1")}, "private_ipv4 must be an IPv4 address"),
        ({"wireguard_port": 0}, "wireguard_port must be between 1 and 65535"),
        ({"wireguard_port": 65536}, "wireguard_port must be between 1 and 65535"),
        ({"wireguard_public_key": "private-key"}, "must be valid base64"),
        ({"capacity": 0}, "capacity must be positive"),
        ({"created_at": datetime.now()}, "created_at must be timezone-aware"),
    ],
)
def test_rejects_invalid_metadata(changes: dict[str, object], message: str):
    with pytest.raises(ValueError, match=message):
        make_node(**changes)


def test_rejects_updated_time_before_created_time():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="updated_at must not be before created_at"):
        make_node(created_at=now, updated_at=now - timedelta(seconds=1))
