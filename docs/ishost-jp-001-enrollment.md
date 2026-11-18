# ishost-jp-001 — PREMIUM enrollment, 2026-11-18

The owner requested adding this existing is*hosting VPS to PrettyLisaVPN and
confirmed its SSH host fingerprint through the provider console before password
authentication. Installation follows [server enrollment](server-enrollment.md).

## Identity and access

| Setting | Value |
| --- | --- |
| Name / credential alias | `ishost-jp-001` |
| Node UUID | `9111e3ad-466e-48bd-829c-5dda3f70d7f1` |
| Provider server / location | is*hosting #487007, Japan (`JP`) |
| Host / expected exit IPv4 | `38.180.7.144` |
| Group | `PREMIUM`, `is_available_for_free=false` |
| Capacity | 20 concurrent leases, as requested by the owner; admission limit, not a load-test result |
| OS / architecture | Ubuntu 24.04.5 LTS, x86_64; kernel `6.8.0-149-generic` |
| Observed resources | 1 vCPU, approximately 1 GiB RAM, 20 GiB root disk |
| WireGuard configuration | `pl-wg0`, `10.88.7.1/24`, UDP 51820, MTU 1380 |
| Managed identity | `server_name=api.prettylisavpn.com`, `reality_target=95.140.152.42` |
| Browser proxy address | `38.180.7.144` |
| Confirmed SSH ED25519 fingerprint | `SHA256:3lUwWSYyXXfvqL05RR8MNhR69UR5+TUIO1e9Vqke+o8` |

The existing worker public key was appended to root authorized_keys, restricted
to source `95.140.152.42`. Existing entries were preserved. The pinned host key
and credential alias were added under the enrollment lock, with private backups
beside the existing inventory. Worker key authentication was verified. A graceful
worker-only restart loaded the inventory before the first configure operation.
No API image, application setting or existing VPN endpoint was replaced.

The bootstrap password remains in the ignored local credential file. No password,
private key, authentication token or proxy password belongs in this handoff or git.

## Authorized operating-system upgrade

