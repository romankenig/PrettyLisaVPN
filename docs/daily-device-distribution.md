# Daily device distribution — 2026-11-15

The owner added this task while authorizing the PR #86 release. It advances
the not-yet-released backend 0.43.0 → 0.44.0 and dashboard 0.10.0 → 0.11.0.
Engine 0.8.0 and all client versions remain unchanged by this follow-up.
The combined rollout upgrades the live backend 0.42.0/dashboard 0.9.0.
Schema stays at 0050; no new database fields or collection are needed.

The device chart now contains one stacked bar per completed calendar day in
the report's two-month window (GMT+3). Colors distinguish device platforms.
The default measure is **Юзеры**: unique account IDs per platform and day of
successful VPN verification. Repeated connections and multiple devices on the
same platform count once. The same account using two platforms counts in each.
**Подключения** counts every verified lease on its verification date; failed,
unverified and current-day sessions are excluded. Test accounts are excluded.

Counts are the default unit. The percentage switch divides each platform's
selected measure by the sum of platform counts for that day. Because accounts
can use several platforms, this denominator is not a global unique-account
total. A known empty day has zero counts and undefined percentages; missing
history stays null. Missing platform metadata belongs to UNKNOWN. The chart
supports horizontal scrolling on narrow screens and keyboard day inspection.

The private product-report endpoint adds `device_platforms.connections` and
`device_platforms.users` to each daily point. The old period-wide `devices`
aggregate remains for compatibility. Account identifiers remain inside the
database/application service and never enter the report, logs or browser.
Snapshot metrics revision 3 rebuilds the existing current snapshot once from
durable evidence, then retains the daily refresh cadence. Old report responses
remain readable; the UI does not invent daily data from a period-wide total.

Unit tests cover repeat connections, account/platform/day deduplication, the
GMT+3 boundary, unknown metadata and null versus zero. PostgreSQL tests exercise
real lease/account/device joins, reserved-test-account exclusion, private
aggregate responses and revision-2 snapshot refresh. Frontend tests validate
daily count/share denominators, gaps and invalid payloads. Browser review checks
the users default, both switches, daily bars, keyboard detail and mobile scroll.

Release order remains engine 0.8.0, backend 0.44.0/migration 0050, dashboard
0.11.0. Final product/build SHA, run/attempt, artifacts and actual live-report
verification are recorded in [PR #86](https://github.com/romankenig/PrettyLisaVPN/pull/86).
Source changes alone do not claim deployment.
