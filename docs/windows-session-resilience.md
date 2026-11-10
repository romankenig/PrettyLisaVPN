# Windows session recovery — 2026-11-09

Windows **0.27.0 → 0.27.1**, backend **0.40.0 → 0.40.1** (PATCH): fix unintended
sign-out after access-token expiry or a temporary network/API failure. Other client,
engine and website versions are unchanged. Additive migration **0048_refresh_retry**.

Home previously sent its saved access token directly and treated expiry as logout.
The VPN refresh path deleted the saved refresh token before the request and cleared
the active session on every error. These are separate confirmed failure paths;
the screenshot alone cannot identify which occurred on the user's device.

All authenticated Windows API transports now obtain a current bearer through the
shared single-flight session refresh. This includes idle Home/device reads, billing,
support and messages; VPN adapters share the same session. An explicit expired-access
response may retry once. Requests cannot acquire another account's token after an
account change. Network, server and secure-storage failures retain the signed-in
state; confirmed invalid/expired/revoked/blocked credentials still end it. VPN health
and lease limits continue to stop unusable tunnels; this does not invent connectivity.

Before refresh, Windows saves a random operation UUID beside the existing refresh
credential in Windows Credential Manager. A credential attribute preserves the
legacy token/expiry format. A successful response atomically replaces the token and
removes the operation attribute. Timeout, process restart or failed response saving
can resend the same credential and operation; there is no plaintext token file.

The optional `rotation_id` on POST /auth/refresh identifies that exact operation.
PostgreSQL stores only the prior token hash and operation UUID alongside the current
hash. A domain-separated HMAC derives the successor from the secret server key,
session, operation and presented token, avoiding stored plaintext/recoverable tokens.
Recovery returns the committed successor and expiry without rotating again or
extending expiry. It is limited to the latest operation while the session is active;
a later rotation, expiry, logout, blocked account or revoked device prevents recovery.
The prior token alone or a different operation UUID never permits recovery. Tokens
and operation identifiers are omitted from logs/error representations.

Legacy clients omit rotation_id and retain one-use refresh behavior. The recovery
pair is a credential and must remain confidential; compromise of the entire pair
has the same consequence as compromise of the pending refresh credential. This is
an application-specific idempotency mechanism, not a claim of OAuth certification.
The protection review considered [RFC 9700 §4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).

Deploy backend 0.40.1 and migration 0048 before the new client to enable lost-response
recovery. Existing clients remain compatible. An older backend can run with the
additive columns left in place, but cannot recover a lost rotation response; do not
downgrade the schema while new servers are running. No quota/payment data changes.

Validation covers token expiry, transient errors, concurrent refresh, retained
operation IDs, storage-write failure, late replies after logout/account change,
legacy replay rejection, real PostgreSQL concurrent retries and application restart,
revoked/blocked principals, and the native Windows Credential Manager round trip.
Native UI capture simulates an expired bearer plus refresh outage and verifies Home
remains signed in before and after recovery. Final SHA/run/attempt, complete CI audit,
screenshots and actual deployment/publication evidence belong in the task PR.
