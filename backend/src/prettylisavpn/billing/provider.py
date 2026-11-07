"""Replaceable idempotent provider boundary. Explicitly configured, server-only adapters.

Adapters MUST durably deduplicate by operation_id, reconcile an uncertain create
using that same key, authenticate receipts, and return authoritative mandate state.
RENEW may retain the active mandate; CHANGE_METHOD must confirm a distinct new
mandate and revocation of the previous one. CANCEL confirms both recurring stop
and mandate revocation. Terminal failures mean no successful payment/mandate
mutation: a partial or uncertain external outcome must remain PENDING.
Sandbox and the monthly Platega SBP adapter are supported.
"""

from typing import Protocol

from prettylisavpn.billing.domain import ALL_PAYMENT_ROUTES, PAYMENT_ROUTES, RouteCapability
from prettylisavpn.billing.operations_domain import (
    Action,
    Currency,
    PaymentRoute,
    ProviderRequest,
    ProviderResult,
)


class BillingProvider(Protocol):
    name: str
    sandbox: bool
    routes: frozenset[PaymentRoute]
    capabilities: tuple[RouteCapability, ...]
    redirect_hosts: frozenset[str]

    def supports(self, action: Action, route: PaymentRoute | None, currency: Currency) -> bool: ...

    def supports_amount(
        self, route: PaymentRoute, currency: Currency, amount_minor: int
    ) -> bool: ...

    async def reconcile(self, request: ProviderRequest) -> ProviderResult: ...


def validate_provider(provider: BillingProvider | None) -> None:
    if provider is not None and (
        (provider.sandbox is not True and provider.name != "platega")
        or not provider.name
        or len(provider.name) > 64
    ):
        raise ValueError("Unsupported billing provider")
    if provider is not None:
        ids = [cap.id for cap in provider.capabilities]
        if len(ids) != len(set(ids)) or not set(provider.routes) <= set(ALL_PAYMENT_ROUTES):
            raise ValueError("Invalid provider route capabilities")


def route_capabilities(
    provider: BillingProvider | None, action: Action, currency: Currency | None = None
) -> list[RouteCapability]:
    declared = {cap.id: cap for cap in provider.capabilities} if provider else {}
    result = []
    for route in (*PAYMENT_ROUTES, *(("SBP",) if "SBP" in declared else ())):
        cap = declared.get(route, RouteCapability(id=route))
        currencies = tuple(
            code
            for code in cap.currencies
            if provider
            and route in provider.routes
            and provider.supports(action, route, code)
            and (currency is None or currency == code)
        )
        result.append(
            RouteCapability(
                id=route,
                currencies=currencies,
                recurring_currencies=tuple(
                    code for code in cap.recurring_currencies if code in currencies
                ),
            )
        )
    return result
