# ishost-uk-001 — PREMIUM enrollment, 2026-11-19

The owner explicitly selected **Продакшен** and confirmed the SSH ED25519
fingerprint through the provider console before password authentication.
Installation followed [server enrollment](server-enrollment.md).
The operational production control plane is `95.140.152.42` /
`api.prettylisavpn.com`; its existing Compose project and `/version.environment`
still say `development`. This task preserves those runtime settings and does not
enroll the node into the separate test control plane.

## Identity and access

| Setting | Verified value |
| --- | --- |
| Name / credential alias | `ishost-uk-001` |
| Node UUID | `afbbf7be-16d4-48be-adc3-4aa400aa49db` |
| Country | United Kingdom, `GB` |
| Host / expected exit IPv4 | `38.180.140.18` |
| Group | `PREMIUM`, `is_available_for_free=false` |
| Capacity | 10 concurrent leases; conservative admission limit, not a load-test guarantee |
| OS / architecture | Ubuntu 24.04.4 LTS, x86_64 |
| Resources observed | 1 vCPU, 961 MiB visible RAM, 20 GiB root filesystem, no swap |
| WireGuard | `pl-wg0`, `10.88.8.1/24`, UDP 51820, MTU 1380 |
| Managed identity | `server_name=api.prettylisavpn.com`, `reality_target=95.140.152.42` |
| Browser proxy | `proxy_host=38.180.140.18`, trusted exact IP SAN |
| Confirmed SSH fingerprint | `SHA256:rmtXKY0RwcarrGJHUnrerfcLpiyGDGWdwOnGTuwCRUU` |

The existing worker public key was appended to root authorized_keys, restricted
to source `95.140.152.42`. Worker inventory and pinned known_hosts were updated
under the enrollment lock with private backups. A graceful worker-only restart
loaded the alias after confirming no running fleet operation and three fresh,
ready customer leases. The backend, reverse proxy, existing SSH entries,
provider services, default route and other nodes' admission settings were
preserved. Credentials and private keys remain outside git and this handoff.

## Versions and deployed artifacts

**Version unchanged** for every component. The documentation base is develop
`6dba22f987475fbc7d14ff1ea3372d13143c4d1c` (backend source 0.54.2 → 0.54.2).
The existing deployed backend/helper source used for enrollment is
`afcf94dd20f22a6027da55a89b491a56acd09620`,
[Backend run 44513423200](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44513423200),
attempt 1. Live `/version` reported
`0.54.1-dev.44513423200+gafcf94dd20f22a6027da55a89b491a56acd09620`.
The source manifest and deployed version are separate facts; this task does not
deploy the newer application source.

This enrollment reuses the installed worker engine and backend helpers. It
creates no application image or client build, changes no API contract or database
schema, and requires no client download publication. Final documentation HEAD
and its complete Actions/Checks audit belong in the task PR.

| Installed artifact | SHA-256 |
| --- | --- |
| `node.py` | `2945d0c3e632881d0b12ed3d4dfdf378efc46303b7779737256dfe2ba7ea113c` |
| `managed.py` | `e22d506b1bc1fda2bebee4c9c032555b0a8914b3eeae01098b8782f65e4c4a85` |
| `browser_proxy.py` | `e224547860fd2cad5414acce3e2b18b97f42c8ceafd9c709752531a117bea865` |
| Reused `pl-node-engine` | `1a418b17d0e9ac4dc1fa695ad1becc10d2b32706ffe7845d3db05e8fb9092434` |

Helper hashes match the running backend; the engine hash matches the existing
worker-mounted artifact. This does not attribute that reused engine to a new build.

## Configuration and health checks in UTC

| Operation | Result |
| --- | --- |
| WireGuard configure `96f98142-c483-4ccd-a2c3-369bb65a0a91` | SUCCEEDED, 12:38:02 |
| WireGuard check `b016e4df-b71c-49a3-9293-bd029816ff4b` | SUCCEEDED / HEALTHY, 12:38:47, DigitalOcean DE → UK |
| Managed configure `43121104-c5ff-4873-9790-c030ee29d174` | SUCCEEDED, 12:41:55 |
| Scheduled managed check `752aa22a-b1b5-4730-bec1-8e900b1bc7d4` | SUCCEEDED / HEALTHY, 12:44:01, AT → UK |

Checks confirmed handshake, DNS, HTTPS, expected exit IP and cleanup. The manual
managed check request was rate-limited by the existing per-node five-minute
window; the scheduled check then succeeded without bypassing that limit.
Missing throughput samples are not reported as measured speeds.

Fourteen additional synthetic checks passed between 12:46 and 12:51 UTC:
UK as a WireGuard origin toward Netcup DE; Netcup DE → RU → UK WireGuard;
Netcup DE → UK AmneziaWG, SSTP, SoftEther, VLESS Reality, VLESS TLS, VMess TLS,
Shadowsocks 2022, Hysteria 1, Hysteria 2, Hysteria 2 Salamander and HTTPS proxy;
Netcup DE → RU → UK VLESS Reality. Every check confirmed handshake, DNS, HTTPS,
expected egress and temporary-grant cleanup. These are bounded path checks,
not a ten-user load test or customer throughput guarantee.

## Public API and direct browser-proxy acceptance

A disposable Chrome device/account was tested in FREE, PREMIUM and PLATINUM
states through the public HTTPS API. FREE could not select GB in native or proxy
country lists; explicit GB allocation returned `VPN_NO_AVAILABLE_NODE`.
Premium and Platinum both saw GB available and obtained READY HTTPS-proxy leases.
For both paid plans, direct proxy traffic from the Windows workstation with
normal TLS verification reached the authenticated session probe and returned
`{"verified":true,"ip":"38.180.140.18"}`. No SSH tunnel or system VPN switch was
used for that traffic. Both leases were closed with confirmed removal; the
disposable account was blocked and its authentication sessions revoked.

This is real transport/API acceptance using a server-issued disposable session,
not a fresh email OTP flow or a full Chrome/native UI regression.

## Certificate and renewal

The existing IP-certificate playbook completed all ten tasks without failures.
Let's Encrypt YE2 issued the exact `38.180.140.18` IP SAN certificate, valid from
2026-11-19 11:41:42 through 2026-11-26 03:41:41 UTC. System trust-chain verification
and renewal dry-run passed. The first dry-run was stopped during its random
delay and repeated with `--no-random-sleep-on-renew`; normal renewal settings
were preserved. The four-hour renewal timer is enabled/active, and TCP/80 remains
available for HTTP-01.

## Final state and follow-up

WireGuard and managed methods are both `READY` with future recurring checks
scheduled by the existing fleet worker. Final inspection found zero unremoved
client leases and zero authorized/active WireGuard or managed grants on this
node. WireGuard, the independent cleanup timer, the measurement service and the
certificate renewal timer are enabled/active. During acceptance approximately
547 MiB RAM remained available and the checked kernel journal had no OOM entries.

No additional backend implementation or application deployment is needed.
Long-term health history must accumulate naturally; this is not a completed
24-hour availability assessment. Any capacity increase should use separate
concurrent-load evidence. Retirement or reinstallation remains a separate action.