The VPS initially ran Ubuntu 22.04.5, below the existing bootstrap requirement.
The owner explicitly authorized an in-place upgrade to Ubuntu 24.04 with reboot.
The system was fully updated and rebooted before running the official
[`do-release-upgrade` procedure](https://documentation.ubuntu.com/server/how-to/software/upgrade-your-release/).
An `/etc` backup and private upgrade logs remain under
`/root/prettylisavpn-enrollment` on this VPS. A temporary 2 GiB swap file was used
only during the upgrade and removed after reboot; no persistent swap entry was added.

The provider image had a stale GRUB install-device reference to an absent
`/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive0`. After the upgrader stopped with
that error, the actual BIOS boot disk was verified as `/dev/sda` (DOS partition
table, `/dev/sda1` mounted at `/`). Its boot prefix was privately backed up, the
GRUB device setting corrected, and package configuration completed. GRUB install
to `/dev/sda`, `grub-script-check`, and `dpkg --audit` passed before reboot.

SSH was temporarily unavailable during package replacement and recovered without
a forced reboot. The final boot verified Ubuntu 24.04.5, the new 6.8 kernel,
unchanged SSH host identity, preserved default route and zero failed system units.
The original upgrade failure is retained in its log; it is not reported as a
successful initial attempt.

## Versions and source identity

**Version unchanged**: backend 0.53.0 → 0.53.0; all client versions, API contracts
and database schema are unchanged. This task adds runtime fleet configuration
and documentation; no client rebuild or download publication is required.

The existing runtime reports
`0.53.0-dev.44092961442+g8f74a39f61a2907f01698bc7bef946eba96d79ae`,
environment `development`. Backend/helper source is
`8f74a39f61a2907f01698bc7bef946eba96d79ae`,
[Backend run 44092961442](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44092961442),
attempt 1. Certificate playbook/documentation base is
`b90d9685e4469c08b7a525639bee9da4f5b65134`.
Final documentation HEAD and its complete Actions/Checks audit are recorded in
the task PR separately from the running product build.

Installed helpers were compared with the running backend; the engine was compared
with the existing worker-mounted artifact. All SHA-256 hashes match:

| Artifact | SHA-256 |
| --- | --- |
| `node.py` | `2945d0c3e632881d0b12ed3d4dfdf378efc46303b7779737256dfe2ba7ea113c` |
| `managed.py` | `e22d506b1bc1fda2bebee4c9c032555b0a8914b3eeae01098b8782f65e4c4a85` |
| `browser_proxy.py` | `e224547860fd2cad5414acce3e2b18b97f42c8ceafd9c709752531a117bea865` |
| Reused `pl-node-engine` | `1a418b17d0e9ac4dc1fa695ad1becc10d2b32706ffe7845d3db05e8fb9092434` |

This task did not create or publish a new engine build.

## Certificate

The existing IP-certificate playbook completed with 10 successful tasks,
7 changed tasks and zero failures. Let's Encrypt YE1 issued the exact
`38.180.7.144` IP SAN certificate, valid from 2026-11-18 15:09:26 through
2026-11-25 07:09:25 UTC. System trust-chain validation and Certbot renewal
dry-run both passed. The four-hour renewal timer is enabled and active;
TCP/80 remains available for HTTP-01. No DNS record was required.

## Fleet operations

| Operation | Result | Finished (UTC) |
| --- | --- | --- |
| configure-wireguard `bcaeb0bc-1d13-4efd-8230-7f752a5d38d7` | SUCCEEDED | 2026-11-18T16:05:52.408907Z |
| check-wireguard `1822e84e-af0f-4490-a195-b8a97a06fe56` | SUCCEEDED | 2026-11-18T16:06:41.563132Z |
| configure-managed `d9eb2260-7ca1-430b-8535-54cfe7007118` | SUCCEEDED | 2026-11-18T16:11:24.535591Z |
| check-managed `b5f75860-b407-4c80-8d49-78d1b90cba44` | SUCCEEDED | 2026-11-18T16:12:16.163850Z |

WireGuard and managed full checks from `netcup-aut-001` confirmed handshake,
DNS, HTTPS, expected egress and cleanup. The operations above are real fleet
worker operations, separate from the additional protocol and client acceptance.

## Client and entitlement acceptance

A disposable Chrome device/account exercised the public HTTPS API with temporary
FREE, PREMIUM and PLATINUM subscription states. No payment was made. FREE did not
receive JP as an available native or proxy country; explicit JP allocation returned
`VPN_NO_AVAILABLE_NODE`. Premium and Platinum both received READY proxy leases.

From the Windows workstation, the Premium lease was used as a direct HTTPS proxy
with normal certificate validation, without an SSH tunnel or changing the user's
system VPN. The authenticated egress probe returned
`{"verified":true,"ip":"38.180.7.144"}`. Both allocated leases reached CLOSED with
confirmed removal. The disposable account was blocked and auth sessions revoked.

This exercises real application services, sessions, transport and egress; it is
not a fresh email-OTP acceptance or a full client UI regression. No UI or rating
aggregation behavior was changed by this enrollment task.

Both fleet methods reached READY and have future scheduled checks. Initial
observations do not establish a complete 24-hour availability history or a
concurrent-load/throughput guarantee. Initial acceptance used a capacity of ten.
The owner subsequently requested twenty sessions; the existing admin update API
applied `capacity=20`, and both the node inventory and monitoring readback confirmed
the value. Name, group and other node metadata were preserved. This configuration
change is not a twenty-session concurrent-load test.

## Additional protocol acceptance

Fourteen synthetic path checks passed between 16:12 and 16:17 UTC:
JP → DE WireGuard; DE → RU → JP WireGuard; DE → JP AmneziaWG, SSTP, SoftEther,
VLESS Reality, VLESS TLS, VMess TLS, Shadowsocks 2022, Hysteria 1, Hysteria 2,
Hysteria 2 Salamander and HTTPS proxy; DE → RU → JP VLESS Reality.
Every check confirmed handshake, DNS, HTTPS, expected exit and cleanup.

Some bounded speed samples were absent: download for WireGuard relay and VLESS
Reality relay; upload for AmneziaWG and SoftEther. These are not represented as
measured throughput, and no line-rate or concurrent-load guarantee is claimed.

Final inspection found zero authorized/active WireGuard and managed grants,
zero failed system units and no recent OOM-kill entries. WireGuard, independent
cleanup, measurement and certificate-renewal units are enabled and active.
API `/health` and `/ready` passed and `/version` remained the same deployed build.
No additional backend implementation or deploy is required to use this node.

Local repository verification covers the three documentation files only:
diff whitespace, new local links, evidence consistency and secret exclusion.
There is no shipped application change requiring a product-version bump or
client/native rebuild. Complete remote HEAD CI discovery belongs in the PR.
