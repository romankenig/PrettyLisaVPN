# Website 0.3.0 — purchase path for Platega moderation

Owner request dated 2026-11-04, based on the Platega manager's screenshots,
[purchase-path guide](https://docs.google.com/document/d/1KZ7-iHcOHmHNZkscIdZbA0Wn-0Xgoc9PbHWubkjYrZ8/edit)
(resolved from https://clck.ru/3VRDWc) and [API documentation](https://docs.platega.io/).
The guide expressly requires a real tariff, concrete price and clickable purchase
button displaying temporary unavailability. It does not require a transaction or
merchant credentials for this stage. No payment API is called by this revision.

## Versions and compatibility

Public website **0.2.2 → 0.3.0**: new pricing and purchase interaction.
Backend **0.33.0**, managed engine **0.6.0**, Windows **0.25.2**, Android **0.21.2**,
iOS **0.1.0**, macOS **0.1.0** unchanged. No migration or server API change.
The separate Apple port PR #51 and its merge/deployment are not website validation.

## Implemented user flow

- Homepage → `#pricing`: Free (one account-wide hour/day UTC, no ads) and Premium
  (no daily time cap in the paid period, country selection, up to five devices).
- Premium, one calendar month: **499 RUB crossed out → 399 RUB**;
  **7 USD crossed out → 5 USD**. Values are minor-unit integers in `src/model.mjs`;
  cards, purchase buttons and the payment document use the same values.
- Each active Buy link opens a native HTML dialog with that currency's amount,
  the period and an explicit unavailable/no-charge/no-subscription message.
  Close and Escape restore focus. Without dialog support/JavaScript, the ordinary
  link reaches `/legal/payments/#payment-unavailable` with the same notice/prices.
- Four documents and the claims contact appear next to the pricing section.
  Existing seven platform pages, verified downloads and FAQ remain available.
- All six languages have complete pricing/dialog/document/contact copy.
- Owner supplied **feedback@prettylisavpn.com** for claims/payment enquiries.
  Technical support stays **help@prettylisavpn.com**. This task does not create a
  mailbox or verify delivery by sending mail. No postal street address was supplied.

The public site has five main sections after adding pricing. Routes and the Caddy
allowlist are unchanged. `POST /checkout[/]` continues to return 503 with
`WEB_CHECKOUT_DISABLED`; no browser secrets, payment forms or provider redirects.
No provider approval, successful payment, subscription or recurring debit is implied.

## Verification and deployment record

Local: Node syntax checks, all eight test groups, static build of 78 pages,
Prettier and diff checks. Browser review covers six locales at 320/390/1280 px,
both purchase amounts, Escape/close and links to the fallback document. Screenshots
are actual browser captures. Local Caddy tests cannot run because the Windows
Docker daemon is unavailable; the required isolated Caddy suite runs in CI.

The task PR records final source HEAD, actual build SHA/run/attempt, all workflow
events/jobs, artifact IDs, screenshots and actual public deployment results after
the last push. Only a verified matching website artifact may replace the current
static release. Keep the previous symlink target for rollback; no backend restart,
database mutation or payment activation is needed.

## Separate commercial activation

`SITE_RELEASE=1` remains blocked by existing commercial requirements. The site is
ready to demonstrate the requested moderation flow; only Platega/bank review can
decide acceptance. Provider approval, server integration, authenticated status/
callback processing, paid-access fulfillment, receipts and final legal/refund
approval remain separate. The supplied email is not substituted for the missing
postal address in the internal commercial-readiness checks.

Before real checkout, create matching account-visible backend offers through the
existing billing administration flow. This public display does not rewrite stored
offers, immutable quotes or subscription contracts. Manual renewal remains the
current exposed behavior; automatic recurring payments require their own approved
implementation and consent flow. No secret should be copied into frontend code.
