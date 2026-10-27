# Server lifecycle and monitoring — backend 0.17.0

Base: develop `227704b044f0b5a6ea67b4f64d6142a813eddec0`. Backend 0.16.0 → 0.17.0,
migration 0029; Ubuntu helper starts at 0.1.0. Windows remains 0.14.1 and Android
0.11.1; their VPN adapters remain placeholders. Legacy credential endpoints stay removed.

## API and explicit setup

`fleet.domain.VpnMethod` defines inspect, plan, configure, grant/revoke, observe,
probe and rollback. `WireGuardMethod` is the first implementation. The separate
worker belongs to the same modular backend and uses PostgreSQL operations.
The web container has no SSH key mount. VPN traffic never traverses the API.

Enable `FLEET_ENABLED=true` with distinct random 32+ character secrets:
`FLEET_ADMIN_TOKEN` and `FLEET_MONITOR_TOKEN`. The latter can only read availability.
Ordinary OTP sessions do not grant administrative access.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/admin/nodes` | Register metadata; does not install |
| GET | `/admin/nodes` | Administrator inventory |
| POST | `/admin/nodes/{id}/methods/wireguard/configuration` | Explicit configuration |
| POST | `/admin/nodes/{id}/methods/wireguard/checks` | Manual check |
| GET | `/admin/operations/{id}` | Redacted operation result |
| GET | `/admin/monitoring/availability?days=7&node_id={id}` | Overall/per-node history |

Configuration/check calls require UUID `Idempotency-Key`; changed parameters with
the same key conflict. Manual checks are limited to one per target per five minutes.
Only implemented methods are accepted. Registration takes name, country_code, public
host, credential_ref, expected_egress_ips, capacity and is_available_for_free.
Configuration example: `{"address":"10.88.1.1/24","listen_port":51820,"mtu":1380}`.

Use distinct RFC1918 /24…/28 subnets and the first usable address for the server.
The last usable address is reserved for the monitoring peer. Configuration is
immutable after successful setup; a subnet/port migration is a separate future task.
Repeating the same request preserves keys and user peers. Registration alone never
installs software. A lone configured node awaits verification from another origin.

The worker inventory binds each credential alias to exact host, user, port, absolute
key_file and pinned known_hosts paths. API input cannot redirect keys elsewhere.
For example, `de1` maps to host `5.181.49.183`, user `root`, port 22,
key_file `/run/fleet/de1.key`, known_hosts `/run/fleet/known_hosts`.

Ansible installs Ubuntu 24.04+ distro packages and the helper, then configures
`pl-wg0`, forwarding and owned `PLF_*` iptables chains. Unowned interface/chain and
route conflicts are rejected. Host default routes and SSH are preserved. Private
keys stay on nodes. Rollback removes only incomplete configuration owned by its
operation, preserving shared OS packages and previously committed configuration.

## Checks, scheduling and truthful evidence

Every configured target gets one hourly slot, evenly spread with bounded stable
jitter. Origins rotate over the other configured nodes, covering all origins in
N−1 hours for a stable roster: O(N) tests/hour. New configured nodes join both roles.
Database tokens fence results and node leases prevent overlapping source/target
checks. Retries keep the operation UUID and are bounded. Missed hours are not replayed
as a burst. Local timers independently expire monitoring peers and namespaces.

If non-monitoring peers exist on the target, observe them without adding a test peer.
Passive success needs fresh handshakes and growth in both aggregate byte counters.
The first sample or idle traffic is UNKNOWN. No destinations, DNS queries, packet
contents or browsing history are collected. Passive mode cannot prove DNS/HTTPS/IP.

Full synthetic check:

1. Verify the source's direct Internet path and its owned HTTPS measurement service.
2. Generate a temporary key on the source; authorize a four-minute target peer.
3. Create WireGuard on the host then move it into an isolated network namespace.
   The namespace has only loopback and WireGuard, with no direct fallback; IPv6 is
   disabled only there. Host routes and running sessions are preserved.
4. Verify handshake, DNS and HTTPS to the fixed API health endpoint. Call the
   source's pinned HTTPS endpoint through the target and match the observed exit IP
   against the target's enrolled expected_egress_ips.
5. Measure bounded 8 MiB upload/download samples. This is observed inter-server path
   throughput, not guaranteed ISP capacity. Missing samples earn no speed credit.
6. Delete the namespace/key and revoke access with confirmation. Unknown cleanup
   cannot report success; the local timer remains the independent fallback.

The unprivileged HTTPS/8443 measurement service uses a node-local random token and
pinned certificate, fixed bounded paths, timeouts and no access logs. It is separate
from the API. Foreign VPS success does not prove reachability from Russian clients.

## History, rating and dashboard

Eight days of raw observations serve 168 hourly buckets. FAILED takes precedence
within an hour; absent samples are UNKNOWN, ongoing empty hours PENDING, and time
before enrollment NOT_REGISTERED. Availability is successful / known hours; coverage
is known / expected completed hours. Show both to expose monitoring gaps.

Score defaults: availability 50%, spare active capacity 20%, connection speed 15%,
throughput 15%. Settings expose weights and speed/time targets. Availability uses
a six-hour half-life over the last day. Latest failed/unknown or >75-minute-old
evidence, unverified setup or unconfirmed cleanup makes the node unavailable.
Full capacity also prevents availability. Country scores are capacity-weighted over
eligible nodes; Free sees only free nodes. Premium and Platinum use the full fleet.

The owner-approved standalone dashboard is in `sites/fleet-dashboard/` and served
at `https://api.prettylisavpn.com/dashboard/` on the main server. HTTPS Basic Auth
protects assets and metrics; only Caddy holds the read-only monitoring token.
Credentials and the built site live in the operator-managed `secrets/dashboard/`
directory and survive backend deployments. The browser receives aggregate data,
never tokens or SSH keys. It provides overall/per-node views, hourly history and
stage evidence. The earlier Sites-hosted prototype is unpublished and unused.
See the [dashboard deployment instructions](../sites/fleet-dashboard/README.md).

