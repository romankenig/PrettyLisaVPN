# Managed transports and rollout evidence

## Acceptance and deployment, 2026-10-29

The deployed backend is 0.22.1, schema 0035, product
`277053a5484bf681bf4c3be7e45a0803e3a63d63`, manual build 20261029184333/1.
The backend and fleet worker use the same immutable image. Managed admission is
enabled; DE, US and the intermediate node are READY. Node binary artifact
12923746083 came from engine run 40932133095/1, product 277053a, merge build
7a479dd2eb8319a88386eca0fd37f384ad8f2633. Its SHA-256 is
895dfb8063bcc7b32af10c39a3639b5ca6c529f4b89a2f1c6748418cae58f1a4.

All forty server combinations (ten managed families, direct/relay, DE/US)
confirmed handshake, DNS, HTTPS and the expected exit IP. Initial pass: 35/40;
all five failures passed a separate retry. Four initial HTTPS failures coincided
with a backend restart; one Salamander+ DNS failure was transient. All 45 grants
were removed. Redacted reports are retained on the main server under
`managed-source-validation-20261029/node-acceptance-owned-{sni,retry}.json`.

Windows product/build 4484c0f3a17ff54864a7eb772e5472ee644a379f, run 40948674534/2,
artifact 12932136870, passed 18/20 packaged DE cases. Each successful case had
40 seconds of sustained connection, a separate HTTPS request explicitly bound
to Wintun, and confirmed local/server cleanup. Native connected screenshots
show the actual selected method and DE exit IP. Only Hysteria 1 and Hysteria 1+
failed; both grants were removed. This prompted the isolated uplink correction
below. Follow-up client results and permanent download identities are recorded
in PR #38; these earlier binaries are not evidence for the corrected Hysteria.

The physical Android phone was disconnected, and the owner's Windows machine
retained its existing VPN. Real client acceptance uses an isolated Android
emulator and Windows runner, not fixture traffic. Android UI checks cover API
26/35/36; transport acceptance uses API 35. ARM64 phone and x86_64 emulator APKs
come from the same source but are separate architecture builds.

Android 0.15.2/code30 product/build abe454301c8ba8d8b763378ba4a2e2de68dd511a,
run 40950109996/1, artifact 12933100794, passed all 20 packaged US cases with
40-second sustained connections, independent VPN-bound HTTPS and all cleanups.
SS2022, VLESS, REALITY+ and Salamander+ needed the bounded second verification;
the other sixteen passed their first probe. All API 26/35/36 UI jobs passed.
Native screenshots confirmed Connected and the selected method.

The isolated Hysteria uplink correction is product/build
5f8aac754b8f6d31e1a8ce8099f41f685fc107ad. Windows follow-up 40953318291/1,
artifact 12933471228, passed Hysteria, Hysteria+ and the Hysteria 2+ control with
the same sustained HTTPS/cleanup criteria. Its tested client artifact is
12932423245: Windows 0.18.0, 71,531,520 bytes, SHA-256
b3d53955615131025b5a100d6f09221a89fdec56a7ad5b3fe877bb9fcb25475b.
The Android counterpart is run 40954115978/1. Its result, the final paginated
CI audit, publication identities and rollback catalog are maintained in
[PR #38](https://github.com/romankenig/PrettyLisaVPN/pull/38), avoiding another
binary build solely to record a completed run. The older full matrices prove
the unchanged adapters; only the corrected Hysteria factory uses these new
follow-up builds. No unverified newer implementation is inferred from an older
artifact. These are development builds, not signed store releases or endurance
proof for every physical device and network.

## Implementation and diagnostic history

Windows run 40948674534 attempt 2 confirmed the repaired private pipe and found
another boundary in Hysteria 1: its UDP listener skipped the outbound controllers
that bind desktop sockets to the physical interface. The uplink now uses the
same protected system dialer as Hysteria 2. A regression first failed because the
controller was never called; it now verifies the destination, UDP send/receive
and fail-closed behavior when protection refuses a socket. Existing version
numbers remain within the unfinished task. New packaged Hysteria acceptance is
required; other methods do not use this changed socket factory.

Android's first packaged six-case US acceptance (product ef77d8f, dispatch
40943421487/1) verified VLESS, SS2022, SS2022+, Hysteria 2 and Hysteria 2+,
including 40-second renewals, independent HTTPS and all six cleanups. VLESS+
failed before verification. Android 0.15.1/code29 → 0.15.2/code30 adds one bounded
retry for transient network verification errors and redacted stage diagnostics;
new artifact acceptance is still required. Cancellation, exit mismatch and
engine shutdown do not qualify for another network attempt. Backend and Windows
versions remain 0.22.1 and 0.18.0 respectively.

