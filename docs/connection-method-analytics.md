# Connection-method availability — 2026-11-15

Backend 0.42.0 → 0.43.0; dashboard 0.9.0 → 0.10.0; managed engine 0.7.0 →
0.8.0. These are new reporting/probe capabilities. Client versions and screens
are unchanged; method IDs already accompany every lease. Migration
`0050_method_checks` follows `0049_report_metrics` and adds one table.

Before release, the owner requested [daily device distributions](daily-device-distribution.md).
That separate reporting task advances backend to 0.44.0 and dashboard to 0.11.0
within the same PR; engine remains 0.8.0. The combined release uses those versions.

## Meaning of the report

Each of the 23 supported method IDs has its own daily assessment. Direct and
relay (`+`) variants are distinct. A method remains fixed during an assessment;
each attempt chooses a random unused exit/relay pair, preferring another exit.
The source is a separate enrolled node, never the exit or relay. Therefore this
measures reachability from fleet nodes, not success rates in users' networks.

The same catalog sampler as service analytics chooses a random existing public
publication, preferring fresh links. Each attempt samples an enabled service;
URLs remain in memory and never enter PostgreSQL, API responses or logs. No
customer browsing data or configured manual rules are used for these checks.

The first attempt succeeds at 100; later success scores
`max(0, 100 × (1 − elapsed attempt-start seconds / 1800))`. Success must finish
within the 30-minute assessment deadline. Failed attempts retry no earlier than
one minute later. Thirty attempts, the deadline, or exhaustion of unique routes
ends the assessment. A measured terminal failure scores zero; absent routes,
samples or actual measurements remain null. A generic VPN-health result cannot
count as a successful public-service request. This is a recovery-time score,
not an SLA or percentage of successful customer connections.

Initial checks are staggered one minute apart, starting 30 seconds after startup.
Subsequent assessments use persistent daily jitter over 23 hours in GMT+3.
Restarts preserve claims, attempts and completed results. Busy nodes postpone
probes. The graph contains seven completed calendar days, today's result is
separate, and the weekly mean includes only observed days with explicit coverage.
No historical backfill. Assessment retention is 30 days.

## Isolation and compatibility

Relay probes provision an actual temporary UDP/TCP forwarding rule, keeping the
exit's cryptographic identity and expected egress IP. They revoke both relay and
exit access. Synthetic relay port reservations share the node row locks with
client admission and are excluded from customer allocation. Uncertain cleanup
or a crashed claimant retains the reservation for five minutes, beyond the node
TTL. Existing client renewal can coexist with a synthetic check and does not
steal its node lock. Checks use reserved monitoring addresses/engine ports.

HTTPS proxy uses the existing per-lease browser proxy, a publicly trusted TLS
connection and authenticated CONNECT. Destination DNS runs on the exit, whose
proxy validates and pins public IPv4 answers. Owned egress verification and the
catalog HTTPS request traverse that proxy; no system TUN or user browser is used.
The probe accepts only its bounded server-generated profile and fixed web ports.
Old node engines reject this profile; deploy the matching engine before enabling
the new worker. Native protocol profiles and client API contracts are unchanged.

The protected GET `/admin/monitoring/connection-methods` and its fixed dashboard
alias return aggregates only. Its histogram counts one verified READY unexpired
session per method, across all traffic modes. Counts and shares use the same
denominator; relay variants remain distinct, and test accounts are excluded.
No user, device, lease or node identifiers are exposed by this report.

## Rollout and verification

This is a separate follow-up to PR #82, merged into develop at
`6177e2e53da41413f60385686d9f1f8e425b0492`. Its backend 0.42.0 deployed through
Actions run `43690059961`, attempt 1; `/version`, readiness and all four nodes
were verified. Dashboard 0.9.0 came from PR build
`97aba1b1260e1b286e561c03b6e2ef755ef5a99d`, run `43607368186`, attempt 1,
artifact `14119015678`; those dashboard sources match the merge. Node engine
0.7.0 came from build `00d9b29a0ba2c694bef8ad961cc667ba1b840ccc`, run
`43604912114`, attempt 1, artifact `14118201842`, with identical engine/helper
sources. Exact final client publication and all-events CI evidence are kept in
[PR #82](https://github.com/romankenig/PrettyLisaVPN/pull/82).

For this follow-up, deploy verified engine 0.8.0 and backend 0050/0.44.0 before
dashboard 0.11.0. Application rollback retains the additive table; database
downgrade deletes new method evidence. No release of this follow-up is claimed
by source changes. The task PR records final product/build SHA, run/attempt,
artifacts, test counts and actual deployment status after checks complete.

Coverage includes route exhaustion, null/zero distinctions, strict deadlines,
actual relay endpoint/cleanup, CONNECT authentication, private endpoint access,
daily restart-safe scheduling, client port exclusion/renewal and aggregate
privacy. UI checks cover seven daily points, gaps, protocol names and counts/shares.
