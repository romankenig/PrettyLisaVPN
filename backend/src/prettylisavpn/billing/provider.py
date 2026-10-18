"""Replaceable idempotent provider boundary. No live adapter or credential loader.

Adapters MUST durably deduplicate by operation_id, reconcile an uncertain create
using that same key, authenticate receipts, and return authoritative mandate state.
RENEW may retain the active mandate; CHANGE_METHOD must confirm a distinct new
mandate and revocation of the previous one. CANCEL confirms both recurring stop
and mandate revocation. Terminal failures mean no successful payment/mandate
mutation: a partial or uncertain external outcome must remain PENDING.
Only explicitly injected sandbox adapters are accepted in this release.
"""

from typing import Protocol

from prettylisavpn.billing.domain import PAYMENT_ROUTES, RouteCapability

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

    async def reconcile(self, request: ProviderRequest) -> ProviderResult: ...


def validate_provider(provider: BillingProvider | None) -> None:
    if provider is not None and (
        provider.sandbox is not True or not provider.name or len(provider.name) > 64
    ):
        raise ValueError("Only explicitly injected sandbox billing providers are supported")
    if provider is not None:
        ids = [cap.id for cap in provider.capabilities]
        if len(ids) != len(set(ids)) or not set(provider.routes) <= set(PAYMENT_ROUTES):
            raise ValueError("Invalid provider route capabilities")


def route_capabilities(
    provider: BillingProvider | None, action: Action, currency: Currency | None = None
) -> list[RouteCapability]:
    declared = {cap.id: cap for cap in provider.capabilities} if provider else {}
    result = []
    for route in PAYMENT_ROUTES:
        cap = declared.get(route, RouteCapability(id=route))
        currencies = tuple(
            code for code in cap.currencies
            if provider and route in provider.routes and provider.supports(action, route, code)
            and (currency is None or currency == code)
        )
        result.append(RouteCapability(
            id=route, currencies=currencies,
            recurring_currencies=tuple(code for code in cap.recurring_currencies if code in currencies),
        ))
    return result
