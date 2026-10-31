"""Catalog authentication, bounded masks and database projection."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from prettylisavpn.auth.session_service import InvalidSessionError
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app
from prettylisavpn.traffic.service import TrafficCatalogService, TrafficService


def preset(**changes):
    return TrafficService.model_validate(
        {
            "id": "0bd811da-f080-4f25-887a-67bf534ac2c6",
            "slug": "youtube",
            "name": "YouTube",
            "icon": "youtube",
            "domains": ["youtube.com", "*.youtube.com"],
            **changes,
        }
    )


@pytest.mark.parametrize(
    "mask",
    [
        "https://youtube.com",
        "youtube.com/path",
        "y*out.be",
        "*.com",
        "127.0.0.1",
        "a..com",
        "-a.com",
        "a.com:443",
        "A.COM",
    ],
)
def test_catalog_rejects_ambiguous_masks(mask):
    with pytest.raises(ValidationError):
        preset(domains=[mask])


async def test_catalog_authenticates_before_loading_presets():
    auth, repository = AsyncMock(), AsyncMock()
    repository.list_enabled.return_value = [preset()]
    app = create_app(
        Settings(_env_file=None),
        postgres=AsyncMock(),
        valkey=AsyncMock(),
        authenticated_sessions=auth,
    )
    async with app.router.lifespan_context(app):
        app.state.traffic_catalog = TrafficCatalogService(repository, auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/vpn/traffic/services")).status_code == 401
            repository.list_enabled.assert_not_awaited()
            auth.authenticate.side_effect = InvalidSessionError()
            assert (
                await client.get(
                    "/vpn/traffic/services", headers={"Authorization": "Bearer invalid"}
                )
            ).status_code == 401
            repository.list_enabled.assert_not_awaited()
            auth.authenticate.side_effect = None
            response = await client.get(
                "/vpn/traffic/services", headers={"Authorization": "Bearer valid"}
            )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"services": [preset().model_dump(mode="json")]}
    repository.list_enabled.assert_awaited_once()


def test_catalog_preserves_exact_vs_subdomain_and_bounds():
    assert preset(domains=["youtube.com", "*.youtube.com", "youtube.com"]).domains == [
        "youtube.com",
        "*.youtube.com",
    ]
    with pytest.raises(ValidationError):
        preset(domains=["youtube.com"] * 65)


def test_catalog_categories_are_bounded_and_backward_compatible():
    assert preset().category == "popular"
    assert preset(category="whitelist").category == "whitelist"
    with pytest.raises(ValidationError):
        preset(category="unknown")


def test_service_networks_are_explicit_canonical_and_bounded():
    assert preset().ipv4_cidrs == []
    assert preset(ipv4_cidrs=["91.108.4.0/22"] * 2).ipv4_cidrs == ["91.108.4.0/22"]
    for value in [
        "91.108.4.1/22",
        "91.108.4.0",
        "0.0.0.0/0",
        "127.0.0.1/32",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "198.18.0.0/15",
        "198.0.0.0/8",
        "224.0.0.0/4",
        "2001:b28:f23d::/48",
    ]:
        with pytest.raises(ValidationError):
            preset(ipv4_cidrs=[value])
    with pytest.raises(ValidationError):
        preset(ipv4_cidrs=["91.108.4.0/22"] * 65)
