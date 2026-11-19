# Direct recurring checkout — 2026-11-19

## Scope and versions

Website **0.7.1 → 0.7.2**, backend **0.54.1 → 0.54.2** (PATCH fixes).
Native/browser client product sources and versions are unchanged. The Chrome
directory contains the existing website browser acceptance runner only. Schema
remains `0053_analytics_plans`; no endpoint or commercial price changes.

The owner requested immediate navigation after Pay and explicitly removed one-off
payments from scope. Only monthly recurring SBP in RUB is offered. The unused
Platega payment-link transport/probe is removed; no fallback to card, crypto or
one-off SBP is introduced. Other historical adapters remain disabled and are not
part of the website's live Platega checkout.

## Website flow

- Existing email OTP authentication still identifies the account. Price and
  monthly renewal consent are on the same offer, without a separate confirmation
  screen. Consent starts unchecked and is required before Pay.
- Pay persists its account-scoped request UUID before POST, then immediately
  navigates to the validated provider URL in the **same tab**. No intermediate
  bank-link page or popup is required.
- A pending operation is fetched immediately when entering the account. If its
  link arrives later, polling uses that same operation and opens it once.
- The journal records that a redirect happened. Returning with Back shows the
  existing operation and allows manual reopening; it does not create a redirect
  loop or another purchase. Unknown outcomes without a URL cannot invent one.
- Unsupported currency, provider mode or unavailable quote shows an inline
  notice and disables Pay. Legacy `/account/unavailable/` and preview-success
  links return to the localized account page; no promised notification email is
  presented. Real success still requires server-confirmed SUCCEEDED.
- POST timeout is 25 seconds to accommodate the backend's 20-second reconciliation
  deadline. Lost responses retain the request journal and recover the same operation.

## Explicit provider rejection

The transport distinguishes only a narrow, explicit creation rejection:
HTTP 400 with `Common:VAL_0001`, type 4001, nonempty field-validation data and no
resource ID/redirect. It applies only to POST `/transaction/process`. Generic
errors, contradictions, timeouts, failed cancellation and unknown outcomes remain
unresolved rather than authorizing another create.

`CreateRejected` is durably stored in the existing agreement state field before
the operation is projected as FAILED. A crash between those steps recovers the
failure without reposting. The same request UUID remains idempotent; a user may
start a new operation after a definite rejection. HTTP response bodies, emails,
secrets and payment URLs are not logged. Existing manual Platinum retains its
plan and accumulated access when a purchase is genuinely confirmed.

## Actual merchant findings

The website was already LIVE at backend source
`afcf94dd20f22a6027da55a89b491a56acd09620`, run `44513423200`, attempt `1`.
The owner-selected account's operation
`d1950cf6-0570-4b80-85f8-6a5384242962` received an explicit validation rejection
at `2026-11-19T11:41:45.537679Z` (trace
`642bc125-c30b-5a40-96b1-26be8bcca8e6`). One controlled diagnostic replay of that
known rejected request, with the same operation ID and immutable 399 RUB quote,
also returned HTTP 400. Its validation identifies `paymentMethod: Subscription`,
trace `c42292319af83caca085851f12dacab2`. No subscription ID or charge was returned.
The earlier unknown Gmail operation was not retried or reset.

The owner authenticated in `https://my.platega.io`; read-only inspection of
"Методы приема платежей" found exactly two active methods: SBP QR and crypto.
Recurring Subscription and cards were absent. The inspected merchant ID matches
the installed credentials (compared without exposing the secret). No merchant
method, fee split, credential, callback URL or financial setting was changed.
Do not claim that local UI changes enable a provider method missing from this list.

After deployment, the known rejected operation may be reconciled using its
specific HTTP evidence and retained fence. Do not infer the same rejection for
the older operation with a lost response. Actual bank agreement, charge, callback
and cancellation acceptance are still outstanding.

## Validation and rollout

Local website checks: 26 Node tests, syntax, 102-page build, rendered browser
acceptance and desktop/mobile screenshots across six languages. Acceptance checks
one-click same-tab navigation, unchecked inline consent, Back without loops, lost
POST recovery without reposting, unavailable/legacy paths, verified success,
cancellation, immutable prices, failure/retry and a pending operation without a URL.

Backend adds transport unit tests for exact versus ambiguous failures and DB
integration tests for rejection recovery, new admission after a definite rejection,
and manual Platinum preservation. Local Ruff/mypy and targeted tests run before
push; Linux CI supplies PostgreSQL/Valkey and isolated Docker checks.

Record final source HEAD, every Actions run/job, build SHA/run/attempt, artifact
and actual backend/static deployment in the task PR. This file is not deployment
or live-payment evidence. Merge and publication require the owner's authorization.
