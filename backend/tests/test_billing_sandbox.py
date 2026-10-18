"""Sandbox receipt policies and explicit environment guards."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from prettylisavpn.billing.operations_domain import ProviderRequest
from prettylisavpn.billing.sandbox import SandboxBillingProvider, deliver, simulated_result
from prettylisavpn.billing.worker import BillingWorker
from prettylisavpn.config import Settings
from prettylisavpn.main import create_app


def request(**changes):
    return ProviderRequest.model_validate(
        {
            "operation_id": uuid4(),
            "account_id": uuid4(),
            "action": "SUBSCRIBE",
            "payment_route": "MIR",
            "amount_minor": 19900,
            "currency": "RUB",
            **changes,
        }
    )


@pytest.mark.parametrize("status", ["PENDING", "SUCCEEDED", "FAILED", "CANCELED"])
@pytest.mark.parametrize("route", ["MIR", "BANK_CARD", "CRYPTO", "ALIPAY_WECHAT"])
def test_receipt_uses_only_accepted_money_and_never_redirects_to_a_payment_site(status, route):
    accepted = request(payment_route=route)
    result = simulated_result(accepted, status)
    assert result.operation_id == accepted.operation_id
    assert result.status == status and result.redirect_url is None
    if status == "SUCCEEDED":
        BillingWorker._validate_confirmation(accepted, result)
        assert result.amount_minor == 19900 and result.currency == "RUB"
        assert bool(result.mandate) == (route in ("MIR", "BANK_CARD"))
        assert simulated_result(accepted, status) == result
    else:
        assert result.amount_minor is result.currency is result.mandate is None
        assert not result.recurring_stopped and not result.previous_mandate_revoked


@pytest.mark.parametrize("action", ["CANCEL", "CHANGE_METHOD"])
def test_nonmonetary_actions_confirm_mandate_state(action):
    accepted = request(
        action=action, payment_route=None, amount_minor=None, previous_mandate_reference="old"
    )
    result = simulated_result(accepted, "SUCCEEDED")
    BillingWorker._validate_confirmation(accepted, result)
    assert result.amount_minor is None and result.currency is None


@pytest.mark.parametrize("environment", ["production", "staging", "Development"])
def test_sandbox_cannot_be_configured_or_injected_outside_allowed_environments(environment):
    with pytest.raises(ValidationError, match="Sandbox billing"):
        Settings(_env_file=None, environment=environment, billing_provider="sandbox")
    config = Settings(_env_file=None).model_copy(update={"environment": environment})
    with pytest.raises(ValueError, match="Sandbox billing"):
        SandboxBillingProvider(AsyncMock(), config)
    provider = SandboxBillingProvider(AsyncMock(), Settings(_env_file=None))
    with pytest.raises(ValueError, match="Sandbox billing"):
        create_app(config, billing_provider=provider)


def test_default_is_disabled_and_unknown_adapter_is_rejected():
    assert Settings(_env_file=None).billing_provider == "disabled"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, billing_provider="live")


async def test_cli_requires_explicit_sandbox_selection_before_connecting():
    with pytest.raises(ValueError, match="explicitly"):
        await deliver(Settings(_env_file=None), uuid4(), uuid4(), "SUCCEEDED")


async def test_invalid_notification_never_connects():
    postgres = AsyncMock()
    provider = SandboxBillingProvider(postgres, Settings(_env_file=None))
    with pytest.raises(ValueError, match="status"):
        await provider.notify(uuid4(), uuid4(), "PENDING")
    postgres.session.assert_not_called()
