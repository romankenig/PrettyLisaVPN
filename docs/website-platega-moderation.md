# Website 0.3.1 — moderation feedback

## Historical record retained on 2026-11-07

This document records the original 0.3.x task, not the current payment behavior.
The current website is 0.5.0: later develop work already retained the moderation
marker, public document links, neutral copy, shared help address and account
screenshot, then added the real billing portal and DEMO information. The current
website source and navigation are preserved byte-for-byte when reconciling PR #52.
Only this missing historical handoff is added; **version unchanged** for all
components, with no application rebuild or deployment required for this record.
Current checkout, limits and provider status are defined by
[Platega billing](platega-billing.md) and [DEMO access](android-demo-access.md).
Statements below about disabled payments and prices describe their original date.
Final reconciliation HEAD, checks and merge are recorded in PR #52.

## Follow-up dated 2026-11-05

Website **0.3.0 → 0.3.1** (PATCH: public copy, document visibility and catalog
validation). Backend and all client versions remain unchanged. No migrations,
payment API calls, merchant credentials or new checkout endpoints.

- All 78 public pages in ru/en/de/fr/es/zh have four permanently available
  document buttons in the shared footer and a header link to that footer.
- Replace the "your rules" headline, transport-selection promotion and named
  service-routing examples with neutral encryption, account and connection
  descriptions. Replace the Android service picker with the unchanged native
  account/home capture from the same previously verified Android artifact.
  Remove the old PNG from the published bundle; source hash/provenance is updated.
- Remove personal seller name, tax ID and tax status from every locale and the
  site model. Public service/data/claims contact is help@prettylisavpn.com.
  This follows the owner's supplied moderation comments, not a claim of legal
  approval; final document/refund/receipt approval remains a launch prerequisite.
- Display the exact temporary marker `platega test` on every page. Remove it
  only after the owner confirms cash-register registration.
- RUB current/reference prices cannot exceed 1,000,000 kopeks (10,000 RUB):
  page generation fails for an excessive, fractional or invalid amount. The
  existing USD display remains capped at the owner-approved $7 reference price
  ($5 payable), not at an invented exchange-rate equivalent. There is no cart,
  quantity multiplier, balance top-up or arbitrary-amount form. Payments remain
  disabled. Before real provider integration, enforce the same 10,000 RUB limit
  server-side on the final settlement amount including any currency conversion;
  a display/build guard is not evidence of transaction enforcement.

Validation: ten Node test groups cover all routes, translated document buttons,
marker, removed claims/personal seller data, exact screenshot bytes, RUB boundary
10,000 / 10,000.01 and rejected unapproved USD changes. Browser review covers
six languages at 320/390/1280 px, documents, currency switching and disabled
checkout. Existing CI additionally tests actual Caddy routes in Docker.
The PR records the final product SHA, build SHA/run/attempt, artifact and actual
publication/rollback evidence. Only that verified artifact may be deployed.

Scope: public website HTML, metadata, documents and shipped screenshot assets.
No access to the Telegram bot/channel was available for a content audit; no
messages were sent and no posts were changed. Internal engineering documents
and application functionality are outside this website copy revision.

## Historical 0.3.0 implementation (superseded contact/visibility details below)

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
- A native RUB / USD radio switch shows one price and one Buy link at a time,
  including the matching currency on the Free zero price. Premium's card copy is
  shortened to unlimited time / per month; renewal details are in the payment document.
  CSS switches the price even without JavaScript; older browsers without `:has`
  retain both links instead of a non-working switch. Keyboard arrows select currency.
- The active Buy link opens a native HTML dialog with that currency's amount,
  the period and an explicit unavailable/no-charge/no-subscription message.
  Close and Escape restore focus. Without dialog support/JavaScript, the ordinary
  link reaches `/legal/payments/#payment-unavailable` with the same notice/prices.
- Four documents are available in the common footer; the owner removed their
  duplicate row and the email from the pricing block.
  The unavailable dialog and fallback notice use **help@prettylisavpn.com**.
  Existing seven platform pages, verified downloads and FAQ remain available.
- All six languages have complete pricing/dialog/document/contact copy.
- Owner supplied **feedback@prettylisavpn.com** for written claims; it remains in
  the legal documents/footer, outside the pricing block and payment placeholder.
  Technical support stays **help@prettylisavpn.com**. This task does not create a
  mailbox or verify delivery by sending mail. No postal street address was supplied.

The public site has five main sections after adding pricing. Routes and the Caddy
allowlist are unchanged. `POST /checkout[/]` continues to return 503 with
`WEB_CHECKOUT_DISABLED`; no browser secrets, payment forms or provider redirects.
No provider approval, successful payment, subscription or recurring debit is implied.

## Verification and deployment record

Local: Node syntax checks, all eight test groups, static build of 78 pages,
Prettier and diff checks. Browser review covers six locales at 320/390/1280 px,
currency switching, a single visible purchase amount, Escape/close and fallback links. Screenshots
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
