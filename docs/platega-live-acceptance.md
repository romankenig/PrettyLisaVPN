# Platega website activation — 2026-11-19

## Scope and versions

The owner confirmed that recurring SBP (method 6) was enabled and requested
website-only payment setup. Native/browser clients, website source, schema and
commercial prices are unchanged. Backend source **0.54.0 → 0.54.1** (PATCH):
correct the reconciliation deadline and retain safe failure diagnostics. Website
remains **0.7.1**. Source changes are not proof of deployment; the actual live
runtime below remains 0.54.0 until a separately authorized merge/deploy.

The existing website owns checkout and the consent flow; see
[client checkout ownership](client-purchase-website.md) and
[Platega integration](platega-billing.md). One-off payments were explicitly
declined. The owner selected a separate FREE account for acceptance after a
read-only check found that the initially proposed account had manual Platinum.
Neither account's entitlement was changed.

## Verified configuration and runtime

- Merchant credentials were read from the owner-provided ignored local file and
  transferred through SSH stdin, without printing them or putting them in command
  arguments, Git, artifacts or browser code.
- `/etc/prettylisavpn/platega.env` is installed with mode `0600`. Compose resolves
  the expected credentials into the backend only. Its **current** provider setting
  is `BILLING_PROVIDER=disabled`; do not mistake credential installation for launch.
- The owner confirmed the merchant callback URL:
  `https://prettylisavpn.com/api/payments/platega/callback`.
  Delivery by Platega is **not yet verified**. Merchant UI inspection was blocked
  by the Windows browser-control tool's capture/URL-detection failure.
- Authenticated `GET /subscription` and the documented JSON transaction export
  returned HTTP 200. The provider ledger contained zero subscriptions, including
  separate reads for every documented numeric subscription status (0–4).
- The database is at `0053_analytics_plans`; the required billing migrations are
  already applied. The live account quote is **39900 RUB minor units per month**,
  read from PostgreSQL rather than the public display fallback.
- The backend image was unchanged during configuration-only restarts:
  source `d6e4c1d537ae6bdcee7c5ccc6f8829cd2dffd5c6`,
  run `44347588791`, attempt `1`, runtime
  `0.54.0-dev.44347588791+gd6e4c1d537ae6bdcee7c5ccc6f8829cd2dffd5c6`,
  image ID `sha256:882a46d4a69b719d813c322392b9f8f89eda24ed2fa173e6e1be75b8ecca95f6`.
- The public website reported version `0.7.1`, source
  `2ac1e72b31ef66e8caba10cc4391bd759e11fe5c`, run `44277188302`, attempt `1`.
  No new website artifact was published. Its embedded `deployment: not-published`
  is build metadata, not evidence that the fetched live artifact is unpublished.

The first readiness checks after backend recreation returned proxy HTTP 503
before Caddy's next 30-second upstream health check. Increasing the operational
wait allowed activation to complete; image identity and public readiness then
matched. No proxy security or health check was disabled.

## Acceptance stopped before payment

Exactly one application operation was admitted through the existing billing
service for the owner-selected FREE account:

- Operation: `3ac21966-8eb7-429e-9419-450ad3dbf39d`.
- Created: `2026-11-19T10:47:11.052787Z` (13:47:11 Europe/Moscow).
- Durable creation fence: `2026-11-19T10:47:11.080993Z`.
- Request: method `6`, `399 RUB`, interval `3`, interval count `1`.
- Description: `PrettyLisaVPN Premium / 3ac21966-8eb7-429e-9419-450ad3dbf39d`.
- Observed state: `PENDING`, no bound provider subscription ID, no checkout URL,
  no payment receipts, account still FREE.

This was server-side operation preparation, **not** a verified browser OTP,
consent, bank binding, charge, callback or cancellation flow. No bank agreement
or payment was confirmed by this task. The initial provider HTTP result was not
retained by the existing adapter, so neither explicit rejection nor successful
acceptance may be claimed. Empty subsequent lists do not authorize another POST.

