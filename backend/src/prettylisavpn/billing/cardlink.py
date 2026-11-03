"""Cardlink postback verification. No charge creation, mandates or checkout admission."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol
from urllib.parse import parse_qsl
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

MAX_CALLBACK_BYTES = 16 * 1024
BillStatus = Literal["NEW", "PROCESS", "UNDERPAID", "SUCCESS", "OVERPAID", "FAIL"]


class CardlinkError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code, self.status = code, status


def amount_minor(value: str) -> int:
    if not re.fullmatch(r"[0-9]{1,10}(?:\.[0-9]{1,2})?", value):
        raise ValueError("Invalid amount")
    amount = int(Decimal(value) * 100)
    if not 0 < amount <= 1_000_000_000_000:
        raise ValueError("Invalid amount")
    return amount


@dataclass(frozen=True)
class Notification:
    operation_id: UUID
    bill_id: str


def authenticate_notification(body: bytes, token: SecretStr) -> Notification:
    """Verify the original OutSum spelling; discard optional personal/card fields."""
    if len(body) > MAX_CALLBACK_BYTES:
        raise CardlinkError("CARDLINK_BODY_TOO_LARGE", 413)
    try:
        encoded = body.decode("ascii")
        if re.search(r"%(?![0-9a-fA-F]{2})", encoded):
            raise ValueError("Invalid encoding")
        pairs = parse_qsl(
            encoded, keep_blank_values=True, strict_parsing=True, errors="strict", max_num_fields=40
        )
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError("Duplicate field")
        inv_id, out_sum = data["InvId"], data["OutSum"]
        operation_id = UUID(inv_id)
        if str(operation_id) != inv_id:
            raise ValueError("Noncanonical order ID")
        amount_minor(out_sum)
        bill_id, signature = data["TrsId"], data["SignatureValue"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", bill_id):
            raise ValueError("Invalid bill ID")
        if not re.fullmatch(r"[a-fA-F0-9]{32}", signature):
            raise ValueError("Invalid signature shape")
    except (KeyError, ValueError, UnicodeError):
        raise CardlinkError("CARDLINK_INVALID_NOTIFICATION", 400) from None
    # MD5 is required by Cardlink's protocol. It does NOT sign status, currency or bill ID.
    expected = hashlib.md5(
        f"{out_sum}:{inv_id}:{token.get_secret_value()}".encode(), usedforsecurity=False
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise CardlinkError("CARDLINK_SIGNATURE_INVALID", 401)
    return Notification(operation_id, bill_id)


class VerifiedBill(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True, frozen=True)

    id: str
    order_id: str
    status: BillStatus
    type: Literal["NORMAL", "MULTI"]
    amount: Decimal
    currency_in: Literal["RUB", "USD", "EUR"]
    success: Literal[True]


class BillLookup(Protocol):
    async def lookup(self, bill_id: str) -> VerifiedBill: ...


class CardlinkAPI:
    def __init__(self, token: SecretStr, *, transport: httpx.AsyncBaseTransport | None = None):
        self.token, self.transport = token, transport

    async def lookup(self, bill_id: str) -> VerifiedBill:
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=5, follow_redirects=False
            ) as client:
                async with client.stream(
                    "GET",
                    "https://cardlink.link/api/v1/bill/status",
                    params={"id": bill_id},
                    headers={"Authorization": f"Bearer {self.token.get_secret_value()}"},
                ) as response:
                    if response.status_code != 200:
                        raise ValueError("Provider unavailable")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_CALLBACK_BYTES:
                            raise ValueError("Provider response too large")
            return VerifiedBill.model_validate(json.loads(body, parse_float=Decimal))
        except (httpx.HTTPError, ValueError, ValidationError):
            raise CardlinkError("CARDLINK_VERIFICATION_UNAVAILABLE", 503) from None


@dataclass(frozen=True)
class ExpectedBill:
    operation_id: UUID
    bill_id: str
    amount_minor: int
    currency: str


class ReceiptStore(Protocol):
    async def expected(self, notification: Notification) -> ExpectedBill: ...
    async def record(self, expected: ExpectedBill, status: BillStatus) -> None: ...


class CallbackHandler(Protocol):
    async def receive(self, body: bytes) -> None: ...


class CardlinkCallbacks:
    def __init__(self, token: SecretStr, api: BillLookup, store: ReceiptStore):
        self.token, self.api, self.store = token, api, store

    async def receive(self, body: bytes) -> None:
        notification = authenticate_notification(body, self.token)
        expected = await self.store.expected(notification)
        bill = await self.api.lookup(expected.bill_id)
        try:
            matched = (
                bill.id == expected.bill_id
                and bill.order_id == str(expected.operation_id)
                and bill.type == "NORMAL"
                and amount_minor(str(bill.amount)) == expected.amount_minor
                and bill.currency_in == expected.currency
            )
        except ValueError:
            matched = False
        if not matched:
            raise CardlinkError("CARDLINK_BILL_MISMATCH", 409)
        if bill.status in ("NEW", "PROCESS"):
            raise CardlinkError("CARDLINK_VERIFICATION_PENDING", 503)
        # Only API-authoritative facts enter the inbox; unsigned callback status is ignored.
        # OutSum may include a payer commission, so the immutable quote is checked against
        # the API bill amount, not against that signed gross payment amount.
        await self.store.record(expected, bill.status)
