# netcup-aut-001 — PREMIUM enrollment, 2026-11-18

The owner requested adding this existing Netcup VPS to PrettyLisaVPN. The owner
reinstalled Debian 13 as Ubuntu 24.04 and confirmed the replacement SSH host
fingerprint through the Netcup console before password authentication.
Installation followed [server enrollment](server-enrollment.md).

## Identity and access

| Setting | Verified value |
| --- | --- |
| Name / credential alias | `netcup-aut-001` |
| Node UUID | `2fdfd817-8099-4ee8-b954-0ba907cfbdbb` |
| Country | Austria, `AT` |
| Host / expected exit IPv4 | `89.58.16.22` |
| Group | `PREMIUM`, `is_available_for_free=false` |
| Capacity | 20 concurrent leases; admission limit, not a load-test result |
| OS / architecture | Ubuntu 24.04.5 LTS, x86_64 |
| Resources observed | 2 vCPU, approximately 4 GiB RAM, 62 GiB root filesystem |
| WireGuard | `pl-wg0`, `10.88.5.1/24`, UDP 51820, MTU 1380 |
| Managed identity | `server_name=api.prettylisavpn.com`, `reality_target=95.140.152.42` |
| Browser proxy | `proxy_host=89.58.16.22`, trusted exact IP SAN |
| Confirmed SSH ED25519 fingerprint | `SHA256:oy1GeD5kJlboM+q/Gi+8quyVNFADNxaJQ3ff7Z5H+ak` |

The worker inventory and pinned known_hosts were updated under the enrollment
lock, with private backups beside the existing inventory. The existing worker
public key was appended to root authorized_keys, restricted to source
`95.140.152.42`; existing SSH entries and the host default route were preserved.
The bootstrap password stays in the ignored local credential file. No password,
private key, account token or proxy password is included in this handoff or git.

The worker loads inventory at startup. Initial operation
`1b063366-c1ef-4ecb-a112-73145594004b` failed with
`NODE_CREDENTIAL_NOT_ENROLLED` before installation. After a graceful worker-only
restart, a new operation succeeded; the original failure remains in history.
No backend image or application configuration was replaced.

## Deployed sources and compatibility

**Version unchanged**: backend 0.53.0 → 0.53.0; all clients, dashboard, website,
API contracts and database schema are unchanged. This task adds runtime fleet
configuration and documentation only. No client rebuild or download publication
is needed.

Backend/helper source is the existing deployed commit
`8f74a39f61a2907f01698bc7bef946eba96d79ae`,
[Backend run 44092961442](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44092961442),
attempt 1. Live `/version` reported
`0.53.0-dev.44092961442+g8f74a39f61a2907f01698bc7bef946eba96d79ae`, environment
`development`. Node helper hashes match that running backend exactly:

| Artifact | SHA-256 |
| --- | --- |
| `node.py` | `2945d0c3e632881d0b12ed3d4dfdf378efc46303b7779737256dfe2ba7ea113c` |
| `managed.py` | `e22d506b1bc1fda2bebee4c9c032555b0a8914b3eeae01098b8782f65e4c4a85` |
| `browser_proxy.py` | `e224547860fd2cad5414acce3e2b18b97f42c8ceafd9c709752531a117bea865` |
| Reused fleet `pl-node-engine` | `1a418b17d0e9ac4dc1fa695ad1becc10d2b32706ffe7845d3db05e8fb9092434` |

The engine was copied from the existing worker-mounted artifact; its installed
hash matches that artifact. This task did not create an engine build or attribute
it to a new source/build run. Certificate playbook and documentation base:
`84466c9` (the playbook is unchanged from `2ac1e72`). Final documentation HEAD and
its complete Actions/Checks audit belong in the task PR, separate from runtime
build identity.

## Verification in UTC

| Operation | Result |
| --- | --- |
| WireGuard configure `4b0e8ddb-b08b-48f7-a2f3-0ad1e087b240` | SUCCEEDED, 10:08:32 |
| WireGuard check `f0a97d72-d468-44ec-97c0-930152237033` | SUCCEEDED / HEALTHY, 10:09:27, RU → AT |
| Managed configure `718a82d2-d4aa-420b-85ed-aa0420748df7` | SUCCEEDED, 10:10:46 |
| Scheduled managed check `82c65c29-0d47-40b3-8c38-185ed551acf8` | SUCCEEDED / HEALTHY, 10:13:34, RU → AT |

Both methods reached `READY`. Full checks confirmed handshake, DNS, HTTPS,
expected egress and cleanup. Fourteen additional synthetic checks passed between
10:13 and 10:15: AT as a WireGuard origin toward DE; DE → RU → AT WireGuard;
DE → AT AmneziaWG, SSTP, SoftEther, VLESS Reality, VLESS TLS, VMess TLS,
Shadowsocks 2022, Hysteria 1, Hysteria 2, Hysteria 2 Salamander and HTTPS proxy;
DE → RU → AT VLESS Reality. Every temporary grant was confirmed removed.
These are bounded path samples, not a throughput guarantee; the VLESS Reality
relay upload sample was absent and is not reported as a measured speed.

The public API was tested with a disposable Chrome device and temporary
FREE/PREMIUM/PLATINUM account states. FREE could not select AT in native or proxy
country lists; its explicit AT allocation returned `VPN_NO_AVAILABLE_NODE`.
Premium and Platinum both saw AT available and obtained READY proxy leases.
From the Windows workstation, a direct HTTPS-proxy connection with normal TLS
verification reached the authenticated probe and returned
`{"verified":true,"ip":"89.58.16.22"}`. No SSH tunnel or system VPN switch was used.
Test sessions were closed, all three allocated client leases had confirmed
removal, disposable accounts were blocked and their auth sessions revoked.
Final node inspection found zero authorized/active WireGuard or managed grants.

This verifies transport and API access, not a fresh OTP flow or a full Chrome
extension UI regression. Early acceptance attempts before managed verification
were retried after the node reached READY; they are not treated as successful
readiness evidence.

## Certificate and ongoing operation

The existing IP-certificate playbook completed with 10 successful tasks and no
failures. Let's Encrypt YE2 issued the exact `89.58.16.22` IP SAN certificate,
valid from 2026-11-18 09:11:05 through 2026-11-25 01:11:04 UTC. System trust-chain
verification and Certbot renewal dry-run both passed. The four-hour renewal
timer is enabled/active; TCP/80 remains available for HTTP-01.

WireGuard, the independent fleet cleanup timer, the measurement service and
the certificate timer are all enabled/active. The main-server worker continues
scheduled health checks with the new node in its roster. No additional backend
implementation or deployment is needed. The ongoing hourly/long-term history
must accumulate naturally; these enrollment checks are not a completed 24-hour
availability assessment. Retirement or reinstallation remains a separate action.
