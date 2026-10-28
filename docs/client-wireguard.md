# WireGuard clients — backend 0.18.0, Windows 0.15.0, Android 0.12.0

This task follows PR #31 (merged at `86831bc0a6afbc63fc2221f4810b16ae42b23604`).
Dashboard source `39a2b6b346ecdd1cbbe19125cba2da8d82d1d296` is already deployed
on the main server at https://api.prettylisavpn.com/dashboard/ with operator
login/password. The initial dashboard deployment used backend 0.17.0; the current
development runtime and client acceptance evidence are recorded below and in PR #32.

## Versions and compatibility

- Backend 0.17.0 → 0.18.0: customer WireGuard API, migration
  `0030_client_wireguard`, short-lived node grants and account quota integration.
- Windows 0.14.1 → 0.15.0: managed official WireGuard and real tunnel verification.
- Android 0.11.1 / code 20 → 0.12.0 / code 21: one APK, WireGuard GoBackend,
  system consent, foreground lifetime, real tunnel verification.
- Dashboard remains 0.1.0. Customer authentication remains email OTP.
- The removed legacy `/vpn/sessions` and managed-engine APIs remain absent.
  Customer endpoints are additive and initially disabled by `CLIENT_VPN_ENABLED=false`.
  Old clients retain their placeholder behavior; they cannot consume new leases.

## Control plane

`POST /vpn/wireguard/sessions` accepts `public_key`, `country` (AUTO or ISO code)
and a UUID `Idempotency-Key`. It authenticates the customer/device, locks the
account, reserves quota and a unique node address, and returns PROVISIONING.
`GET /current`, `GET /{id}`, `POST /{id}/heartbeat`, `DELETE /{id}` and
`GET /{id}/probe` are scoped to the authenticated account **and device**.
Responses are private/no-store. The probe compares the actual caller IP with
the node's configured egress addresses. No private client key reaches the API.

The main-server fleet-worker runs a separate customer lease loop. Configuration
remains exclusive; customer renewals/revocations may share a CHECK lock, and a
new fleet operation cannot race an unfinished customer claim. Grants last at most
180 seconds and are refreshed every 30 seconds. Since backend 0.19.0, established
access does not expire for missing client heartbeats: Android sleep is expected.
Unfinished provisioning is bounded to 90 seconds. Auth-session, device, account, node and paid-period
eligibility are checked again by the worker. Premium and Platinum share rules.
Free reserves the remaining account-wide UTC hour and ends by UTC midnight.
Unused time returns only after confirmed peer removal; uncertain outcomes keep
the address, device slot and budget reserved. Historical usage remains counted.

On Ubuntu the helper journals customer grants under its protected persistent
directory before mutation. Per-client kernel firewall rules enforce UTC lease
deadlines independently of the worker and cleanup timer. Renewal atomically
replaces the deadline rules. The existing timer removes expired peers/rules;
revoke confirms both peer and rule cleanup. Monitoring keeps its separate,
reserved last subnet address and observes real customers when present.

## Clients

Both apps replace only the WireGuard placeholder in the shared executor. The
other 13 methods still wait three seconds and fail; progress continues to name
the current and previous method. Success stops the sequence and shows WireGuard.
Cancellation finishes local teardown and remote revocation before another method.