Continuation on 2026-10-29 keeps backend 0.22.1, Android 0.15.1/code29,
Windows 0.18.0 and engine 0.3.0 within this unfinished feature. Dispatch-only
Android/Windows acceptance now builds the current checkout, uses expiring
disposable accounts and selects each requested method independently. Success
requires the application's DNS/HTTPS/exit verification, 40 seconds of continued
connection, a second HTTPS request bound to the VPN, and confirmed cleanup.
Proof artifacts contain only outcomes, stable codes and native screenshots;
credentials, profiles and traffic logs are excluded. These checks are separate
from fixture UI tests. Actual run results and publication identities belong in PR #38.

Relay diagnosis found TCP established but TLS stalled with the previous
`www.cloudflare.com` SNI on the RU-to-US path. On the same forwarded port,
the owned `api.prettylisavpn.com` SNI completed TLS 1.3; a scoped MSS reduction
did not fix the old SNI. All three nodes now use the owned HTTPS endpoint
95.140.152.42 as their REALITY target and identity name. TLS 1.3, certificate
validation and HTTP/2 were checked from every node. Private identities were
backed up on-node before rotation, no managed leases were active, and WireGuard
configuration was unchanged. Real clients still enforce their private CA pin,
hostname and expiry; diagnostic certificate bypass was not added to runtime.

Backend 0.21.1 в†’ 0.22.0 (migration 0035), Android 0.14.2/code27 в†’ 0.15.0/code28,
Windows 0.17.2 в†’ 0.18.0, managed engine 0.3.0. These are minor feature increments,
not deployment or acceptance claims. Android and Windows native integration is
implemented in source; device and packaged-build acceptance remain pending.
Dashboard 0.4.0 в†’ 0.4.1 adds small corresponding-source download links. Its
publisher switches binaries, source archives and notices atomically; Android
0.15+ and Windows 0.18+ cannot publish without a matching source SHA and notices.
Archives remain stored with each immutable build, not only in expiring CI artifacts.

Admission currently implements AmneziaWG, SSTP, SoftEther, REALITY/Vision, VLESS/TLS, VMess/TLS, SS2022,
Hysteria 1/2 and Salamander, each direct or `_relay`. Relays permanently forward the
encrypted TCP/UDP connection through INTERMEDIATE nodes to the selected exit.
WireGuard retains its compatible API and lifecycle. OpenVPN/OpenConnect and other
GPL/LGPL-dependent integrations are deferred; sing-box is excluded.

The private `/vpn/sessions` API delegates to existing account-serialized quota,
device and country admission. The former WireGuard API remains compatible.
Each managed authorization has a unique port and an unprivileged process with a
hard deadline. Credentials derive from a dedicated `MANAGED_VPN_SECRET`, retained
until cleanup; they never enter PostgreSQL or logs. `MANAGED_VPN_ENABLED` defaults
to false; disabling admission preserves revocation.

The main server worker renews grants of at most 180 seconds. Ubuntu also enforces
an independent firewall deadline and process watchdog. Revocation writes a
tombstone, denies new packets, then confirms process/listener/firewall cleanup
before releasing reservations. A delayed grant cannot reopen revoked access.
Ansible installs helpers and the verified operator-provisioned artifact at
`/run/fleet/pl-node-engine`. Node identities remain private on the exit node.
Configuration uses fleet administration's `managed` method; READY requires a
real server-to-server probe. Hourly jobs are staggered across node/method pairs.

