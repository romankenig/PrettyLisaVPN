# Device-limit cabinet across platforms

## Versions and scope

| Component | Before | After |
| --- | --- | --- |
| Backend | 0.45.0 | 0.46.0 |
| Windows | 0.29.1 | 0.30.0 |
| Android | 0.28.1 (56) | 0.29.0 (57) |
| iOS | 0.4.1 | 0.5.0 |
| macOS | 0.3.1 | 0.4.0 |
| Chrome Extension | 0.4.0 | 0.5.0 |
| Website | 0.6.1 | unchanged |

MINOR: new restricted account cabinet and device activation contract. Linux and
Android TV currently have scaffolds, not shipping account screens. Their platform
values use the same backend contract and are included in integration tests; their
future clients must opt in and implement this gate. No platform is exempt from
the server-side device cap. The website payment portal has separate cookie OTP
authentication, never registers a VPN device and never grants VPN access.

## Implemented contract

New clients send `allow_device_management: true` to `POST /auth/verify-otp`.
Valid OTP at five active devices creates/reuses a `PENDING` installation and
issues ordinary durable session credentials. The pending device consumes no
active slot. Its real successful OTP time is recorded. Existing admitted devices
continue normally, including when `active_device_count == 5`.

`GET /me` adds `device_limit_reached`: true only for the requesting pending
installation. The session can read `/me`, refresh tokens, list/revoke devices,
activate the current device, and log out. Other private capabilities reject it
with HTTP 403 / `device_limit_reached`. Disabled controls are not the security
boundary. Private responses remain non-cacheable; no browsing data is collected.

`GET /devices` includes the requesting pending device, but hides other pending
installations so older admitted clients retain their existing device enum.
Revoking the pending device invalidates its sessions without consuming a slot.

`POST /devices/activate` rechecks the user, session and current device under the
account lock. If a slot exists, it activates that installation with its existing
session; otherwise HTTP 409 / `device_limit_reached`. Repeated activation is
idempotent. Two competing installations cannot create a sixth active device.
Activation is attempted after removing another device and when refreshing the
device list, so a slot freed elsewhere can be claimed without another OTP.

## UI and cleanup

Chrome, Windows, Android, iOS and macOS show a red device-limit notice and links
from the notice/account/settings to Devices. VPN and other product actions are
disabled and dimmed; privileged background screens/requests are not mounted.
Device removal, logout and explicit local credential cleanup stay available.
Local cleanup does not claim server-side revocation if the network is unavailable.
After confirmed activation, `/me` is refreshed before ordinary features return.
All new copy is localized into the existing six languages.

## Compatibility, migration and delivery

Migration `0051_pending_devices` adds enum value `PENDING` and updates the
revocation-timestamp constraint. No changes to active-slot counting or paid
entitlements. Without opt-in, existing clients retain HTTP 409 at the cap.
Deploy backend before the new clients. New clients on an old backend still
receive the old cap error; they cannot synthesize an authorized cabinet.

Rollback requires care: old backend code cannot decode pending rows. Downgrade
refuses while any pending row exists; revoke/resolve those rows explicitly or
roll back only to a backend that understands them. The unused enum value is
retained on schema downgrade, matching PostgreSQL enum migration conventions.

Base product SHA after synchronizing PR #89: `29dd77c2` (develop).
The analytics task already uses backend 0.45.0; this task uses 0.46.0.
This task does not merge, tag, publish downloads or deploy production. Backend
follow-up is a separately authorized 0.46.0 rollout, then client publication.
The PR records the verified product HEAD, actual build SHA/run/attempt, native
screenshots, artifacts and every completed Actions workflow. Local fixtures are
synthetic and do not claim real VPN traffic or changes to a production account.

Validation includes seven-platform PostgreSQL auth/access/activation tests,
concurrent slot admission, client parsing/session tests, installed MV3 navigation,
and native Windows/Android/Apple cabinet screenshots. See the PR for actual
results and any remaining platform build limitations.

Local verification before the first push: backend Ruff and mypy pass; migration
upgrade/check pass; 1,132 tests passed in the Linux run, with three PostgreSQL
connection/worker timeouts through Docker Desktop's host bridge. All affected
quota/support tests plus the new device-limit suite then passed directly against
the disposable PostgreSQL instance (22 tests). The complete isolated CI run is
still required. Windows: 390 Vitest tests, TypeScript, ESLint and Vite build pass.
Chrome: 54 tests, formatting/lint/TypeScript/build and installed MV3 review pass;
the existing browser billing-portal review also passes. Apple structural checks
and five packaging unit tests pass locally; Swift/native builds and Android
build/instrumentation require their CI runners.
