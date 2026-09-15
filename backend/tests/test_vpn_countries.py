"""Authenticated VPN country availability endpoint and service tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from prettylisavpn.auth.session_service import InvalidSessionError, MeSummary
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.subscriptions.domain import SubscriptionPlan
from prettylisavpn.vpn_nodes.availability import VpnNodeCapacitySnapshot
from prettylisavpn.vpn_nodes.countries import (
    AutopilotEligibility,
    VpnCountryAvailability,
    VpnCountryAvailabilityService,
)
from prettylisavpn.vpn_nodes.domain import (
    VpnNode,
    VpnNodeHealthStatus,
    VpnNodeProvider,
    VpnNodeStatus,
)
from prettylisavpn.vpn_nodes.selection import CountryEligibility, VpnNodeSelectionService

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
STALE_TIMEOUT = timedelta(seconds=100)
PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def dependency() -> AsyncMock:
    result = AsyncMock()
    result.ping.return_value = True
    return result


def api_client(service: AsyncMock) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                otp_hmac_secret="vpn-country-test-secret-at-least-32-characters",
            ),
            postgres=dependency(),
            valkey=dependency(),
            otp_service=AsyncMock(),
            product_events=AsyncMock(),
            authenticated_sessions=AsyncMock(),
            vpn_country_availability=service,
        )
    )


def make_node(node_id: int, country_code: str = "DE", **changes: object) -> VpnNode:
    node = VpnNode(
        id=UUID(int=node_id),
        name=f"internal-node-{node_id}",
        provider=VpnNodeProvider.DIGITALOCEAN,
        provider_region="fra1",
        country_code=country_code,
        city="Frankfurt",
        public_ipv4=IPv4Address(f"203.0.113.{node_id}"),
        private_ipv4=None,
        wireguard_port=51820,
        wireguard_public_key=PUBLIC_KEY,
        capacity=100,
        status=VpnNodeStatus.ACTIVE,
        last_seen_at=NOW,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
        health_status=VpnNodeHealthStatus.HEALTHY,
        health_checked_at=NOW,
        is_available_for_free=True,
    )
    return replace(node, **changes)


class MutableCapacityRepository:
    def __init__(self, snapshots: list[VpnNodeCapacitySnapshot]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    async def list_capacity_snapshots(
        self,
        country_code: str | None = None,
        *,
        at: datetime,
        lock_nodes: bool = False,
    ) -> list[VpnNodeCapacitySnapshot]:
        self.calls += 1
        return [
            snapshot
            for snapshot in self.snapshots
            if country_code is None or snapshot.node.country_code == country_code
        ]


def authenticated_user(plan: SubscriptionPlan) -> AsyncMock:
    sessions = AsyncMock()
    sessions.me.return_value = MeSummary(uuid4(), "user@example.com", plan, 1)
    return sessions


def test_endpoint_returns_only_product_level_country_information():
    service = AsyncMock()
    service.list_countries.return_value = VpnCountryAvailability(
        autopilot=AutopilotEligibility(True, 92),
        countries=(
            CountryEligibility("DE", True, 81),
            CountryEligibility("US", False, 0),
        ),
    )

    with api_client(service) as client:
        response = client.get("/vpn/countries", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json() == {
        "autopilot": {"quality": 92, "available": True},
        "countries": [
            {"country_code": "DE", "quality": 81, "available": True},
            {"country_code": "US", "quality": 0, "available": False},
        ],
    }
    forbidden = {
        "node_id",
        "node_name",
        "node_count",
        "provider",
        "provider_region",
        "public_ipv4",
        "private_ipv4",
        "capacity",
        "node_score",
        "wireguard_endpoint",
    }
    assert forbidden.isdisjoint(response.text.split('"'))
    service.list_countries.assert_awaited_once_with("access-token")


def test_endpoint_requires_authentication():
    service = AsyncMock()
    with api_client(service) as client:
        response = client.get("/vpn/countries")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "authentication_required"}}
    service.list_countries.assert_not_awaited()


def test_endpoint_maps_invalid_authenticated_session_without_echoing_token():
    service = AsyncMock()
    service.list_countries.side_effect = InvalidSessionError
    with api_client(service) as client:
        response = client.get("/vpn/countries", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "invalid_session"}}
    assert "secret-token" not in response.text


async def test_service_personalizes_mixed_eligibility_for_free_and_premium():
    repository = MutableCapacityRepository(
        [
            VpnNodeCapacitySnapshot(make_node(1, is_available_for_free=True), 80),
            VpnNodeCapacitySnapshot(make_node(2, is_available_for_free=False), 0),
            VpnNodeCapacitySnapshot(make_node(3, "US"), 50),
        ]
    )
    catalog = VpnNodeSelectionService(repository, STALE_TIMEOUT)

    free = await VpnCountryAvailabilityService(
        authenticated_user(SubscriptionPlan.FREE), catalog, lambda: NOW
    ).list_countries("free-token")
    premium = await VpnCountryAvailabilityService(
        authenticated_user(SubscriptionPlan.PREMIUM), catalog, lambda: NOW
    ).list_countries("premium-token")

    assert free.countries == (
        CountryEligibility("DE", True, 20),
        CountryEligibility("US", True, 50),
    )
    assert premium.countries == (
        CountryEligibility("DE", True, 100),
        CountryEligibility("US", True, 50),
    )
    assert free.autopilot == AutopilotEligibility(True, 50)
    assert premium.autopilot == AutopilotEligibility(True, 100)
    assert repository.calls == 2


async def test_service_reflects_changing_health_and_capacity_snapshots():
    repository = MutableCapacityRepository([VpnNodeCapacitySnapshot(make_node(1), 100)])
    catalog = VpnNodeSelectionService(repository, STALE_TIMEOUT)
    service = VpnCountryAvailabilityService(
        authenticated_user(SubscriptionPlan.FREE), catalog, lambda: NOW
    )

    full = await service.list_countries("token")
    repository.snapshots = [
        VpnNodeCapacitySnapshot(make_node(1, health_status=VpnNodeHealthStatus.UNHEALTHY), 0)
    ]
    unhealthy = await service.list_countries("token")
    repository.snapshots = [VpnNodeCapacitySnapshot(make_node(1), 25)]
    recovered = await service.list_countries("token")

    assert full.countries == (CountryEligibility("DE", False, 0),)
    assert full.autopilot == AutopilotEligibility(False, 0)
    assert unhealthy.countries == (CountryEligibility("DE", False, 0),)
    assert recovered.countries == (CountryEligibility("DE", True, 75),)
    assert recovered.autopilot == AutopilotEligibility(True, 75)


async def test_autopilot_is_best_country_opportunity_not_country_average():
    repository = MutableCapacityRepository(
        [
            VpnNodeCapacitySnapshot(make_node(1, "DE"), 10),
            VpnNodeCapacitySnapshot(make_node(2, "US"), 90),
        ]
    )
    service = VpnCountryAvailabilityService(
        authenticated_user(SubscriptionPlan.PREMIUM),
        VpnNodeSelectionService(repository, STALE_TIMEOUT),
        lambda: NOW,
    )

    result = await service.list_countries("token")

    assert [country.quality for country in result.countries] == [90, 10]
    assert result.autopilot == AutopilotEligibility(True, 90)
    assert result.autopilot.quality != 50
    assert repository.calls == 1