Android uses `com.wireguard.android:tunnel:1.0.20260102` (Apache-2.0 wrapper,
MIT wireguard-go); GPL command-line libraries are excluded and packaging checked.
No companion APK is required. The app requests Android VPN consent, keeps a
private foreground service, and binds DNS and HTTPS verification to the VPN
Network whose address matches the lease. A fresh WireGuard handshake is required.
Backend 0.19.0 advertises `heartbeat_required=false`. Android 0.12.2 preserves the
verified tunnel across sleep and temporary API failures, including an ambiguous
refresh (which is never replayed). Confirmed terminal authorization failure,
expiry or system VPN revocation still stops the connection. Absent capability
retains the legacy bounded heartbeat policy. See [sleep stability](android-sleep-stability.md).
The foreground lifetime uses Android's documented approved-VPN `systemExempted`
eligibility, after the VPN is established and with a runtime consent check.
AGP 8.11's alarm-only static permission check is narrowly annotated on that service
and its startup; all other lint checks remain enforced. No unrelated exact-alarm
permission is added. See [Android's eligibility criteria](https://developer.android.com/develop/background-work/services/fgs/service-types#system-exempted).

Windows manages the separately installed [official WireGuard client](https://www.wireguard.com/install/).
It never bundles a GPL driver. Native commands generate keys, restrict local
configuration ACLs to the user/SYSTEM/Administrators, and install/remove only
`WireGuardTunnel$PrettyLisaVPN` through Windows UAC. No arbitrary command/path is
accepted from the webview. An existing foreign VPN is detected without changing
its routes. DNS and HTTPS proof are bound to the assigned tunnel source address.
Private key/configuration content is never returned to the webview or logged.
An app crash leaves a server-owned reservation until explicit cleanup or the
auth/entitlement deadline; the next Connect recovers and removes it before creating
another peer. Free time continues while a reservation remains active, including
sleep or an abandoned process. Short node grants still fail closed if the worker stops.
Explicit disconnect/logout confirms teardown. Refresh credentials are consumed
once and serialized with account transitions; ambiguous refresh requires OTP.

## Rollout and rollback

1. Apply migration 0030 and deploy the new backend with customer access disabled.
2. Update each enrolled Ubuntu helper through its explicit configuration API;
   idempotent configuration preserves keys and original configured_at.
3. Enable CLIENT_VPN_ENABLED on both API and fleet-worker on the main server.
4. Verify a real client connection on a disposable foreign test host; inspect
   handshake, tunnel-bound DNS/HTTPS, correct egress, expiry and confirmed cleanup.
5. Supply CI-built APK/EXE links tied to the tested source/build SHA/run/attempt.

To roll back, first disable new customer requests and drain all customer peers
with the current worker. Confirm all leases have removed_at before migration
downgrade; the downgrade refuses live reservations. Never simply delete lease
records. Client rollback does not remove the official Windows WireGuard install.
Keep the password-protected dashboard and server-owned hourly processes running.

Implementation and automated tests are not proof of a phone or Windows Internet
connection. PR #32 records the final status and exact artifacts for each live
attempt. The owner's PC VPN must remain enabled; use an isolated runner for
real full-route Windows tests. Phone tests use downloadable APKs without USB.

## Development evidence — 2026-10-27

Backend source `33a096e807f0905dffca93e7078a4f117d54570b`, manual development
build `20261027105359`, attempt 1 (no GitHub deployment run), is running as
`0.18.0-dev.20261027105359+g33a096e807f0905dffca93e7078a4f117d54570b`.
Migration 0030, health/readiness/version and dashboard HTTP authentication were
verified. Both Ubuntu helpers were upgraded through the administrator API;
CLIENT_VPN_ENABLED is true for API and the main-server worker.

The new customer-grant path was exercised in isolated namespaces on both nodes:
US→DE at 10:58:11 UTC and DE→US at 10:58:23 UTC passed handshake, DNS, HTTPS,
expected egress, speed transfer and confirmed peer/namespace cleanup. This is
server data-plane evidence, not a client-app acceptance result.

Local/isolated validation: backend 534 passed, 1 skipped (Docker tests separately
covered by Backend CI), Ruff, strict mypy and Alembic drift checks; Windows 260
TypeScript tests and 12 native tests, typecheck/lint/format and native clippy.
Windows native UI review [40493619491](https://github.com/romankenig/PrettyLisaVPN/actions/runs/40493619491)
passed for PR head `c98f912186a8461ee34f1485835e3ddc654c0066`, temporary merge build
`db897cdac2dd9a427dd7a1d516571d87021bc28f`, attempt 1. It uses UI fixtures,
not a real Windows tunnel.

The first isolated Android live attempt
[40493854618](https://github.com/romankenig/PrettyLisaVPN/actions/runs/40493854618)
used source/build `c98f912186a8461ee34f1485835e3ddc654c0066`, attempt 1.
Authentication/provisioning succeeded, but VPN verification failed; all placeholders
then failed as designed. Server removal was confirmed. No successful client
connection is claimed by that run. Subsequent evidence includes only fixed stages,
HTTP status and aggregate WireGuard counters/handshake, without destinations,
keys, tokens or exception messages. Tunnel proof explicitly bypasses HTTP proxies.

Attempt 2 [40495655538](https://github.com/romankenig/PrettyLisaVPN/actions/runs/40495655538),
source/build `eeebce4b9ba3314925decefbffd46ebfaf05005d`, reported a SocketException
at HTTPS startup, no handshake, 148 transmitted / 0 received bytes. The server
observed the peer briefly without a handshake and confirmed removal. The adapter
now allows up to 20 seconds for the initial WireGuard handshake, then makes at
most two network-bound verification probes on the same tunnel. It never declares
Connected from interface presence alone. These probes do not create new leases.

Acceptance accounts are disposable, with credentials held only in protected files
and a temporary Actions secret. A persistent main-server timer revokes the account
after two hours, including rotated sessions; manual cleanup runs after acceptance.
The independent fleet 24-hour window ends 2026-10-28 09:42:10 UTC; its main-server
report timer is scheduled for 09:52:10 UTC. It is not yet a completed 24-hour result.

## Android 0.12.1 / code 22 — sustained connection fix

The owner's phone confirmed working VPN egress but then showed the server-loss
notice and disconnected. Server evidence from 12:01–12:05 UTC on 2026-10-27:
DE/US tunnel probes returned 200 through the correct egress; no heartbeat was
acknowledged, and both leases were removed with VPN_CLIENT_LOST after ~90 seconds.
The earlier 0.12.0 emulator success lasted only ~20 seconds and did not exercise
renewal. The observed old-route heartbeat request is consistent with reuse of
pre-tunnel HTTP connections; no packet contents or browsing history were captured.

0.12.1 binds both authenticated API requests and public metadata/notice requests
to the same Android VPN Network used for successful initial verification. Each
route change gets separate connection pools and VPN-bound DNS/sockets; disconnect
restores a fresh default-route pool. There is no process-wide network binding and
no automatic replay of OTP, refresh, billing or other mutations. See Android's
[Network socket/DNS contract](https://developer.android.com/reference/android/net/Network).

Lease renewal alone retries offline/network_uncertain/service_unavailable within
70 seconds including its normal 30-second interval. The backend keeps its 90-second
heartbeat timeout; at most one 15-second blocking call can unwind after cancellation.
Invalid authorization, ambiguous token rotation, remote revocation and session
expiry still stop the tunnel. Unit regressions cover route/pool replacement,
no fallback to pre-VPN sockets, both API consumers, transient recovery, sustained
outage, terminal failure and cancellation.

Real acceptance now holds the connection for at least 120 seconds, requires at
least three acknowledged heartbeats, checks public API reachability, repeats HTTPS
through the VPN, checks the rendered server-loss notice is absent, and confirms
remote cleanup. This test uses one disposable account and one real connect attempt
per explicit workflow dispatch. The current task's exact result and artifacts
are recorded in PR #32; phone stability still requires the owner's manual retest.
