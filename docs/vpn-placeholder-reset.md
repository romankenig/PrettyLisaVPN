# VPN reset: replace the implementation with adapter slots

Owner request: remove all real VPN connection code, including engines and the
server implementation; retain automatic fallback and short progress messages.
The scope was explicitly extended to server code and DE/US configuration.

## Versions and rollback

| Component | Before | After |
| --- | --- | --- |
| Android | 0.10.0 / code18 | 0.11.0 / code19 |
| Windows | 0.13.0 | 0.14.0 |
| Backend | 0.15.0 | 0.16.0 |
| Node agent / managed engine | 0.3.0 / 0.2.0 | removed |
| Database schema | 0028 | 0028, unchanged |

This is a pre-1.0 breaking MINOR task. PR #29 was merged first, preserving the
complete previous implementation at `dc3789904cb903eb100b9e35a3bea436146a753a`.
Its product head was `2504051955210f5bad5755839fe7ed2b51e4122b`.
[PR #29](https://github.com/romankenig/PrettyLisaVPN/pull/29) contains the earlier
release/rollback map. Rollback requires restoring a matching client/backend/node
set; installing an old client alone cannot revive retired listeners. Android
downgrade normally requires uninstalling or a new build with a higher versionCode.

## Shipped execution, not an animated mock

The 14 adapters are separate files under each client's `vpn/placeholders` directory:

1. WireGuard
2. AmneziaWG
3. OpenVPN (TCP/UDP family)
4. IPsec
5. SSTP
6. SoftEther VPN
7. AnyConnect / OpenConnect (including camouflage)
8. Shadowsocks
9. Shadowsocks-2022
10. VMess
11. VLESS (TLS/REALITY/Vision family)
12. Trojan
13. SSH
14. Hysteria / Hysteria 2 (including Salamander)

These are the agreed families from the owner's article list, not every combination
of transports/obfuscators. The loop invokes each real adapter entry point, awaits
its three-second cancellable delay, receives failure, finishes its cleanup and
then invokes the next. A complete shipped cycle takes about 42 seconds. Country
and cancellation are passed to the adapters. Repeated Connect clicks cannot run
parallel loops; Cancel/logout/account change stops further attempts. Reconnect
starts from WireGuard. Restart never restores a Connected flag.

No placeholder opens sockets, requests system VPN permission, starts a service,
creates keys, allocates a backend session or spends a Free quota. The UI says this
is placeholder mode and shows “trying X”, “X did not connect, trying Y”. After the
last failure it reports all methods tried. It never reports Connected for a stub.

## Adding a real method later

Replace that method's factory, preserving the `ConnectionAdapter` contract and
registry order. The adapter owns setup, bounded verification and cleanup. It must
return verified success only after proving Internet connectivity through its own
tunnel. Cancellation must release resources; a failed cleanup stops fallback.
Windows supplies an AbortSignal; Android uses coroutine cancellation. Both stop
on verified success and show the adapter's public method details. Integration
tests inject a verified adapter to prove this branch without shipping a fake success.
Credentials, provisioning, tunnel verification and platform permissions are future
work and must be implemented within the real adapter, not the UI.

## Removal and data preservation

Removed: WireGuard/native commands and dependencies, Android engine services/AIDL,
Go/Xray engine and its build/licensing archives, server node agent, profile runners,
obfuscators, Ansible VPN provisioning, session and credential APIs/workers, runtime
configuration and obsolete tests. Engine-specific workflows are removed with their
products; client/backend CI and native acceptance remain.

Retained: auth/account/device/billing/support code, platform credential storage,
public location, translations, navigation and design system. Historical SQLAlchemy
mappings live in `legacy_vpn`; they have no provisioning, node calls or connection
API. Existing migrations and historical Free usage are retained for account data,
support ownership validation and rollback. No database schema is dropped.
`GET /vpn/countries` remains authenticated metadata, returning DE/US with zero
quality and unavailable status. Placeholder tests can select these countries.

## Evidence and acceptance

Baseline Android debug APK from source `2504051`, run `40179327801`, attempt 1:
111,051,208 bytes, SHA-256
`f23ff9eff93e79c653efd5c8ccdc13de1f1731a99f5ab176d4fe72b6d5e948c8`.
Baseline Windows native UI debug exe, run `40179331275`, attempt 1, PR merge tree
`86094b9712014fcc235a87ac883565f72fb5c033`: 26,271,232 bytes.
Compare the same debug package types/architectures, separately from compressed ZIPs.

The task PR records the verified final product SHA, every CI run/attempt, binaries,
screenshots, exact after sizes, removed/net source lines and actual node retirement.
Artifact `build-identity.json` identifies the checkout (including temporary PR merge
SHA), version, run/attempt and hash. A source manifest alone is not deployment proof.

Install the new single Android APK over the existing app; launch the Windows
development exe using the real API (the UI-review exe uses fixture APIs and is not
the user download). Sign in, check account/devices/settings/subscription/support,
then press Connect once: watch the 14 methods fail and test Cancel on a second
run. This verifies the replacement shell, not a real VPN connection. The previous
three-attempt real-VPN acceptance goal is superseded by this reset.

## Development retirement evidence — 2026-10-26

PR #29 merge `dc3789904cb903eb100b9e35a3bea436146a753a` was deployed by
Backend run `40310081716`, attempt 2. Its previous manual release had root-owned
files that blocked the deployment user; ownership was repaired without changing
secret contents or weakening mode 0600.

The reset backend was built from committed source
`55643dacce7fae69ce3199a34004c97373963b80` on the development host and deployed
at 11:56 UTC. This was a manual SSH build, not an Actions-produced binary.
Backend validation runs `40318257073` (push) and `40318264955` (PR), attempt 1,
passed before deployment. Runtime:
`0.16.0-dev.20261026115620+g55643dacce7fae69ce3199a34004c97373963b80`.
Release directory:
`/opt/prettylisavpn/releases/55643dacce7fae69ce3199a34004c97373963b80-manual-reset-20261026115620`.
The release retains previous.env, previous-release, previous-image-id,
runtime-identity.json and image-id. Canonical env remains mode 0600 and belongs
to prettylisa-deploy. The first manual attempt encountered Windows line endings
before deployment and successfully verified rollback to the previous release;
the completed attempt normalized the shell script to LF.

Fresh checks after deployment: health and readiness OK, PostgreSQL/Valkey ready,
exact runtime version confirmed, POST /vpn/sessions returns 404. Before and after:
1 account, 6 historical device rows, 63 terminal VPN session rows, zero unremoved
sessions/credentials/managed leases. No account, device or history rows were deleted.

DE and US agent databases also had zero active/unremoved managed leases before
retirement. Project services were disabled/stopped, then configs, managed binaries,
agent virtualenvs, WireGuard keys/profiles, obfuscators, service units and owned
firewall/NAT rules were removed. The owner separately authorized US x-ui removal;
its service, binaries and database were included. SSH remained reachable; no VPN
listeners remained (only SSH and loopback host services). Base OS packages and the
US swap file were retained; they do not start a tunnel.

Private archives remain only on their respective hosts, under root mode 0700
folders, with archive/files mode 0600; never publish them because they contain
old keys and credentials:

- DE: `/root/prettylisavpn-retired-20261026T120110Z`, 78,041,162-byte archive,
  SHA-256 `cc445b2de9991c6dac101f0c6214e9e4f3324f457b945ff487060ac407119091`.
- US: `/root/prettylisavpn-retired-20261026T120152Z`, 176,911,733-byte archive,
  SHA-256 `31bb6e5d69339bfab2b7247ac086e70b06a888dd2f066dfb61f32e7539cd2cd2`.

Each archive has its exact path manifest, original unit enablement and pre-cleanup
firewall snapshot. An operator rollback must restore the matching node archive,
owned rules, services, backend release and client together; do not restore all
firewall rules blindly over later host changes. The reset PR remains separate
from the already merged PR #29.

Old diagnostic containers `pl-fleet-cross-netcup` (US), `pl-fleet-nyc` and
`pl-fleet-netcup` (backend) were removed. Unused backend node-agent mTLS files were
removed from the active secrets directory after a private archive was retained at
`/root/prettylisavpn-retired-20261026T120457Z` on the backend host. Its archive
SHA-256 is `b922efb459ca966dc050c14573a07e10deb3c8370588841b22ae5122a736107e`.
