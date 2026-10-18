"""Deterministic external sandbox ledger. Never imports an HTTP/payment SDK."""

import asyncio
from uuid import uuid4

from prettylisavpn.billing.operations_domain import ProviderMandate, ProviderResult


class TestBillingProvider:
    __test__ = False
    name = "test-ledger-v1"
    sandbox = True
    routes = frozenset({"MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO"})
    redirect_hosts = frozenset({"payments.example.test"})

    def __init__(self, ledger=None):
        self.ledger = ledger if ledger is not None else {}
        self.requests = {}
        self.calls = []
        self.outcome = "PENDING"
        self.fail_after_accept_once = False
        self.fail_before_accept_once = False
        self.started = asyncio.Event()
        self.gate = None
        self.invalid = None
        self.unsupported = set()

    def supports(self, action, route, currency):
        return (route,currency) not in self.unsupported

    async def reconcile(self, request):
        self.calls.append(request.operation_id)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_before_accept_once:
            self.fail_before_accept_once = False
            raise OSError("Never log this provider credential or URL")
        if request.operation_id not in self.ledger:
            self.requests[request.operation_id] = request
            self.ledger[request.operation_id] = self.result(request, self.outcome)
        if self.fail_after_accept_once:
            self.fail_after_accept_once = False
            raise TimeoutError("Provider accepted; response lost")
        return self.invalid or self.ledger[request.operation_id]

    def result(self, request, status):
        mandate = None
        if status == "SUCCEEDED" and request.action != "CANCEL" and request.payment_route not in ("CRYPTO", "ALIPAY_WECHAT"):
            mandate = ProviderMandate(reference="sandbox-" + str(uuid4()), label="Тестовый способ оплаты")
        return ProviderResult(operation_id=request.operation_id, status=status,
            amount_minor=request.amount_minor if status == "SUCCEEDED" else None,
            currency=request.currency if request.amount_minor is not None and status == "SUCCEEDED" else None,
            mandate=mandate, recurring_stopped=True, previous_mandate_revoked=True,
            redirect_url="https://payments.example.test/confirm" if status == "PENDING" else None)

    def complete(self, operation_id, status="SUCCEEDED"):
        self.ledger[operation_id] = self.result(self.requests[operation_id], status)
