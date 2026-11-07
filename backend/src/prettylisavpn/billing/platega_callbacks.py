"""Authenticated, bounded callback inbox; only the server API can confirm a payment."""

import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select

from prettylisavpn.billing.model import BillingOperationRecord
from prettylisavpn.billing.platega_api import minor_units
from prettylisavpn.billing.platega_model import PlategaAgreementRecord, PlategaChargeRecord
from prettylisavpn.connections import Postgres

PAYMENT_STATUSES = {"CONFIRMED", "CANCELED", "CHARGEBACKED", "PARTIALLY_REFUNDED", "DISPUTED"}
SUBSCRIPTION_STATUSES = {
    "SUBSCRIPTION_ACTIVATED",
    "SUBSCRIPTION_PAST_DUE",
    "SUBSCRIPTION_CANCELLED",
    "SUBSCRIPTION_FAILED",
}


class InvalidPlategaCallback(ValueError):
    pass


class PlategaCallbacks:
    def __init__(self, postgres: Postgres, merchant_id: UUID, secret: SecretStr) -> None:
        self.postgres, self._merchant, self._secret = postgres, str(merchant_id), secret

    def authenticated(self, merchant: str, secret: str) -> bool:
        # Both comparisons run; neither credential enters logs or exception details.
        return hmac.compare_digest(
            merchant.encode(), self._merchant.encode()
        ) & hmac.compare_digest(secret.encode(), self._secret.get_secret_value().encode())

    async def accept(self, body: bytes) -> None:
        try:
            value = json.loads(body, parse_float=Decimal)
            if not isinstance(value, dict):
                raise ValueError
            status = value["status"]
            if status not in PAYMENT_STATUSES | SUBSCRIPTION_STATUSES:
                raise ValueError
            identity, provider_id = UUID(value["id"]), UUID(value["subscriptionId"])
            amount = minor_units(value["amount"])
            if value["currency"] != "RUB" or (
                status in SUBSCRIPTION_STATUSES and identity != provider_id
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError):
            raise InvalidPlategaCallback from None
        async with self.postgres.session() as session, session.begin():
            agreement = await session.scalar(
                select(PlategaAgreementRecord)
                .where(PlategaAgreementRecord.provider_id == provider_id)
                .with_for_update()
            )
            if agreement is None:
                return  # This merchant can have unrelated products; never bind by client payload.
            operation = await session.get(BillingOperationRecord, agreement.operation_id)
            if operation is None or operation.quote["amount_minor"] != amount:
                raise InvalidPlategaCallback
            agreement.checked_at = None
            if status in SUBSCRIPTION_STATUSES:
                return  # Activation is a schedule notification, not proof of paid access.
            charge = await session.get(PlategaChargeRecord, identity, with_for_update=True)
            if charge is None:
                session.add(
                    PlategaChargeRecord(
                        id=identity,
                        agreement_id=agreement.operation_id,
                        amount_minor=amount,
                        currency="RUB",
                        status="PENDING",
                        received_at=datetime.now(UTC),
                    )
                )
            elif charge.agreement_id != agreement.operation_id or charge.amount_minor != amount:
                raise InvalidPlategaCallback
            else:
                charge.verified_at = None  # Reconcile even reordered/duplicate notifications.
