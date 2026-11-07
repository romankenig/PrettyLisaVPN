# Price display and monitoring follow-up

## Scope and component versions

Owner-authorized reference prices: **499 → 399 RUB / 7 → 5 USD per calendar month**.
PostgreSQL remains the source of offers and accepted contract prices. Owner also
requested a Buy label, independent retry observers, median speed and disk cleanup.

| Component | Before → after | Reason |
| --- | --- | --- |
| Website | 0.4.0 → 0.4.1 | Buy CTA, resilient public/account price display |
| Windows | 0.26.0 → 0.26.1 | Read-only reference prices on billing load failure |
| Android | 0.22.0/code 42 → 0.22.1/code 43 | Same shared account UI |
| iOS / macOS | 0.2.0 → 0.2.1 | Shared SwiftUI reference price card |
| Chrome | 0.2.0 → 0.2.1 | Browser-only subscription reference price card |
| Backend | 0.35.0 → 0.35.1 | Independent retry observers and unknown-history gaps |
| Dashboard | 0.6.2 → 0.6.3 | Median aggregate speed |

All are compatible PATCH changes. Database schema remains 0045. Linux has no
separate shipped subscription UI in this repository; its website/account entry
uses the same resilient web portal. No protocol or payment API changes.

## Price source and safety

The static homepage contains approved reference amounts, so API timeout, failed
JSON, blocked storage and disabled JavaScript do not erase prices. After a valid
public catalog response, cache only currency amounts/reference amounts and a
timestamp for seven days. No account ID, token, offer ID, revision, actions or
contract data is cached. Reject corrupt, future, expired and invalid cache data;
storage failure is harmless. Fresh database prices take priority. Refresh without
a discount hides any old struck-through value. Cache misses use approved values.
All reference/cached displays say terms must be confirmed before payment.

Native clients show the same clearly labeled new-subscription reference prices
when no overview is available. Existing loaded data on Android/Apple remains
visible on failed refresh; authoritative payment guards remain unchanged. Unknown
legacy current-contract prices are not backfilled. A normal valid empty offer
list remains authoritative and does not become a purchasable fallback offer.

Web overview failure replaces stale checkout controls with reference prices and
retry. Authentication errors still return to login. Operation polling preserves
pending idempotency recovery; a provider return URL still cannot settle a payment.
The public cache is display-only even if a user edits browser storage. Actual
checkout always requires authenticated server quotes and explicit consent.
Platega remains disabled until merchant credentials and separate activation.

## Completed operations before this source change

PR #62 merged to develop as bb0e08af3c7e5826fca056938a39e8a6da743bc1.
Dashboard 0.6.2 published from successful run 42288991958/attempt 1; authenticated
HTTP file hashes and real desktop/mobile UI were verified. This proves 0.6.2,
not the new median in 0.6.3.

The default catalog was published through the existing operator service with
expected revision, not direct contract updates. New revision:
8f0f0f03-24d6-4995-be65-60b1f32a3a98; offer:
f94762b9-d5cb-4244-acae-5d1ff009b8e8; UTC start:
2026-11-06T20:40:18.866971+00:00. Old offer interval closed at that instant;
history and immutable contracts retained. Public API returns approved values.
Remote audit: `/opt/prettylisavpn/operations/pricing-f94762b9/publication.json`.

Backend disk cleanup reclaimed 3,650,007,040 bytes (3.65 GB): reproducible old
validation virtualenv/test/type caches, client upload staging older than 48 hours,
and apt cache. Resolved paths, symlinks, mount and process references were checked.
Database, volumes, secrets, published downloads and rollback releases were retained.
Container IDs and API health were unchanged. Audit:
`/opt/prettylisavpn/operations/cleanup-20261106T204226Z`.

## Validation and publication handoff

Public cache unit tests cover expiry, corrupt/blocked storage and data minimization.
Browser acceptance covers fresh values, cached outage, cold outage, currency
switching, six locales/mobile widths, account outage with no payment action and
recovery; existing contract-price and idempotent checkout tests stay in place.
Windows and Android tests cover reference UI without a payment command; installed
Chrome UI covers a failed billing request. Apple resources reuse Android locales.
Fleet tests use real PostgreSQL for observer rotation, restart, locks and idempotency.
Dashboard tests cover odd/even medians, outliers, missing samples and coverage.

Exact verified product SHA, build SHA/run/attempt, all Actions/jobs/checks and
native/browser artifacts belong in the task PR after the final push. Current source
changes are not yet deployed. New client downloads require successful approved
merge/develop publication; retain stable URLs and honest unsigned Apple labels.
