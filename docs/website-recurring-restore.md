# Restore recurring website payments — 2026-11-20

## Scope and versions

**Тестовый контур**. Owner-approved website **0.7.1 → 0.7.3** and backend
**0.54.4 → 0.54.5**, PATCH restoration/fixes after the test rollback.
Base: `5e2fad3f0d11fe2a522bcaddd14122e44355bba3` (PR #123).
Integrate current `develop` `9a27aa0b71d4a03cfb0ade971d084117aa39d3bb` (parallel
PR #125) without changing its client sources/versions; retain both changelog entries.
Preserve the restricted real-fleet backend, current client sources/versions,
database schema `0053_analytics_plans`, commercial prices and immutable contracts.
No client application changes or production publication are included.

The owner clarified that **unsuccessful payments show failure**. A confirmed
successful payment must never be deliberately shown as failed.

## Checkout and returns

- Only monthly recurring SBP in RUB: Platega method `6`, interval `3`, count `1`.
  No one-off payment, card or crypto fallback is added.
- Monthly consent is initially unchecked on the offer. Pay creates/reuses the
  account-scoped operation and navigates straight to the validated `pay.platega.io`
  form in the same tab. Unavailable checkout stays inline with Pay disabled.
- Restore durable browser request journaling, delayed-link polling and Back
  recovery without automatic redirect loops or duplicate creation after timeout.
- Hosted-form `return` and `failedUrl` use the configured website origin and an
  opaque operation UUID. It is a lookup identifier, never authentication or proof
  of payment. Authenticated account ownership remains enforced by the existing API.
- Success/failure pages recover the operation even without local storage, after
  refresh or after an expired login. Server `SUCCEEDED` displays success;
  `FAILED`/`CANCELED` displays failure. `PENDING` keeps checking, including on a
  failure return. Forging either URL cannot change payment status or access.
- Localized terminal routes retain their locale. Retry returns to the offer and
  requires explicit consent/Pay; it does not submit another charge by itself.
- Failed/cancelled subscription evidence cannot release a fresh purchase while
  a received payment is unverified or still PENDING. Late confirmation can settle
  the original operation after authoritative subscription/payment verification.

Callback remains **https://prettylisavpn.com/api/payments/platega/callback**.
The merchant callback setting is unchanged. Browser return URLs are separate from
this server callback. Existing unknown operations and creation fences are preserved.

## Validation and deployment evidence

Website unit tests, syntax/build and a rendered browser suite exercise six locales,
mobile/desktop layout, direct navigation, Back, lost responses, all four statuses,
contradictory return paths, refresh, login recovery and absence of payment reposts.
Mock HTTP tests verify exact provider payloads and allowed return origins in both
environments. PostgreSQL integration tests cover terminal failure/cancellation and
late/pending receipts. Ruff, mypy, migration and Docker checks remain required.

Shared CI rule (both environments, version unchanged): the rendered website suite
runs in the website workflow and gates its deploy. It reuses the existing locked
Playwright tooling without modifying clients. Website edits no longer trigger
Chrome packaging; CI-only Chrome workflow edits do not publish a new installer
without Chrome or publisher source changes.

Final source SHA, all Actions run/job results, build SHA/run/attempt, artifact IDs
and actual test deployment evidence are recorded in the task PR after completion.
This document alone is not deployment or real-charge acceptance evidence.

Test configuration retains `BILLING_PROVIDER=disabled` and no live merchant keys.
No production secrets are copied and no real bank charge is made in testing.
Production publication and a bank/callback acceptance run remain separate work.
The previous merchant-method finding is historical, not a fresh availability check;
see [previous direct checkout](website-direct-checkout.md).

Provider contract: [merchant instruction](https://docs.google.com/document/d/1zME5hfnSUlIpzpcyqOroX1HrwCfOceDMbP6NZFW9koI/edit)
and [Platega API](https://docs.platega.io/).
