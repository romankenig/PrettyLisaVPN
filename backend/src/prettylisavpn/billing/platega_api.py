"""Server-only Platega transport. A timeout never authorizes another create.

Contract: docs.platega.io, monthly SBP subscriptions, reviewed 2026-11-06.
Responses are reduced to business evidence; provider bodies/headers are never logged.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr


class PlategaUnavailable(RuntimeError):
    pass


def minor_units(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("Invalid payment amount")
    amount = Decimal(value) * 100
    if not amount.is_finite() or amount != amount.to_integral_value() or not 0 < amount <= 10**12:
        raise ValueError("Invalid payment amount")
    return int(amount)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)


class PlategaSubscription(Evidence):
    id: UUID
    status: Literal["PendingAgreement", "Active", "PastDue", "Cancelled", "Failed"]
    amount_minor: int = Field(gt=0, le=10**12)
    currency: Literal["RUB"]
    next_charge_at: AwareDatetime | None
    last_charge_at: AwareDatetime | None
    description: str = Field(repr=False)
    created_at: AwareDatetime
    successful_charges: int = Field(ge=0)


class PlategaPayment(Evidence):
    id: UUID
    status: Literal[
        "PENDING", "CONFIRMED", "CANCELED", "CHARGEBACKED", "PARTIALLY_REFUNDED", "DISPUTED"
    ]
    amount_minor: int = Field(gt=0, le=10**12)
    currency: Literal["RUB"]
    description: str | None = Field(default=None, repr=False)


class CreatedSubscription(Evidence):
    id: UUID
    redirect: str = Field(repr=False)


class PaymentLink(Evidence):
    id: UUID
    url: str = Field(repr=False)
    operation_id: UUID
    amount_minor: int
    active: bool


class PlategaPort(Protocol):
    async def create(
        self, operation_id: UUID, amount_minor: int, email: str
    ) -> CreatedSubscription: ...
    async def subscription(self, subscription_id: UUID) -> PlategaSubscription: ...
    async def payment(self, payment_id: UUID) -> PlategaPayment: ...
    async def cancel(self, subscription_id: UUID) -> None: ...
    async def recover(self, operation_id: UUID, since: datetime) -> list[PlategaSubscription]: ...
    async def recover_payments(
        self, operation_id: UUID, since: datetime
    ) -> list[PlategaPayment]: ...


def description_for(operation_id: UUID) -> str:
    return "PrettyLisaVPN Premium / " + str(operation_id)


def subscription_url(subscription_id: UUID) -> str:
    return "https://pay.platega.io/subscription/" + str(subscription_id)


class PlategaAPI:
    def __init__(
        self,
        merchant_id: UUID,
        secret: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if merchant_id.int == 0 or len(secret.get_secret_value()) < 16:
            raise ValueError("Platega merchant credentials are not configured")
        self.merchant_id, self._secret, self._transport = merchant_id, secret, transport

    async def _call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        params: dict[str, str] | None = None,
        idempotency_key: UUID | None = None,
        accepted_statuses: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        try:
            # Fixed host, verified TLS, no redirects and no automatic retries, including POST.
            async with httpx.AsyncClient(
                transport=self._transport, timeout=8, follow_redirects=False
            ) as client:
                headers = {
                    "X-MerchantId": str(self.merchant_id),
                    "X-Secret": self._secret.get_secret_value(),
                }
                if idempotency_key is not None:
                    headers["Idempotency-Key"] = str(idempotency_key)
                async with client.stream(
                    method,
                    "https://app.platega.io" + path,
                    headers=headers,
                    json=body,
                    params=params,
                ) as response:
                    if response.status_code not in accepted_statuses:
                        raise PlategaUnavailable
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 512_000:
                            raise PlategaUnavailable
            value = json.loads(content, parse_float=Decimal)
            if path == "/transaction/export/json" and isinstance(value, list):
                return {"items": value}
            if not isinstance(value, dict):
                raise PlategaUnavailable
            return value
        except (httpx.HTTPError, ValueError, InvalidOperation):
            raise PlategaUnavailable from None

    async def create(
        self, operation_id: UUID, amount_minor: int, email: str
    ) -> CreatedSubscription:
        # The subscription schema specifies integer RUB. Never round the DB quote.
        if not 0 < amount_minor <= 10**12 or amount_minor % 100:
            raise ValueError("Platega subscription requires whole RUB")
        value = await self._call(
            "POST",
            "/transaction/process",
            body={
                "paymentMethod": 6,
                "paymentDetails": {
                    "amount": amount_minor // 100,
                    "currency": "RUB",
                    "interval": 3,
                    "intervalCount": 1,
                },
                "description": description_for(operation_id),
                "metadata": {"user_email": email},
            },
        )
        try:
            identity = UUID(value["transactionId"])
            if (
                UUID(value["merchantId"]) != self.merchant_id
                or value["paymentMethod"] != "Subscription"
                or str(value["status"]).upper() != "PENDING"
                or value["redirect"] != subscription_url(identity)
            ):
                raise ValueError
            return CreatedSubscription(id=identity, redirect=value["redirect"])
        except (ValueError, KeyError, TypeError):
            raise PlategaUnavailable from None

    @staticmethod
    def _subscription(value: dict[str, Any], identity: UUID) -> PlategaSubscription:
        try:
            if (
                UUID(value["id"]) != identity
                or value["intervalUnit"] != "Month"
                or value["intervalCount"] != 1
            ):
                raise ValueError
            return PlategaSubscription(
                id=identity,
                status=value["status"],
                amount_minor=minor_units(value["amount"]),
                currency=value["currencyCode"],
                next_charge_at=value.get("nextChargeAt"),
                last_charge_at=value.get("lastChargeAt"),
                description=value["description"],
                created_at=value["createdAt"],
                successful_charges=value["chargeMetrics"]["chargesSuccess"],
            )
        except (ValueError, KeyError, TypeError):
            raise PlategaUnavailable from None

    async def subscription(self, subscription_id: UUID) -> PlategaSubscription:
        return self._subscription(
            await self._call("GET", "/subscription/" + str(subscription_id)), subscription_id
        )

    async def payment(self, payment_id: UUID) -> PlategaPayment:
        value = await self._call("GET", "/transaction/" + str(payment_id))
        try:
            # The documented GET spells the merchant field `mechantId`.
            merchant = value.get("mechantId", value.get("merchantId"))
            if UUID(value["id"]) != payment_id or UUID(merchant) != self.merchant_id:
                raise ValueError
            if "merchantId" in value and UUID(value["merchantId"]) != self.merchant_id:
                raise ValueError
            details = value["paymentDetails"]
            return PlategaPayment(
                id=payment_id,
                status=value["status"],
                amount_minor=minor_units(details["amount"]),
                currency=details["currency"],
                description=value.get("description"),
            )
        except (ValueError, KeyError, TypeError):
            raise PlategaUnavailable from None

    async def cancel(self, subscription_id: UUID) -> None:
        value = await self._call("POST", "/subscription/" + str(subscription_id) + "/cancel")
        try:
            if UUID(value["subscriptionId"]) != subscription_id or value["status"] != "cancelled":
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise PlategaUnavailable from None

    async def recover(self, operation_id: UUID, since: datetime) -> list[PlategaSubscription]:
        matches: list[PlategaSubscription] = []
        # Recovery searches the provider ledger; it NEVER submits another create.
        for page in range(1, 101):
            value = await self._call(
                "GET",
                "/subscription",
                params={"from": since.isoformat(), "page": str(page), "size": "100"},
            )
            try:
                items, total = value["items"], value["total"]
                if (
                    not isinstance(items, list)
                    or not isinstance(total, int)
                    or total < 0
                    or value["page"] != page
                    or value["size"] != 100
                ):
                    raise ValueError
                for item in items:
                    if item.get("description") == description_for(operation_id):
                        matches.append(await self.subscription(UUID(item["id"])))
                if page * 100 >= total:
                    return matches
                if not items:
                    raise ValueError
            except (ValueError, KeyError, TypeError, AttributeError):
                raise PlategaUnavailable from None
        raise PlategaUnavailable

    @staticmethod
    def _payment_link(value: dict[str, Any], operation_id: UUID, amount_minor: int) -> PaymentLink:
        try:
            url = urlsplit(value["url"])
            amount = Decimal(amount_minor) / 100
            if (
                value["usageMode"] != 1
                or value["paymentMode"] != 0
                or value["currency"] != "RUB"
                or Decimal(value["minAmount"]) != amount
                or Decimal(value["maxAmount"]) != amount
                or value["orderId"] != str(operation_id)
                or value["payload"] != str(operation_id)
                or url.scheme != "https"
                or url.netloc != "pay.platega.io"
                or url.fragment
                or len(value["url"]) > 2048
                or type(value["active"]) is not bool
            ):
                raise ValueError
            return PaymentLink(
                id=value["id"],
                url=value["url"],
                operation_id=operation_id,
                amount_minor=amount_minor,
                active=value["active"],
            )
        except (ValueError, KeyError, TypeError, InvalidOperation):
            raise PlategaUnavailable from None

    async def create_payment_link(self, operation_id: UUID, amount_minor: int) -> PaymentLink:
        """Optional one-off API contract, NOT an SBP mandate/card-replacement operation.

        Merchant activation is required. This method is deliberately not exposed as
        recurring checkout: links do not document a reusable payment authority.
        """
        if type(amount_minor) is not int or not 0 < amount_minor <= 10**12:
            raise ValueError("Invalid payment amount")
        amount = format(Decimal(amount_minor) / 100, ".2f")
        value = await self._call(
            "POST",
            "/v2/payment-links",
            idempotency_key=operation_id,
            accepted_statuses=(200, 201),
            body={
                "usageMode": 1,
                "paymentMode": 0,
                "currency": "RUB",
                "minAmount": amount,
                "maxAmount": amount,
                "orderId": str(operation_id),
                "payload": str(operation_id),
                "name": "PrettyLisaVPN Premium",
                "description": description_for(operation_id),
                "return": "https://prettylisavpn.com/account/success/",
                "failedUrl": "https://prettylisavpn.com/account/failure/",
            },
        )
        return self._payment_link(value, operation_id, amount_minor)

    async def payment_link(
        self, link_id: UUID, operation_id: UUID, amount_minor: int
    ) -> PaymentLink:
        value = self._payment_link(
            await self._call("GET", "/v2/payment-links/" + str(link_id)), operation_id, amount_minor
        )
        if value.id != link_id:
            raise PlategaUnavailable
        return value

    async def payment_link_payments(self, link: PaymentLink) -> list[PlategaPayment]:
        value = await self._call(
            "GET",
            f"/v2/payment-links/{link.id}/transactions",
            params={"page": "1", "pageSize": "20"},
        )
        try:
            items = value["items"]
            # Only our single-use links are supported; never silently truncate a ledger.
            if not isinstance(items, list) or value["totalCount"] != len(items) or len(items) > 1:
                raise ValueError
            result = []
            for item in items:
                if (
                    UUID(item["paymentLinkId"]) != link.id
                    or minor_units(item["amount"]) != link.amount_minor
                    or item["currency"] != "RUB"
                ):
                    raise ValueError
                payment = await self.payment(UUID(item["id"]))
                if payment.amount_minor != link.amount_minor:
                    raise ValueError
                result.append(payment)
            return result
        except (ValueError, KeyError, TypeError):
            raise PlategaUnavailable from None

    async def recover_payments(self, operation_id: UUID, since: datetime) -> list[PlategaPayment]:
        """Recover missed callbacks only when two provider reads bind the opaque order ID.

        The documented export returns JSON rows. File URLs and absent/inconsistent
        descriptions are not evidence and are never followed with credentials.
        """
        value = await self._call(
            "POST",
            "/transaction/export/json",
            body={
                "from": since.isoformat(),
                "to": datetime.now(UTC).isoformat(),
                "timeZoneId": "UTC",
            },
        )
        try:
            items = value["items"]
            if not isinstance(items, list) or len(items) > 5000:
                raise ValueError
            result = []
            for item in items:
                if item.get("description") != description_for(operation_id):
                    continue
                receipt = await self.payment(UUID(item["recordId"]))
                if (
                    receipt.description != description_for(operation_id)
                    or receipt.amount_minor != minor_units(item["amount"])
                    or item["currencyCode"] != receipt.currency
                ):
                    raise ValueError
                result.append(receipt)
            return result
        except (ValueError, KeyError, TypeError, AttributeError):
            raise PlategaUnavailable from None
