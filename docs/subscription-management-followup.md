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

The originally investigated provider was abandoned by the owner on 2026-11-03.
Its callback, merchant verification and configuration have been removed; see
[removal handoff](payment-provider-removal.md). No charge, invoice, card binding or
subscription mutation was performed. Payment capabilities remain disabled.
Recurring billing is postponed; monthly invoices are not automatic debits. Crypto
remains a [separate provider-independent plan](crypto-payment-plan.md).

## Verification and rollback

Windows/Android tests cover first-use, legacy and cleared preferences plus paid
deadline boundaries. UI tests check FAQ answers and subscription/support navigation.
Native Windows review and Android instrumentation capture the FAQ answer states.
The task PR records final source HEAD, actual build SHA/run/attempt, every workflow
and job, screenshots and artifacts. No new live VPN acceptance is claimed or needed.
Rollback to Windows 0.24.1 / Android 0.20.1 preserves selections; old clients ignore
the optional initialization marker. No database migration or backend deploy.
