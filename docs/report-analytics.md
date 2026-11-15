# Availability and product reports — 2026-11-14

Current-day follow-up: [all product charts](current-product-analytics.md) include
today's partial observations with minute refresh (backend 0.46.0/dashboard 0.13.0).

## Versions and contract

Backend 0.41.0 → 0.42.0 (after integrating the independent Chrome/email-identity
release); dashboard 0.8.0 → 0.9.0; managed engine
0.6.2 → 0.7.0 (new server-only synthetic service request). Windows
0.28.1 → 0.28.2 and Android 0.27.3 → 0.27.4 / code 54 add configured-selection
metadata at admission. Client screens and navigation are unchanged. Apple and
Chrome versions remain unchanged; their existing all-traffic sessions contribute
device and duration metrics through backend evidence.

Migration `0049_report_metrics` follows `0048_refresh_retry` and is additive except for extending the analytics
plan constraint to include DEMO. Deploy backend/migration before new clients:
older clients remain accepted; older backend builds reject the new optional
request fields. Billing, entitlements, admission and quota semantics are unchanged.

## Availability report

- The default speed view is seven completed calendar days in GMT+3. Each point
  is one day, computed from original counter intervals with the existing activity
  threshold. Means use bytes / account-active seconds; user medians retain distinct
  accounts. Reference speed is the median of per-server medians of all synthetic
  measurements in the same day. The 24-hour monitoring view remains available.
- “Защита выбранного трафика” opens service history and a live selection histogram.
  The protected GET `/admin/monitoring/services` returns aggregates only; Caddy
  exposes its fixed dashboard alias under the existing Basic auth.
- Each enabled catalog service receives one durable assessment per GMT+3 day.
  New services are assessed on initial startup, staggered one minute apart.
  Subsequent daily slots are spread across 23 hours with deterministic daily
  jitter. Restart preserves attempts, claims and results; missing past days are
  never fabricated. Seven completed dates are graphed, with today's result shown
  separately and the number of observed days stated alongside the weekly mean.
- Each attempt chooses a random unused exit/protocol combination and a separate
  probe source. Retries prefer changing both server and protocol; a fleet with only
  one available dimension still exhausts unique pairs. Eligible methods are
  configured direct WireGuard and native managed transports; transit-only nodes
  are probe sources, never exits. Browser-only proxy and relay variants are not
  included in this synthetic route roster.
- Unsuccessful checks retry no earlier than one minute after the previous attempt.
  Each assessment ends on success, after 30 attempts, after all eligible pairs,
  or 30 minutes from its first attempt. Busy node locks postpone a check. Immediate
  success scores 100; a retry scores `100 * (1 - elapsed_seconds / 1800)`, floored
  at zero. Failed terminal assessments with actual measurements score zero;
  missing route/sample evidence stays null. This is recovery latency, not the
  percentage of successful requests or a service-wide SLA.
- Discovery samples links from the primary catalog domains and advertised RSS/Atom
  feeds, preferring publication paths/recent feed entries. A random candidate is
  confirmed to exist before testing over the chosen VPN route. Services without
  discoverable public links (for example, login-only/JavaScript-only surfaces)
  remain explicitly unobserved. No login, captcha bypass or invented content URL.
- Discovery and probe requests are bounded HTTPS requests. Hosts/redirects must
  stay within catalog domains; DNS answers must be public and are pinned to the
  TLS connection. VPN DNS and HTTPS use the encrypted core or isolated WireGuard
  namespace. Sampling uses no customer rules, account identity or browsing data.
  Synthetic URLs live only in memory/pipes; logs and history contain fixed codes,
  node IDs, methods, timestamps and scores. Old helpers cannot count a generic
  successful VPN check as a service success.
- Histogram unit: one selected service per confirmed open session (`READY`,
  verified and unexpired). Repeated IDs are deduplicated; multiple manual rules
  produce one UNKNOWN per session. Share denominator is the sum of all service
  selections, not the number of users. A session can select several services.
  Missing selection metadata is excluded and reported as incomplete coverage.
  Exact manual rules are stored privately in `client_wireguard_leases.custom_rules`
  for operator investigation; they never appear in the aggregate API. Rules are
  configuration, not visited destinations. Completed-session manual rules and
  first-silence evidence are pruned after 180 days; probe assessments after 30 days.

## Product report

- DEMO is a separate activity-time cohort. Guest identities are included in the
  active audience; email registration counts still exclude anonymous admission.
  Available guest lease observations can restore actual activity timestamps only.
  Later account tariffs never relabel earlier recorded observations.
- Each DAU/WAU/MAU chart switches between counts and tariff shares (shares default).
  DEMO + Free + Premium + Platinum + Unknown sum to the active audience. No
  percentage is shown for an empty audience.
- Device distribution originally counted confirmed sessions for the whole period.
  The owner-requested follow-up replaces that chart with daily stacked platform
  bars and a users/connections switch (users default), while retaining count/share
  units. See [daily device distribution](daily-device-distribution.md) for account
  deduplication, percentage denominators and snapshot revision 3.
- Connection duration starts at backend egress verification, ends at the first
  disconnect/revocation decision or entitlement expiry, and excludes peer-cleanup
  delay. It describes a logical VPN session: device sleep is not a disconnect.
  Historical sessions without this evidence and still-open sessions are excluded,
  with their count shown. Daily averages use disconnect date; the period histogram
  uses the cohort of sessions verified during the report period.
- First silence is the start of the first ten continuous seconds with no increment
  in either byte counter. Five-second sampling provides approximate boundaries;
  any earlier sampling gap, epoch change/reset or missing baseline invalidates
  first-silence inference for that session. Silence confirmed after the report
  cutoff is excluded. No packet inspection, destination or DNS collection.
- Both duration histograms use `(previous bound, bound]` at 10, 60, 180, 300,
  900 seconds and a final >900s bucket; zero is included in the first. Counts and
  percentages are available. The saved report refreshes immediately after a
  metrics revision, then once per completed day in the existing independent worker.

## Validation, rollout and evidence

Base: develop `6868e484`. Exact final product HEAD, CI checkout/merge SHA,
run/attempt and artifact links are recorded in the task PR, updated after the final
push rather than by another documentation-only commit. This document is not a
claim of deployment or live service reachability.

Local validation: backend Ruff/mypy and available Windows-host unit tests;
dashboard TypeScript/Vite and Node tests; Windows TypeScript/ESLint, tests and
format checks on changed files; managed node Go tests. CI must additionally verify
PostgreSQL upgrade/check/downgrade, integration tests, Linux deployment tests,
Android builds/lint/tests, managed engines and triggered client builds. Dashboard
browser review uses explicitly synthetic fixtures, not live production metrics.

Rollout requires backend 0049, the matching verified node-engine artifact and
updated Ansible node helpers (including `service_probe.py`), fleet worker, then
dashboard/Caddy and clients. Existing running customer connections are preserved.
Allow a week for a complete availability history; silence history starts with
newly observed sessions. The owner subsequently authorized release through develop: PR #82 merged at
`6177e2e53da41413f60385686d9f1f8e425b0492`; backend 0.42.0 deployed in run
`43690059961`, attempt 1. Dashboard and all four node helpers were installed
before client publication. Exact artifact identities and final publication/CI
evidence are in [PR #82](https://github.com/romankenig/PrettyLisaVPN/pull/82). Ordinary rollback retains additive tables and stops
the new worker code; database downgrade deletes new analytics evidence.