Android's private `:engine` process stays in the one APK. Binder control is
unexported and same-UID; parent death closes TUN. Verification binds DNS and HTTPS
to the VPN Network and checks the authorized exit IP. Sleep or loss of the old
physical network alone does not prove that a working VPN has failed.

Windows keeps the UI unelevated. A separate elevated host authenticates both
ends of a local private pipe by process ID and contains the engine in a
kill-on-close Job Object. Only private stdin carries credentials. One elevation
can serve successive attempts after confirmed cleanup. The pinned, signed
official Wintun binary is redistributed under its binary license, with notices;
its GPL driver sources are not built or linked into the application.

The first full Windows live run (40946090883, product 5e46b6a) provisioned and
cleaned all twenty managed leases, but none reached verification. A native
regression reproduced `ENGINE_UNAVAILABLE`: Rust `File::read` turns the empty
nonblocking pipe's `ERROR_NO_DATA` into EOF. The host now uses bounded Win32
reads, preserving idle connections and fragmented frames while rejecting a
closed peer or incomplete timed-out frame. Delayed/fragmented, idle-timeout and
partial-frame tests cover this boundary. Windows remains 0.18.0; real acceptance
of the corrected packaged build is required before publication.

Advanced settings persist a nonempty device-local subset (default all). Each
attempt snapshots it and prefers the last verified enabled method. Confirmed
cleanup gates fallback; starting an engine is never sufficient for success.

Validation remains in progress: local Go tests cover encrypted TCP/UDP, identity
rejection, strict parsing, cancellation and renewal. Backend tests cover admission
boundaries, credentials and cleanup. PostgreSQL migration and 610 backend tests
passed in an isolated database (11 environment-specific skips). Five shell tests
required a rerun after correcting CRLF in the Windows-to-Linux validation archive;
repository shell sources are unchanged. The initial 864b3ca milestone has 293 passing Windows frontend tests,
15 native tests, TypeScript, ESLint and clippy checks. Android packaging, Windows native/UI and DE/US
acceptance must be recorded against the actual PR
head, build SHA/run/attempt and artifacts; no historical binary is evidence.

Rollback retains the previous clients and disables new admission. Migration 0035
can downgrade only before any managed lease is issued; afterwards preserve its
schema/history and credential until all authorizations and usage are settled.

AmneziaWG uses pinned MIT amneziawg-go v3.1.20260828 and the small MPL Xray
proxy adaptation in engines/managed/amnezia. Native loopback tests confirm TCP,
UDP and rejection of unauthorized keys. Kernel modules and GPL utilities are
not used. Its source integration adds two more managed adapter cases; repeat
packaged Android/Windows and real-server acceptance for the resulting head.

Hysteria 1 uses a bounded MIT protocol-v3 adapter over the current pinned QUIC
runtime, distinct from Hysteria 2. It authenticates before forwarding, checks the
pinned CA plus hostname/expiry, and uses the protected socket/TUN lifecycle.
Official v1.3.5 interoperability passes TCP and UDP in both directions; the old
Go 1.20 reference executable is test-only, never redistributed in the clients.
The adapter uses QUIC's standard congestion control and advertises a 30 Mbit/s
rate. Source tests additionally cover fragmented UDP, malformed frames, wrong
credentials/identity, core integration and shutdown. CI repeats races and fuzzing.
Backend admission and both client selectors contain 22 methods including direct
WireGuard and every implemented relay variant. This is source implementation,
not a claim that all methods have already passed DE/US device acceptance.
The expanded race suite found unsynchronized closed flags in upstream Hysteria 2.
The pinned core is now copied and patched reproducibly (two atomic flags), with
its checksum, MPL notices and modified sources retained. No check is disabled.
The same full race suite exposed gRPC Send/CloseSend concurrency. The pinned
patch now cancels blocked RPC sends and serializes send/close in both framing
modes. Regression tests cover blocked sends and writing after close. Hysteria 1
also recreates expired UDP upstreams instead of retaining a dead flow.

