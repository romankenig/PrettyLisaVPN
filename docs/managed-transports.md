# Managed transport rollout (in progress)

Backend 0.21.1 → 0.22.0 (migration 0035), Android 0.14.2/code27 → 0.15.0/code28,
Windows 0.17.2 → 0.18.0, managed engine 0.3.0. These are minor feature increments,
not deployment or acceptance claims. Android and Windows native integration is
implemented in source; device and packaged-build acceptance remain pending.
Dashboard 0.4.0 → 0.4.1 adds small corresponding-source download links. Its
publisher switches binaries, source archives and notices atomically; Android
0.15+ and Windows 0.18+ cannot publish without a matching source SHA and notices.
Archives remain stored with each immutable build, not only in expiring CI artifacts.

Admission currently implements AmneziaWG, REALITY/Vision, VLESS/TLS, VMess/TLS, SS2022,
Hysteria 1/2 and Salamander, each direct or `_relay`. Relays permanently forward the
encrypted TCP/UDP connection through INTERMEDIATE nodes to the selected exit.
WireGuard retains its compatible API and lifecycle. OpenVPN/OpenConnect and other
GPL/LGPL-dependent integrations are deferred; sing-box is excluded. SSTP and native
SoftEther still require audited adapters.

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
Backend admission and both client selectors contain 18 methods including direct
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
hashes and notices. It is not admitted or linked into clients yet. TLS loopback
tests cover packet exchange, credentials, certificate pin/hostname, shutdown,
rejection before authentication, and current-nonce crypto binding. Its in-memory
TCP/UDP network adapter now passes encrypted echo and shutdown tests; official-peer
interoperability and admission integration remain required. The reviewed
upstream system-TUN/server code is not used; packet admission is owned here.

The native Windows capture for source 006364d (merge build 88e540e,
UI run 40873782903) confirmed bounded scrolling; visual inspection also found a
clipped fieldset legend, now replaced by an inset accessible group heading.
The next capture must verify that correction. Ansible's local artifact check
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
