# FREE node timeweb-nl-001 — 2026-11-04

Owner-requested operational enrollment. **Version unchanged**: no application,
API, database-schema or protocol changes. Backend remains 0.33.0; the existing
fleet API, Ansible bootstrap, SSH inventory and PostgreSQL scheduler are reused.

| Property | Value |
| --- | --- |
| Name / credential alias | `timeweb-nl-001` |
| Public host / expected egress | `81.31.245.143` |
| Country / group | NL / FREE |
| Node UUID | `2b1f6617-b3e6-4e0e-bf2e-634b6f35abb8` |
| Host | Ubuntu 26.04.1 LTS, x86_64, 1 vCPU, approximately 889 MiB RAM |
| Admission capacity | 20, matching existing FREE nodes; not a load-test result |
| WireGuard | `pl-wg0`, `10.88.4.1/24`, UDP 51820, MTU 1380 |
| Managed methods | Existing ten encrypted families and their relay variants |
| Managed server name / REALITY target | `api.prettylisavpn.com` / `95.140.152.42` |

FREE includes this exit in country selection and AUTO. Premium/Platinum retain
their existing access to FREE exits; the INTERMEDIATE node remains excluded
from direct country selection. No account quota or device limit was changed.

## Deployment identity and credentials

The running backend and worker use source
`05d945dbd5da35f1c85523d00b4ab57415882a3c`, Backend run `41822292784`, attempt 1,
runtime `0.33.0-dev.41822292784+g05d945dbd5da35f1c85523d00b4ab57415882a3c`.
Node helper hashes match those files in the running backend image:

- `node.py`: `7bf8b3671e94bcd802dec2b27d91d489cdbded116d51bbfd28fb7bab03bebb1d`
- `managed.py`: `03a148ea9d9c97e3d5c092177e8626b0255be114695e994206d4849e9b6b0adf`

Bootstrap reused the same operator-provisioned Linux engine as the existing
fleet, SHA-256 `895dfb8063bcc7b32af10c39a3639b5ca6c529f4b89a2f1c6748418cae58f1a4`.
Its source/build identity is recorded in [managed transport evidence](managed-transports.md):
product `277053a5484bf681bf4c3be7e45a0803e3a63d63`, build
`7a479dd2eb8319a88386eca0fd37f384ad8f2633`, run `40932133095`, attempt 1,
artifact `12923746083`. This enrollment does not claim a new Linux engine build.

The supplied ignored password file was read locally only for initial SSH setup.
Worker access uses the existing fleet public key, restricted on the new node to
source `95.140.152.42`, with the node's ED25519 host key pinned. The worker inventory
contains the exact host/user/port/key/known-hosts binding. Inventory and known-hosts
backups were retained before enrollment. A short graceful worker restart loaded
the new entry; API/Caddy and existing VPN-node services were not restarted.
Private keys, passwords, tokens and raw client profiles are absent from this record.

## Live verification

| Operation | UUID | Result / UTC |
| --- | --- | --- |
| Configure WireGuard | `4438e310-fc91-4ff3-bbba-b362a71d8366` | SUCCEEDED, 12:23:07 |
| Configure managed | `98f63039-c209-4b2a-b61c-7edb369cfff5` | SUCCEEDED, 12:23:59 |
| US → NL WireGuard | `9cea3cff-6a11-4720-90bf-ae1196b43b7a` | FULL_CHECK_PASSED, 12:24:13 |
| US → NL managed | `471defc8-cf0d-4d59-bdfe-bfdd78ea881e` | MANAGED_CHECK_PASSED, 12:24:56 |

Both real isolated probes confirmed handshake, DNS, HTTPS, expected exit IP and
cleanup. Sample download/upload: WireGuard 26.98/30.99 Mbps, managed 25.53/37.36
Mbps. These are bounded inter-server samples, not advertised bandwidth or a
complete per-client/per-protocol acceptance matrix.

A disposable FREE account used the public HTTPS API: refresh → `/vpn/countries`
returned NL available → a WireGuard lease became READY with endpoint
`81.31.245.143:51820` → DELETE reached CLOSED with confirmed removal. Lease UUID
`f9017cfb-9bdd-44f5-bba6-0258d9a60dad`. The disposable account was blocked and all
its sessions revoked; no test lease remained.

Both fleet methods are READY. WireGuard, measurement service and independent
cleanup timer are active and enabled. The host default route and provider Zabbix
service were preserved. The four-node scheduler includes NL as target and origin;
monitoring and dashboard discovery are automatic. Initial next target checks:
WireGuard 13:12:05 UTC, managed 13:17:13 UTC. Future observations are not claimed
as already successful. Final monitoring, any later origin/retry results, source
HEAD and CI audit are recorded in the task PR.

Early scheduled managed checks with NL as the origin and RU as the destination
reported `DNS_FAILED` at 12:28:16 and 12:28:41 UTC, with handshake/expected egress
and cleanup confirmed. These failed observations remain in history; the existing
scheduler retries them. The successful exit-node results above concern US → NL.

No full-day reliability, saturation test or physical iPhone/macOS tunnel acceptance
is inferred from node enrollment. Apple client acceptance remains a separate task.

## Recovery

Do not restore the pre-enrollment inventory while NL leases exist: cleanup still
needs its SSH entry and node identity. If withdrawal is needed, stop new allocation,
drain and confirm all access removal through the existing control plane first,
then remove only this node's enrollment. Preserve other inventory entries and
independent cleanup timers. No migration rollback or client upgrade is required.
