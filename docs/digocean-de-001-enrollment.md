# digocean-de-001 — PREMIUM enrollment, 2026-11-18

The owner requested adding this existing DigitalOcean Frankfurt VPS to
PrettyLisaVPN. Installation followed [server enrollment](server-enrollment.md),
using the host fingerprint confirmed through the provider console. Initial SSH
allowed public-key authentication only; the owner installed the existing fleet
worker public key, restricted to source `95.140.152.42`. Password authentication
was not enabled. The bootstrap credential stays in the ignored local file.

## Identity and access

| Setting | Verified value |
| --- | --- |
| Name / credential alias | `digocean-de-001` |
| Node UUID | `ac1beee6-9c71-4e9c-af41-15dff405b911` |
| Country | Germany, `DE` |
| Host / expected exit IPv4 | `201.79.12.109` |
| Group | `PREMIUM`, `is_available_for_free=false` |
| Capacity | 5 concurrent leases; conservative admission limit, not a load-test guarantee |
| OS / architecture | Ubuntu 24.04.5 LTS, x86_64 |
| Resources | 1 vCPU, 512 MiB class (458 MiB visible), 8.7 GiB root filesystem, no swap |
| WireGuard | `pl-wg0`, `10.88.6.1/24`, UDP 51820, MTU 1380 |
| Managed identity | `server_name=api.prettylisavpn.com`, `reality_target=95.140.152.42` |
| Browser proxy | `proxy_host=201.79.12.109`, trusted exact IP SAN |
| SSH ED25519 fingerprint | `SHA256:qcI8BpGesu1fOisKMaAnDoQgYGc6eNy7I6bz9ny/Jss` |

Premium and Platinum may use this exit. FREE/DEMO remain excluded from this
node; Germany remains available to Free through the existing `netcup-de-001`.
No other node's group, capacity or enabled state was changed.

Worker inventory and pinned known_hosts were updated under the enrollment lock,
with private backups beside the existing files. A graceful worker-only restart
loaded the new alias before configuration. Provider agents, existing SSH entries,
host default route and other services were preserved. Secrets and private keys
are absent from this handoff and git.

## Versions and deployed artifacts

**Version unchanged**: backend 0.53.0 → 0.53.0; all clients, dashboard, website,
API contracts and database schema are unchanged. This task changes runtime
fleet configuration and documentation. No client rebuild or download publication
is needed.

The existing backend/helper source is
`8f74a39f61a2907f01698bc7bef946eba96d79ae`,
[Backend run 44092961442](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44092961442),
attempt 1. Live `/version` reported
`0.53.0-dev.44092961442+g8f74a39f61a2907f01698bc7bef946eba96d79ae`, environment
`development`. No new application image or engine build was created.

| Installed artifact | SHA-256 |
| --- | --- |
| `node.py` | `2945d0c3e632881d0b12ed3d4dfdf378efc46303b7779737256dfe2ba7ea113c` |
| `managed.py` | `e22d506b1bc1fda2bebee4c9c032555b0a8914b3eeae01098b8782f65e4c4a85` |
| `browser_proxy.py` | `e224547860fd2cad5414acce3e2b18b97f42c8ceafd9c709752531a117bea865` |
| Reused fleet `pl-node-engine` | `1a418b17d0e9ac4dc1fa695ad1becc10d2b32706ffe7845d3db05e8fb9092434` |

Helpers match the running backend. The engine matches the existing worker-mounted
artifact; it is not attributed to a new source/build run. The certificate playbook
and documentation base are `84466c97c6938fcf09fcef296da38dc18d27f479`.
Final documentation HEAD and its complete Actions/Checks audit are recorded in
the task PR separately from runtime build identity.

## Verification in UTC

| Operation | Result |
| --- | --- |
| WireGuard configure `9492d8c4-5064-4252-8cdd-0fd15c2526e3` | SUCCEEDED, 10:43:36 |
| WireGuard check `3549d17a-c7f6-4669-90f3-6ce83d07f6eb` | SUCCEEDED / HEALTHY, 10:44:13, RU → new DE |
| Managed configure `73220111-8802-42ae-ba51-cb4489e866cb` | SUCCEEDED, 10:46:22 |
| Scheduled managed check `ee07ff69-e814-4c15-9e7f-25ff67eab050` | SUCCEEDED / HEALTHY, 10:48:31, NL → new DE |

Both methods reached `READY`. The scheduled managed check confirmed connectivity
and cleanup but returned no download/upload speed samples; those missing samples
are not reported as measured throughput.

Fourteen additional synthetic checks passed between 10:47 and 10:49: new DE as
a WireGuard origin toward Netcup DE; Netcup DE → RU → new DE WireGuard;
Netcup DE → new DE AmneziaWG, SSTP, SoftEther, VLESS Reality, VLESS TLS,
VMess TLS, Shadowsocks 2022, Hysteria 1, Hysteria 2, Hysteria 2 Salamander and
HTTPS proxy; Netcup DE → RU → new DE VLESS Reality. Each confirmed handshake,
DNS, HTTPS, expected egress and cleanup. These are bounded path samples, not
guaranteed customer speeds or a five-user throughput test.

During these checks the node had approximately 232 MiB available memory and no
kernel OOM entries. The small RAM allocation warrants the conservative capacity;
increasing it requires separate concurrent-load evidence or a VPS upgrade.

Public HTTPS country queries for a disposable Chrome account returned Germany
available for FREE, PREMIUM and PLATINUM, preserving the existing FREE exit.
To test this particular node without changing other servers or customer routing,
a separate acceptance process used the deployed `ClientVpnService` with real
token authentication and database records, restricting only its own fleet
snapshot to the new node. FREE allocation was denied with
`VPN_NO_AVAILABLE_NODE`; Premium and Platinum allocations reached READY through
the normal fleet worker. This is a targeted application-service acceptance test,
not a new public API capability to select individual nodes.

Lease polling, revocation and exit verification used the normal public API.
From the Windows workstation, direct HTTPS-proxy traffic with normal TLS
verification returned `{"verified":true,"ip":"201.79.12.109"}`. No SSH tunnel or
system VPN switch was used for that traffic. Both temporary client leases were
CLOSED with confirmed removal; the disposable account was blocked and its auth
session revoked. Final inspection found zero authorized/active WireGuard or
managed grants.

## Certificate and ongoing operation

The existing IP-certificate playbook completed with ten successful tasks and no
failures. Let's Encrypt YE1 issued the exact `201.79.12.109` IP SAN certificate,
valid from 2026-11-18 09:46:05 through 2026-11-25 01:46:04 UTC. System trust-chain
verification and Certbot renewal dry-run passed. The four-hour renewal timer is
enabled/active; TCP/80 remains available for HTTP-01.

WireGuard, the independent cleanup timer, the measurement service and the
certificate renewal timer are enabled/active. The main-server worker owns the
recurring health schedule. No further backend implementation or application
deployment is required for this enrollment.

Enrollment verification does not represent a fresh OTP flow, a full native or
Chrome UI regression, or a completed 24-hour availability assessment. Ongoing
health history must accumulate naturally. Retirement or reinstallation remains
a separate action.