After this result, new purchases were disabled again and only the backend was
recreated from the same image. Final public `/ready` was HTTP 200 with PostgreSQL
and Valkey ready; `/version` matched the runtime above. An unauthenticated empty
callback probe returned HTTP 503 / `PAYMENT_PROVIDER_DISABLED`, as expected.
The pending operation and creation fence were preserved. No second creation
request, fresh operation key, forced failure, record deletion or manual paid
access was used to bypass recovery.

## Remaining work

1. Ask Platega to locate the original request by merchant, UTC timestamp and
   description. Obtain its subscription ID, or an explicit rejection/no-creation
   result and reason. Do not resend while the outcome is unknown.
2. Deploy the verified deadline/diagnostics patch before a controlled retry. The
   live 0.54.0 worker has a 5-second reconciliation deadline while individual HTTP
   calls allow 8 seconds; this is a potential timing issue, **not** a proven cause
   of this attempt. The patch does not release or resend the original operation.
3. Recover the original operation when provider evidence permits. Repeat only
   according to a reviewed, evidence-backed recovery plan; no new charge key on
   timeout or an empty ledger.
4. Verify website authentication and consent, bank confirmation by the owner,
   actual callback receipt, independent API confirmation, exactly-once Premium
   access and provider schedule. Then verify cancellation and retention of paid
   access. Configuration success alone is not payment acceptance.
5. Keep manual Platinum unchanged. The existing initial purchase projection
   assigns Premium even to Platinum; the owner chose another FREE account rather
   than changing that business behavior in this task.

Before live activation, use the existing merchant/receipt/refund operational
requirements in [Platega integration](platega-billing.md). This handoff neither
asserts legal approval nor introduces a new policy or approval gate.

## Validation and provenance

Source 0.54.1 allows 20 seconds for reconciliation, allowing time for create plus
an authoritative read while remaining below the unchanged 30-second worker lease.
Transport HTTP timeouts remain 8 seconds. A real outer timeout still preserves
PENDING and the creation fence, and records `PROVIDER_TIMEOUT` with the operation
UUID. HTTP failure diagnostics contain only status, a bounded machine error code
and a validated trace UUID. Provider messages, data, headers and URLs are never
logged; malformed diagnostic identifiers become `unknown`.

The patch changes no HTTP schema, payment amount, recurring consent, provider
switch, mandate, or entitlement rule. Integration regressions exercise a create
response taking more than five seconds and an actual outer cancellation, including
single-create recovery and unchanged FREE access. Transport tests cover redaction
and malformed provider diagnostics. Local formatting, linting, strict type checks
and 114 targeted billing tests passed. The full local unit run passed 954 tests
and 27 subtests, with nine skips; four deployment-script tests failed because
Windows selected WSL Bash without an installed Linux `/bin/bash`. Full Linux
unit/integration/image checks and the exact source/build SHA/run/attempt must be
recorded in the task PR; the local failures are not counted as passes.

Earlier checks in this chat passed on the unchanged website source tree: 26 website
tests, syntax checks and the 102-page build; 105 targeted billing/API tests; and
the rendered browser fixture flow covering OTP, consent, lost responses, success,
cancellation, fixed price and failure/retry. These are simulated-provider checks,
not evidence of a real charge. Local Docker integration tests were unavailable.

Verify the changed Markdown targets and `git diff --check`; record the final
source HEAD, PR and all actual Actions runs after the last push in the PR
description. PR merge builds, branch-head builds and the live runtime are separate.

Provider references: [authorization](https://docs.platega.io/),
[subscription creation](https://docs.platega.io/создать-подписку-40029698e0),
[subscription listing](https://docs.platega.io/список-подписок-40029720e0),
[callbacks](https://docs.platega.io/колбэки-общая-информация-2499110m0).
