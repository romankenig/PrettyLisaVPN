# Android: one APK and automatic connection plan

Owner request: one APK, try every available encrypted DE/US method until an
independent tunnel check succeeds, then repeat acceptance with at most three
manual client attempts. One attempt means one Connect press and its entire
internal candidate loop. New round: **0/3**, no device success claimed yet.

## Versions and compatibility

- Android 0.9.0/code17 → 0.10.0/code18 (MINOR): a single installed application.
- Backend 0.14.0 → 0.15.0 (MINOR): additive authenticated managed-plan endpoint.
- Node agent 0.2.0 → 0.3.0; managed engine 0.1.0 → 0.2.0 (MINOR): complete catalog.
- PostgreSQL schema remains 0028; Windows remains 0.13.0. Windows managed-engine
  wiring is still pending and the host's Kaspersky VPN must remain enabled.

The old `/managed` response remains compatible with the two-APK preview.
The new APK uses `/managed-plan`; deploy the node and backend before installing
it. Install only `app-debug.apk` over the previous PrettyLisaVPN development APK.
The old PrettyLisaVPN Engines app is no longer used and can be uninstalled.
No sing-box or GPL/AGPL/LGPL native engine is added. The approved Xray/MPL and
MIT/BSD/Apache/ISC dependency policy remains in force.

## Connection loop

The Android coordinator preserves all supported WireGuard UDP candidates, then
appends every profile in the authenticated server plan, in server order:

1. VLESS/REALITY/Vision TCP.
2. VLESS/TLS, VMess/TLS and Trojan/TLS, each using raw TCP, WebSocket, gRPC,
   HTTPUpgrade and XHTTP (15 variants).
3. Shadowsocks AEAD and Shadowsocks 2022.
4. Hysteria 2 TLS and Hysteria 2 with Salamander.

This is 20 managed profiles plus the node's WireGuard candidates. It is complete
coverage of the **currently implemented catalog**, not every family in the Habr
article. OpenVPN/OpenConnect, IPsec, AmneziaWG, SSH and other unimplemented families
are not advertised as working automatic candidates. Their separate adapters and
license-compatible packaging remain follow-up work.

Each candidate has 30 seconds. It must stop before the next starts. Cancellation,
owner/device changes, expiry and unconfirmed cleanup abort the loop. Every
candidate shares the same owned backend session and original allowance. A fully
unsuccessful 21-candidate loop can take about 11 minutes, within the existing
15-minute development lease cap; a shorter account deadline takes precedence.
The UI keeps a short trying/switching comment visible while starting and checking,
and displays the actual winning method/transport only after verification.

One unexported `VpnService` in the APK's private `:engine` process owns Xray and
TUN for every protocol, including WireGuard. IPC requires the same UID. The main
process never loads a native Go engine. WireGuard's Java key helpers remain;
unused WireGuard native binaries/services and the second APK module are removed.
Owner death, unbind, Android revoke, deadline and physical-network loss close the
tunnel. Main-process background endurance remains a separate device test.

The canary selects this application's VPN network and checks owner, address,
default route and DNS configuration. A bounded UDP DNS query to 1.1.1.1 is bound
to that network and validates the transaction/question/answer. HTTPS is also bound
to it, with certificate verification and no proxy, redirects or physical fallback.
The fixed DNS lookup cannot reuse a system cache or hang the next candidate.
Only closed stage codes are exposed in debug UI; no browsing history, DNS queries,
destinations, credentials or packet contents are logged.

## Server and rollback

`POST /vpn/sessions/{id}/managed-plan` authenticates session/device ownership and
returns a bounded private plan with `Cache-Control: no-store`. The existing HMAC
credential and durable lease intent/revocation are reused. Node agent mTLS/bearer
`PUT /v1/managed/{id}/plan` starts one unprivileged native process with 20 adjacent
listener ports. One revoke/EOF/expiry closes all listeners and established sockets.
Retries never extend the lease; tombstones block resurrection. Failed cleanup
reserves the ports until termination is confirmed.

TLS profiles pin a node-private CA SHA-256, not a leaf certificate. Xray verifies
the chain, hostname and validity under that pinned CA. Private keys stay in the
protected node configuration/stdin. REALITY retains its existing public-key
authentication. The preview range is intended to hold two complete plans (40
ports) on both TCP and UDP; SSH/control-plane rules remain separate.

Rollout: confirm no active preview leases, install the new binary/wheel and private
TLS configuration, apply bounded TCP/UDP rules, deploy backend, verify actual
runtime health/version, then share the single APK with its exact source/license
archive. For rollback, disable new issuance and confirm all leases removed before
rolling back node binaries. Keep additive schema0028 and old immutable artifacts.

## Evidence and acceptance

Local tests cover real encrypted TCP/UDP exchange for every managed variant,
strict plan parsing, a 21-candidate loop with success only on the last candidate,
all-failed cleanup, and PostgreSQL-backed issue/revoke recovery. Android CI must
additionally exercise actual system consent, native TUN, DNS/HTTPS, failure,
revoke and process restart on API26/35/36 with the single APK. These isolated
tests do not prove a real DE/US connection on the owner's network.

Previous round ended at **3/3 failed**: the last DE session on 2026-10-24 started
06:30:56 UTC and reported DNS_FAILED; server authorization, managed node and WG
peer were removed. Do not mix those attempts with the new round.

Exact checked product HEAD, actual build SHA/run/attempt, all workflow/job results,
download links, live deployment identity and the three bounded manual outcomes
are maintained in [PR29](https://github.com/romankenig/PrettyLisaVPN/pull/29).
At this document's introduction, the new code is not deployed and no new APK or
manual acceptance success has been verified. Do not cite old e012594 artifacts
as evidence for this implementation.
