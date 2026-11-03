# Cardlink notification endpoint and domain verification

## Scope and versions

Backend 0.31.0 → 0.32.0: new public callback, additive migration 0042.
Public website 0.2.0 → 0.2.1: exact owner-supplied domain verification file.
Android/Windows unchanged. No new client navigation or payment availability.

Project registration addresses:

- Store: https://prettylisavpn.com/
- Success: https://prettylisavpn.com/payment/success
- Fail: https://prettylisavpn.com/payment/failure
- Result: https://prettylisavpn.com/api/payments/cardlink/callback
- Verification: https://prettylisavpn.com/shop-verification-xO2ZZeK02A.txt

The two return pages accept GET/HEAD/POST and ignore the provider form/query.
They never authenticate a payment, choose an account, redirect to a supplied URL,
or grant access. Refund and chargeback endpoints are not implemented.

## Notification contract and authenticity

Official reference, inspected 2026-11-03: https://cardlink.link/en/reference/api

Result GET/HEAD returns endpoint metadata (HTTP 200), not a paid receipt.
POST accepts bounded URL-encoded forms only. Missing token returns HTTP 503 /
`CARDLINK_NOT_CONFIGURED`, without writing a receipt or modifying subscriptions.
This permits project registration before Cardlink issues the API token; it does
not represent provider approval or a tested live payment.

Cardlink signs **only OutSum:InvId:apiToken** using uppercase MD5. Original decimal
spelling is preserved; comparison is constant-time. Duplicate fields, malformed
encoding, invalid IDs/amounts and oversized bodies are rejected. Optional payer,
phone, card and custom fields are discarded and never logged or stored.

Because Status, CurrencyIn and TrsId are unsigned, a valid signature is insufficient.
The service requires an existing `cardlink` SUBSCRIBE/RENEW operation and a
server-owned, pre-bound unique bill ID. It then queries the fixed HTTPS Cardlink
bill/status endpoint (no redirects), checks NORMAL bill type, both IDs, currency
and the immutable quoted amount. `OutSum` can include payer commission, so the
amount comparison uses the authoritative bill amount. NEW/PROCESS returns 503
for retry; terminal API observations enter a PostgreSQL inbox.

HTTP 200 / `received` means **committed delivery to the inbox only**. Concurrent
replays deduplicate by operation and API status. Append-only snapshots preserve
prior evidence, including success when a later contradictory status appears.
Timeout, unavailable database/API or incomplete verification never acknowledges
delivery. Signature, identity and quote mismatch never grant access.

## Deliberately disabled until the next integration stage

There is no production invoice creation or Cardlink settlement adapter yet.
The callback cannot create bill bindings or arbitrary orders. Existing sandbox
provider guards stay intact; adding a token alone does not enable selling.
No receipt consumer is enabled, so no real orders may be accepted until admission,
reconciliation/recovery and settlement are implemented together and tested.

The owner changed the desired renewal mode to **monthly automatic payment** on
2026-11-03. Do not relabel a repeat payment link as automatic renewal. Before
enabling it, obtain Cardlink's official recurring API/eligibility confirmation,
implement explicit versioned consent, mandates, scheduled idempotent charges,
recovery and cancellation, and test them. Current public terms must describe the
actually available behavior until that mechanism exists.

## Configuration, deployment and rollback

Save the API-integration token (not the cabinet password) in the owner's private
`cardlink.env`: `CARDLINK_API_TOKEN=<secret>`, mode 0600. Omit the file/key while
unconfigured; do not use a blank token. `CARDLINK_ENV_FILE` can select its path.
The deployment script defaults to the environment file's sibling `cardlink.env`.
Compose injects it into the API container only; the shared CI environment does
not overwrite this owner-managed credential. Never commit/upload it in artifacts.

Migration 0042 adds `billing_cardlink_bills` and `billing_cardlink_receipts`.
Existing payment/account records are unchanged. An application rollback retains
these tables; do not downgrade away financial evidence. Future admission must
persist the bill binding durably before redirecting a customer, and handle unknown
provider outcomes with the same operation UUID.

The public Caddy host exposes only the exact callback and verification paths.
The callback body is limited to 16 KiB; public access logging remains disabled.
Verification is an exact static file included in every website build, not a broad
filesystem or `/api/*` exposure.

## Verification and release evidence

Tests cover signature decimal spelling, unsigned-field tampering, malformed forms,
fixed-host provider requests, amount/currency/identity mismatch, retries, secret
redaction, POST return isolation, and real PostgreSQL concurrent inbox deduplication.
Website HTTP/container tests check the verification token, MIME type and exact
routing. Local Linux/container checks run in existing Linux CI when Docker/WSL is
unavailable on the Windows workstation; required checks stay enabled.

The task PR records the final product HEAD, all push/PR workflow runs and jobs,
temporary merge SHA, actual build SHA/run/attempt, deployment identity and live
HTTP evidence. A successful mocked callback is not proof of a Cardlink payment.
The website's own CI artifact identifies its exact source and version; the backend
image is built from the same checked commit, with its separate build identity.
