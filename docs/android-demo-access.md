# Android guest DEMO and public documents

## Versions and scope

Android 0.24.0 → **0.25.0**, versionCode 46 → 47; backend 0.35.1 → **0.36.0**;
public website 0.4.1 → **0.5.0**. New capabilities require MINOR increments.
Windows, Chrome, Apple and dashboard versions are unchanged. Work starts on
`ffcbb0ec010c891ab17c7549d60d38a0a4febcca` (PR #64, still independently reviewed).
This is Android guest access, not a new account plan UI on the other clients.

## Implemented behavior

- Authentication offers a small “try without registration” button. About has four
  document rows; authentication has smaller links below its primary controls.
  Fixed HTTPS URLs open localized terms, privacy, refunds and payments on
  prettylisavpn.com. No token, email, device identifier or redirect is appended.
- DEMO 🌱 gets 900 seconds per device per UTC day, AUTO selection among free nodes
  and full traffic protection. FREE 🆓 retains 3600 account-wide seconds/day;
  Premium ⭐ and manually assigned Platinum 💎 retain their existing capabilities.
- The official Android adapters force AUTO/all regardless of previously saved
  country, split selection or manually enabled method subset. Preferences are
  retained for a later registered session. Locked country, split, device and
  manual-method controls remain visible with muted labels and readable registration
  actions. Exhausted DEMO cannot reconnect by exploring other protocols.
- Registration closes the guest tunnel and remotely signs out before showing OTP.
  A registered user is a separate principal. DEMO usage never deducts from FREE;
  signing into an existing FREE account does not reset that account's usage.
- Website priorities are Premium, Free, then a quieter DEMO strip linking to the
  Android download. Prices and immutable existing subscription contracts are unchanged.

## Backend and privacy boundary

`POST /auth/demo` accepts a bounded 64-character app-scoped device hash, returns
the existing refresh/access contract, and never sends email. An independent stable
HMAC key maps it to a PostgreSQL `demo_devices` principal, stable installation UUID
and one device. A reserved synthetic email is internal only; OTP/web login for its
domain is denied and guest `/me.email` is null. Registered users retain their email.

Concurrent admissions serialize by the keyed identity. A new admission revokes
previous auth sessions and marks outstanding leases for durable cleanup; time is
not refunded until removal is confirmed. Existing short lease reservations and
node expiry enforce the 900-second budget and UTC midnight. FREE admin resets
cannot enlarge a DEMO budget. Redis only limits admission (30/IP/hour and
10/device/hour, hashed keys); quota and identity survive Redis loss. Unavailable
Redis or PostgreSQL fails closed with stable public error codes.

Guest billing, device management, traffic catalog, support submission and account
messages require registration. Country metadata remains readable for locked UI
previews; connect rejects explicit country, split mode and browser proxy before
granting access. Guests are excluded from registered-account analytics. No raw
ANDROID_ID, IMEI, advertising ID, browsing history, destinations or packets are
stored by this feature. Existing OTP and registered authentication stay unchanged.

Android 8+ ANDROID_ID is scoped to signing key, OS user and device. The client
hashes it before transmission; the backend HMACs it again. Ordinary uninstall and
reinstall with the same signer/profile keeps the identity. Factory reset, a new OS
profile or signing-key change can change it. A modified client can invent a new
hash: this is **not hardware attestation** or an absolute anti-abuse guarantee.
IP admission limits bound this abuse but do not prove device ownership. Stronger
resistance needs a separately reviewed attestation/device-recall provider, including
distribution outside Google Play. Backend cannot prove routing of traffic a modified
client never sends into the tunnel; official client routing and declared API mode
are enforced here. See [Android's documented identity scope](https://developer.android.com/about/versions/oreo/android-8.0-changes).

The single ANDROID_ID getter has a documented `HardwareIds` lint exception: a
random installation ID would violate the requested reinstall-resistant daily
budget. This exception is scoped to that function, with minSdk 26, no advertising
use, no email-account linkage, and client hashing/server HMAC. The full lint task
remains required; there is no project-wide suppression or baseline. Android's
[identifier guidance](https://developer.android.com/identity/user-data-ids) explains
the persistence/privacy tradeoff; hardware attestation is still not provided.

## Rollout and rollback

Migration **0046_demo_devices** adds DEMO to the PostgreSQL enum and a durable
identity table. **BREAKING rollback constraint:** after admitting guests, binaries
before 0.36.0 cannot safely read the new enum rows. Roll back via a compatible
forward fix, retaining guest identity and usage. Migration downgrade refuses a
populated guest table/subscription; an empty pre-activation downgrade removes only
the new table/constraint, retaining the enum member like the earlier PLATINUM migration.

Admission defaults **off**. After approved deployment/migration, install the
backend-only overlay `/etc/prettylisavpn/demo.env` (0600), based on
[`infra/deployment/demo.env.example`](../infra/deployment/demo.env.example), with
`DEMO_ENABLED=true` and a dedicated cryptographically random secret of at least
32 characters. Keep and back up this secret across builds; never derive it from
OTP/payment keys or rotate it routinely, because rotation would remap quotas.
The existing Compose deployment preserves this separate file. Disabling admission
stops new guest logins; already issued leases remain subject to their existing
quota/deadlines. Explicit revocation is required to terminate them immediately.

Deploy compatible backend before publishing the Android APK and website. Existing
registered clients never receive a DEMO token through their email flow; additive
`split_tunneling_allowed` and `traffic_mode` (default all) remain compatible.
Public references must not claim activation until an actual guest API/tunnel smoke
has passed after deployment. Merchant/payment activation is unrelated and unchanged.

## Validation and handoff

New unit tests cover entitlements, UTC limits, private hashing, fail-closed admission,
reserved email, stable errors, guest session restoration, full routing and terminal
quota handling. PostgreSQL integration covers concurrent logins, reinstall identity,
token invalidation, actual quota/cleanup, FREE independence, endpoint restrictions and
non-destructive migration rollback. Existing integration tests cover an empty rollback.

Android API 26/35/36 acceptance now actually uninstalls/reinstalls the same signed APK
and compares the app-scoped hash privately (artifacts retain only PASS). Native UI
tests capture documents, auth, DEMO home/locked controls, and guest → OTP → FREE.
Website tests cover all six translations, legal pages and tariff hierarchy.
The DEMO seedling emoji also renders on the minimum supported Android 8.0; native
API 26 review caught the unsupported test-tube glyph before publication.

Local isolated PostgreSQL migration/head consistency and focused tests passed during
implementation; full final counts, product HEAD, build/merge SHA, run/attempt and
artifact links belong to the task PR after the last push. No DEMO live activation,
publication or production acceptance is claimed by this source document. The real
WireGuard proof from PR #64 covers Android 0.24.0, not this new guest implementation.
