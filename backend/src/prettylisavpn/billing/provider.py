"""Replaceable idempotent provider boundary. No live adapter or credential loader.

Adapters MUST durably deduplicate by operation_id, reconcile an uncertain create
using that same key, authenticate receipts, and return authoritative mandate state.
Only explicitly injected sandbox adapters are accepted in this release.
"""

from typing import Protocol

from prettylisavpn.billing.operations_domain import Action, Currency, PaymentRoute, ProviderRequest, ProviderResult


class BillingProvider(Protocol):
    name: str
    sandbox: bool
    routes: frozenset[PaymentRoute]
    redirect_hosts: frozenset[str]

    def supports(self, action: Action, route: PaymentRoute | None, currency: Currency) -> bool: ...

    async def reconcile(self, request: ProviderRequest) -> ProviderResult: ...


def validate_provider(provider: BillingProvider | None) -> None:
    if provider is not None and (not provider.sandbox or not provider.name or len(provider.name) > 64):
        raise ValueError("Only explicitly injected sandbox billing providers are supported")
