# Test clients on the existing real VPN fleet

Owner decision, 2026-11-19: test clients must connect to the real VPN servers,
not a separate test exit. This explicitly supersedes the original prohibition on
all test access to production nodes. Scope: **Тестовый контур**, plus restricted
access enrollment on **Продакшен** VPN nodes. Production application/database,
website and installers are not republished by this task.

The owner selected the latest backend as the repair baseline: test backend
0.53.0 → **0.54.4**, based on published 0.54.3 plus this fix. Its billing/provider
fixes and country metadata are restored with their tests. Test live billing remains
disabled. Android 0.30.2/code 61, Windows 0.31.2, Chrome 0.5.1, iOS 0.6.1,
macOS 0.5.1 and website 0.7.1 retain the selected rollback versions. Existing client
API contracts and schema `0053_analytics_plans` remain compatible and unchanged.

## One infrastructure owner, two isolated account databases

Production remains the only fleet configuration/monitoring owner. The test worker
uses `FLEET_SHARED_NODES=true`: it runs customer renewal/cleanup and a read-only
snapshot consumer, without configuration, monitoring, service/method probes or
traffic aggregation jobs. Its admin mutation methods reject requests. Production
monitoring naturally observes total node activity, including authorized test peers.

The forced-command [exporter](../infra/testing/export_shared_fleet.py) executes a
read-only database transaction inside the existing production backend. It exports
only public fleet metadata/configuration and the last 24 hours of real observations.
No account, authentication, payment, SSH or customer-lease data is exported. A separate
test key is restricted by source IP and fixed command; it cannot run a shell. The
consumer uses pinned SSH host keys. Imported observations retain original IDs and
times; new FK operation records are terminal `IMPORTED`, never runnable checks.

Snapshots refresh every 30 seconds. After 120 seconds without a valid snapshot,
new test connections become unavailable and existing test grants are revoked.
Unconfirmed removal remains outstanding until the existing node TTL/cleanup proves
removal. No stale timestamp is rewritten as a fresh measurement.

## Resource and ownership boundary

The enrolled owner fleet uses /24 WireGuard networks and capacity <=100 per node.
The owner's first-free customer allocators remain below the reserved test ranges:

| Resource | Test range | Existing owner behavior |
| --- | --- | --- |
| WireGuard addresses | subnet offsets 128–191 | offsets 2 upward, at most 100 leases |
| Managed TCP/UDP ports | 48000–48499 | from 40000; probes 49900–49999 |
| Intermediate forwarding | 28000–28499 | from 20000; bounded daily probes from 29999 |

The snapshot rejects owner capacity >100, non-/24 subnets, or conflicting outstanding
owner reservations. **Before changing these owner allocation bounds, stop test grants,
confirm cleanup and remove/reconfigure shared access.** Capacity expansion is not
safe to perform independently of this reservation contract.

The separate [node helper](../backend/src/prettylisavpn/fleet/ubuntu/shared_access.py)
is installed by [Ansible](../infra/ansible/shared-test-access.yml), preserving owner
helpers, keys, interfaces, certificates and active peers. The test key can only
grant/renew/revoke its own customer access. It cannot configure, probe, run cleanup,
inspect traffic, invoke a shell or use the owner's address/port ranges. Relay targets
are an explicit public-node allowlist. New exit grants also respect total node
capacity. All mutations share the owner's node mutex and short-lived access timers.

New test lease UUIDs have a controller prefix, but the prefix alone is not authority.
A root-only ownership journal rejects adoption/removal of any existing foreign UUID,
fences immutable access parameters and retains disconnect tombstones against late
retries. Independent test credentials stay outside Git and are never copied from the
owner's administrative keys.

## Deployment and recovery

1. Save current test environment configuration and copied outstanding lease rows.
   Detach only the initial clone's outstanding customer leases in the **test DB**,
   recording `IMPORTED_SESSION_DETACHED`; do not send any corresponding node revoke.
   This local closure is not evidence that a production peer was removed.
2. Enroll restricted keys/policies on each existing node and the owner snapshot host.
   Verify pinned host identities, denial of forbidden operations, owner helper hashes
   and active production sessions. Do not reinstall owner tooling through test bootstrap.
3. Persist the separate inventory/keys and the fleet env file through the existing
   durable deployment configuration. Set `FLEET_SHARED_NODES=true`,
   `CLIENT_VPN_ENABLED=true`, `MANAGED_VPN_ENABLED=true`, and
   `FLEET_WORKER_ENABLED=true` only after the verified backend update and enrollment.
   Persist `FLEET_SHARED_NODES=true` in release/canonical deployment env as well.
   Set GitHub **testing** environment variables `DEV_FLEET_SHARED_NODES=true` and
   `DEV_FLEET_WORKER_ENABLED=true` after activation so subsequent deploys preserve
   the role. CI rejects an enabled test worker without the shared role; production
   requires the owner role. The worker also refuses owner mode at the test origin.
   Keep test PostgreSQL/Valkey, OTP/DEMO identity and disabled payment/support settings.
4. Verify the actual `/version`, refreshed country availability, real test session
   issuance, tunnel egress and confirmed cleanup. Check production leases independently.
   Record source/build SHA, Actions run/attempt, installed helper hashes and actual
   acceptance evidence in the task PR after the last push.

Rollback: stop new test connections, let the shared customer worker confirm removal
of its own grants, then disable the worker and shared policies/revoke the separate
test keys. Retain journals/tombstones and local cleanup timers. Do not start the
ordinary owner worker on the test database or restore a production database snapshot.
No production backend deployment or schema downgrade is needed.

Unit and integration coverage includes disjoint allocation, foreign-UUID rejection,
late grant fencing, stale-snapshot admission/revocation, imported-lease startup refusal,
idempotent observation import and non-runnable imported operations. Source tests are
not a substitute for the recorded live tunnel acceptance.