## Deployment and acceptance

Owner-managed `fleet.env` and `fleet/` live beside the deployment env and survive
CI-generated env replacement. `deploy.sh` enables the optional `fleet` Compose profile
when fleet.env exists. File mode must be 0600; mounted keys are restricted to worker
UID 10001. Do not commit these files. Backend and worker use the same image.

Rollback preserves migration 0029 and historical data. Stop the worker before
reverting to an image without this module. Node expiry continues independently;
removing configured gateways is a separate explicit operation.

The worker runs on the main development server, `95.140.152.42`, with Docker
`restart: unless-stopped`; Docker starts with the host. PostgreSQL owns scheduling,
leases and observations. Nodes run independent systemd cleanup timers. Sites is
only a read-only view. Closing Codex/ChatGPT does not stop any recurring process.
SSH control sessions are reused within each operation so the existing node SSH
rate limit remains intact.

`python -m prettylisavpn.fleet.acceptance --since <UTC ISO> --until <UTC ISO>`
produces a read-only JSON report for a completed observation interval. It checks
hourly scheduled jobs (manual tests do not fill missing hourly coverage), requires
all expected samples, successful observations and confirmed cleanup. A host
systemd timer runs this command for the 24-hour acceptance window and saves its
result under `/opt/prettylisavpn/fleet-acceptance/`; no assistant callback is used.

Validation: latest isolated Linux run: 508 passed, 1 skipped, 9 Docker tests
excluded; Ruff, strict mypy and Alembic upgrade/check passed. The separate Docker
suite passed 9 tests before the SSH reuse/report follow-up. Real explicit API setup
completed on Ubuntu 24.04 DE and US. DE→US and US→DE both passed handshake,
DNS, HTTPS, expected exit IP and cleanup on 2026-10-27 at 09:10 and 09:11 UTC.
Observed handshake times were about 113 ms; bounded down/up samples were
19.4/29.2 and 23.6/22.9 Mbps respectively.

An independent expiry test stopped the worker: the node timer removed the test
peer before the worker restarted. An initial controlled UDP fault also hit the
existing US SSH rate limit; it truthfully recorded UNKNOWN/CLEANUP_UNCONFIRMED.
The independent rollback timer removed the fault and no peer remained. This
motivated SSH reuse; repeat fault/recovery and 24-hour acceptance are tracked in
PR #31. Source, deployment and acceptance are separate claims. Exact final product
SHA, manual build identity, Sites deployment and CI evidence belong in the PR.
