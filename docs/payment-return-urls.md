# Public payment addresses — 1Plat

Backend 0.28.0 → 0.29.0 (new public HTTP endpoints); schema remains 0041.
Client versions, engines and dashboard are unchanged by this task. Source baseline:
develop `66c26f243d6890686beb1e0d94271b5d7b849764`.

| 1Plat setting | URL | Purpose |
| --- | --- | --- |
| Successful payment return | https://prettylisavpn.com/payment/success | Browser return; directs the customer to the subscription screen while server confirmation is pending. |
| Unsuccessful payment return | https://prettylisavpn.com/payment/failure | Browser return after cancellation/failure; directs the customer to check status before retrying. |
| API callback | https://prettylisavpn.com/api/payments/1plat/callback | Reserved POST notification endpoint. Currently fails closed with HTTP 503 / BILLING_NOT_CONFIGURED. |
| Support | https://prettylisavpn.com/support | Contact page; the button opens a message to help@prettylisavpn.com in the user's mail application. |

The independent public-support follow-up raises backend 0.29.0 → 0.30.0, without
schema/client changes. Both payment pages link to `/support`; `/support/` also works.
The owner selected a mailto button, not a web form. No email is sent automatically,
and this page does not invoke the authenticated in-app support API or store content.

The public pages and their CSS/logo ship inside the backend image. Caddy terminates
HTTPS on the main server and exposes only these paths on the apex domain. Other
paths on that host return 404; private monitoring remains on api.prettylisavpn.com.
DNS A for the apex must point to 95.140.152.42. No Codex/ChatGPT hosting or scheduler
is used. Payment return URLs contain no account credentials and their query string
is neither reflected into HTML nor logged by the public-host Caddy configuration.
Pages have CSP, no-referrer, no-store, noindex, and no external scripts/trackers.

## Current callback boundary

This task prepares merchant registration addresses, not a live payment adapter.
The callback intentionally does not acknowledge, store, or settle a payment until
1Plat is configured. Visiting a success URL, sending status=success, or repeating
a callback cannot grant a subscription. The existing provider remains disabled.
HTTP 503 is an explicit failure, not a claimed successful delivery. Do not send
real customer payments to this endpoint before the next integration is complete.

## Merchant domain verification

The owner-provided TXT file is served at `https://prettylisavpn.com/1plat.txt`.
Store its exact bytes in `merchant-verification/1plat.txt` beside the deployment
environment file (the live path is
`/opt/prettylisavpn/secrets/merchant-verification/1plat.txt`). `deploy.sh` exports
this directory as `MERCHANT_VERIFICATION_DIR`; Caddy mounts it read-only. Direct
Compose invocations must set that variable explicitly for non-default paths.
The CI deployment explicitly selects the persistent `secrets/merchant-verification`
directory because its input environment file is staged in a temporary incoming directory.
The file is not committed or included in application images. Only the exact
public path is served, without authentication or directory listing; unrelated
paths remain 404. Verify HTTP 200 and SHA-256/byte equality with the source file
before the owner presses "Проверить txt" in 1Plat. Payment processing stays disabled.

This is an infrastructure-only change: backend remains 0.29.0, schema 0041 and
client versions are unchanged. The existing backend image need not be rebuilt
or restarted for this Caddy-only rollout. Keep the previous deployment directory
for rollback; restoring its Caddy configuration removes this verification URL.

## Provider documentation

The owner supplied https://1plat.cash/doc/api. The HTML/browser initially exposed
only marketing text; its public application bundle and documentation chunk were
then retrieved successfully from the main server. The provider documents a
callback body with signature/signature_v2, payment/order identifiers, status and
amounts. HTTP 200/201 acknowledges the payment; the unconfigured route must not
return those statuses. Its HMAC example serializes payload with JavaScript
JSON.stringify, so a future Python adapter must test serialization compatibility
and authoritative status reconciliation, not assume arbitrary JSON encoding works.
Before activating payments, obtain merchant credentials through a private server
configuration; implement and test
signature/authentication, authoritative status reconciliation, amount/currency/
order matching, idempotency and the existing durable billing operation settlement.
Never put shop secrets in return URLs, client APK/EXE, Git, or logs.

## Validation and rollback

Tests cover public pages/assets, ignored forged query claims, fail-closed callbacks,
POST-only notification behavior, and the restricted public-host route. Browser QA
checks desktop and narrow-screen layout. Exact source/build/run/attempt, public
HTTPS responses and deployment evidence are recorded in the task PR.
Rollback to the previous immutable backend release also restores its Caddyfile;
the three payment URLs become unavailable. No database rollback is required.
