# Subscription management follow-up — 2026-11-02

Windows 0.24.1 → 0.25.0; Android 0.20.1/code38 → 0.21.0/code39.
MINOR: interactive FAQ and initial split selections. Backend remains 0.30.0;
engines, dashboard, database schema and payment contracts are unchanged.

## Client behavior

- About has a question dropdown, one short answer and real internal Home,
  Subscription or Support links, in six languages. No external payment launch.
- New device preferences start in full-tunnel mode. A valid server catalog seeds
  include with YouTube + Telegram and exclude with Gosuslugi + MAX. Masks/networks
  come from the existing authenticated catalog, never hardcoded client copies.
  Persisted selections, including empty lists, are preserved. Missing/incomplete
  catalogs leave initialization pending; explicit editing/saving stops it.
- Defaults cannot change a running split tunnel. Dialog changes retain confirmed
  disconnect-before-save behavior. Both lists remain independent across restarts.
- Subscription shows remaining paid days (partial days rounded up) with exact
  expiry, current contract price and payment method. Android formats dates in the
  device locale/time zone and hides internal status/provider-mode codes. The server
  still owns entitlement; a display counter cannot extend access.
- Bind/change/cancel remain capability gated. Cancellation explains payment-method
  revocation and preservation of the paid period until its exclusive deadline.

## Payment work not activated

The owner verified the 1Plat merchant domain and supplied a private API credential.
A read-only authenticated methods request from the management server was rejected
by Cloudflare HTTP 403 / Error 1010 before merchant authentication. No charge,
invoice, card binding or subscription mutation was performed. No provider-block
bypass was attempted. Credentials remain outside Git, clients and artifacts.

The public [1Plat documentation](https://1plat.cash/doc/api), including its API-page
bundle, describes orders/status/callback signatures but did not establish recurring
charges or tokenized methods. The owner postponed recurring-capability investigation
on 2026-11-02. Monthly invoices must not be described as automatic recurring debits.

Follow-up: allow server API access, verify shop capabilities, currency units and
idempotency, implement the replaceable live adapter, authoritative reconciliation,
authenticated durable callback deduplication and contract settlement. Only then
enable LIVE capabilities and run an owner-approved real payment test. Callback
remains 503 BILLING_NOT_CONFIGURED; browser returns never grant access. Crypto is
a [separate plan](crypto-payment-plan.md), not an enabled method.

## Verification and rollback

Windows/Android tests cover first-use, legacy and cleared preferences plus paid
deadline boundaries. UI tests check FAQ answers and subscription/support navigation.
Native Windows review and Android instrumentation capture the FAQ answer states.
The task PR records final source HEAD, actual build SHA/run/attempt, every workflow
and job, screenshots and artifacts. No new live VPN acceptance is claimed or needed.
Rollback to Windows 0.24.1 / Android 0.20.1 preserves selections; old clients ignore
the optional initialization marker. No database migration or backend deploy.