SSTP's MIT wire/PPP foundation is in `engines/managed/sstp`, with upstream file
hashes and notices. It is registered in backend and client source. TLS loopback
tests cover packet exchange, credentials, certificate pin/hostname, shutdown,
rejection before authentication, and current-nonce crypto binding. Its in-memory
TCP/UDP network adapter passes encrypted echo and shutdown tests. An isolated
official SoftEther Stable 4.41/9787 reference also passed tunneled DNS and HTTPS;
the reproducible CI test retains its archive hash and never redistributes that
reference binary. PPP peers may use a dummy inner address; it creates no system
route and cannot bypass authentication or binding. The reviewed
upstream system-TUN/server code is not used; packet admission is owned here.

The native Windows capture for source 006364d (merge build 88e540e,
UI run 40873782903) confirmed bounded scrolling; visual inspection also found a
clipped fieldset legend, now replaced by an inset accessible group heading.
The source 53cd8d5 native capture (run 40876641682, merge build
3e41564d152b1c35b4e3c97189eb0f45917e97c4) verified the correction. The newly added
SSTP rows still require their next capture. Ansible's local artifact check
now uses its private temporary directory for read-only worker containers.

First fleet acceptance used the real Linux artifact from run 40873782931,
attempt 1, product 006364d, merge build 88e540e53c254073e1b0ce47cff035b41068714b,
artifact 12897296698. All three node installations preserved existing WireGuard
configuration. Of 32 DE/US direct/relay probes, 21 confirmed DNS, HTTPS and the
expected exit IP; all probe grants were removed. Hysteria 1 failed all four cases;
some TLS/QUIC relay cases also failed and require diagnosis. This is not complete
fleet or client acceptance. API admission remains disabled on the old backend.

A regression test then reproduced Hysteria 1 resetting a completed upstream
response instead of delivering QUIC FIN. The adapter now preserves queued bytes
on normal EOF; the new finite-response test passes 30 consecutive local runs.
The changed code still requires new artifact and fleet acceptance. Versions stay
within this unfinished task (backend 0.22.0, Android 0.15.0, Windows 0.18.0,
engine 0.3.0); current CI/build evidence is maintained in PR #38.

The corrected Hysteria binary from product/build
61aa4f6e6132e086920f89208c88ece8ad739d3b, run 40879877744 attempt 1,
artifact 12898884722, SHA-256
e98bbc2861c6830d27ba7ce0ddd784e56264024ed5df9493f0268f66e361dcdc,
passed direct DE, direct US and relay DE DNS/HTTPS/exit checks. The new twenty-case
series still failed five US relay paths (REALITY, VLESS, VMess, Hysteria 1/2),
plus one DE VMess relay DNS check. Every test grant was removed. These network
failures are not hidden by the passing builds; further diagnosis and client
acceptance remain open. SSTP acceptance is separate and not covered by that binary.

Native SoftEther now uses bounded MIT PACK/auth/block codecs with an owned TLS
session, per-lease static Ethernet segment, ARP and source validation. It shares
only pinned TLS verification and the in-memory TCP/UDP adapter with SSTP. A fresh
challenge is mandatory; pre-authentication data, replay, anonymous authentication,
spoofed inner sources and ambiguous control fields are rejected. Independent
SoftEther Stable 4.41/9787 native-server DNS/HTTPS acceptance passed in a disposable
container; CI repeats the pinned reference. Both client catalogs and backend
admission now include SoftEther/SoftEther+. No new version increment within this
unfinished transport task. Actual fleet and device acceptance remain outstanding.

Owner-requested Android publication on 2026-10-29 used product/build
0b1301566e4f5cab7f672ff38f4abe1999a1b255, push run 40884321086 attempt 1,
artifact 12901602893, Android 0.15.0/code28. All API 26/35/36 jobs passed. The
published APK SHA-256 is ec4fda2b8c659fc38fc771ff1396881bc2e767a3a4f6b6028d9fa6885387c640;
its exact corresponding sources are retained and downloadable behind dashboard
authentication. This build predates native SoftEther. Backend admission remains
disabled while deployment and device validation are incomplete. The owner has
requested a smaller replacement because this universal debug APK is 253155576 bytes.
