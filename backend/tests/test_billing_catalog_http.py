"""Public prices have no account data, auth requirement, fallback prices or query selectors."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_billing import catalog

from prettylisavpn.billing.public_catalog import PublicCatalog
from prettylisavpn.billing.router import router
from prettylisavpn.billing.service import BillingUnavailableError


def test_anonymous_catalog_exposes_only_acquisition_offer():
    app = FastAPI()
    app.include_router(router)
    value = PublicCatalog(offers=[catalog().entries[0].offer])
    read = AsyncMock(return_value=value)
    app.state.billing_catalog = SimpleNamespace(read=read)
    with TestClient(app) as client:
        response = client.get("/billing/catalog?group_id=private&user_id=another")
    assert response.status_code == 200
    assert response.json() == value.model_dump(mode="json")
    assert response.headers["cache-control"] == "no-store"
    read.assert_awaited_once_with()


@pytest.mark.parametrize("failure", [BillingUnavailableError(), RuntimeError("private details")])
def test_catalog_outage_never_discloses_error_details_or_invents_prices(failure):
    app = FastAPI()
    app.include_router(router)
    app.state.billing_catalog = SimpleNamespace(read=AsyncMock(side_effect=failure))
    with TestClient(app) as client:
        response = client.get("/billing/catalog")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "BILLING_UNAVAILABLE"}}
    assert response.headers["cache-control"] == "no-store"
