"""Billing commands and money-safe, provider-independent operation policies."""

import calendar
import hashlib
import json
from datetime import datetime
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, StrictInt, model_validator

from prettylisavpn.billing.domain import StrictModel

Action = Literal["SUBSCRIBE", "RENEW", "CHANGE_METHOD", "CANCEL"]
Currency = Literal["RUB", "USD"]
PaymentRoute = Literal["MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO"]
OperationStatus = Literal["PENDING", "SUCCEEDED", "FAILED", "CANCELED"]


class BillingCommand(StrictModel):
    action: Action
    payment_route: PaymentRoute | None
    request_id: UUID
    expected_revision: str = Field(min_length=1, max_length=128)
    offer_id: UUID | None
    currency: Currency

    @model_validator(mode="after")
    def valid_shape(self) -> Self:
        purchase = self.action in ("SUBSCRIBE", "RENEW")
        if purchase != (self.offer_id is not None) or purchase != (self.payment_route is not None):
            raise ValueError("Invalid action fields")
        return self

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class BillingOperation(StrictModel):
    id: UUID
    status: OperationStatus
    redirect_url: str | None = None


class ProviderMandate(StrictModel):
    reference: str = Field(min_length=1, max_length=200, repr=False)
    label: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def safe_summary(self) -> Self:
        if any(ord(c) < 32 or ord(c) == 127 for c in self.reference + self.label):
            raise ValueError("Invalid mandate summary")
        return self


class ProviderRequest(StrictModel):
    operation_id: UUID
    account_id: UUID
    action: Action
    payment_route: PaymentRoute | None
    amount_minor: StrictInt | None
    currency: Currency
    previous_mandate_reference: str | None = Field(default=None, repr=False)


class ProviderResult(StrictModel):
    operation_id: UUID
    status: OperationStatus
    amount_minor: StrictInt | None = Field(default=None, ge=0, le=1_000_000_000_000)
    currency: Currency | None = None
    mandate: ProviderMandate | None = Field(default=None, repr=False)
    previous_mandate_revoked: bool = False
    recurring_stopped: bool = False
    redirect_url: str | None = Field(default=None, max_length=2048, repr=False)


def safe_redirect(value: str | None, allowed_hosts: frozenset[str]) -> str | None:
    if value is None:
        return None
    if len(value) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError("Unsafe redirect")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.port not in (None, 443) or parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("Unsafe redirect")
    return value


def next_month(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware time required")
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))
