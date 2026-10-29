# Managed transport rollout (in progress)

Backend 0.21.1 → 0.22.0 (migration 0035), Android 0.14.2/code27 → 0.15.0/code28,
Windows 0.17.2 → 0.18.0, managed engine 0.3.0. These are minor feature increments,
not deployment or acceptance claims. Android and Windows native integration is
implemented in source; device and packaged-build acceptance remain pending.

Admission currently implements REALITY/Vision, VLESS/TLS, VMess/TLS, SS2022,
Hysteria2 and Salamander, each direct or `_relay`. Relays permanently forward the
encrypted TCP/UDP connection through INTERMEDIATE nodes to the selected exit.
WireGuard retains its compatible API and lifecycle. OpenVPN/OpenConnect and other
GPL/LGPL-dependent integrations are deferred; sing-box is excluded. AmneziaWG,
SSTP, native SoftEther and Hysteria1 still require audited adapters.

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
repository shell sources are unchanged. Windows has 293 passing frontend tests,
15 native tests, TypeScript, ESLint and clippy checks. Android packaging, Windows native/UI and DE/US
acceptance must be recorded against the actual PR
head, build SHA/run/attempt and artifacts; no historical binary is evidence.

Rollback retains the previous clients and disables new admission. Migration 0035
can downgrade only before any managed lease is issued; afterwards preserve its
schema/history and credential until all authorizations and usage are settled.
