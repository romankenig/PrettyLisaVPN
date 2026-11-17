# Daily distributions and tariff filters — 2026-11-17

Backend 0.51.0 → 0.52.0; fleet dashboard 0.16.0 → 0.17.0. Both are MINOR
features. Clients and VPN engines are unchanged. Base develop `8f6492e9`.
Migration `0053_analytics_plans` follows `0052_pending_devices` and adds nullable
tariff snapshots to client leases and device/day app activity, with value checks.
It does not relabel historical records or backfill from today's subscription.

## Daily duration charts

Each bar is the GMT+3 day of successful connection verification; one session
belongs to one start day even if it crosses midnight. The six inclusive upper
bounds remain 10s, 60s, 180s, 300s, 900s and above 900s. Duration ends at the
recorded disconnect; first silence is the beginning of the first confirmed 10s
without counter changes. Gaps in counters never imply silence.

The product report adds `duration_history`, covering two calendar months plus
today. Both charts have independent counts/shares controls. Shares use completed
observations within each day, separately for duration and silence. Unobserved
sessions are shown in coverage/tooltips, never assigned zero duration. Unknown
days are null; known empty days have zero counts and undefined shares. Today is
marked incomplete. Minute refresh can update earlier start cohorts after late
completion, without modifying stored completed-day product snapshots.

## Tariff meaning

All five private report pages have a tariff control: All (default), DEMO, Free,
Premium, Platinum, Unknown. The URL query retains selection across navigation.
An obsolete request is aborted; a mismatched/old tariff response cannot be shown
under a newly selected tariff. Polling keeps the current selection.

- DAU/WAU/MAU and their shares: latest account activity inside each calendar
  window, chosen before filtering. An account that upgrades is not counted again
  in its former tariff for the same window. Registration counts use the last
  observed activity on the registration day, otherwise Unknown. DEMO accounts
  remain excluded from registration counts, as before.
- VPN/device/duration/connection-success metrics and method/service usage: tariff
  frozen when the lease is created. Later subscription changes never move the
  lease. Existing exact snapshots win; legacy DEMO email identity and `is_free`
  recover DEMO/Free. Old paid leases without exact evidence remain Unknown.
- Versions: tariff at the latest authorized app activity for each device/day;
  older late writes cannot overwrite it. Old rows without tariff remain Unknown.
  This is app activity, not VPN connection success; platforms remain separate.
- Actual user speed: stored counter intervals carry the lease tariff. Filter
  before account union, activity threshold and averaging. Pre-migration intervals
  without this tag are Unknown; no historical backfill. Synthetic throughput
  references remain shared.

Synthetic server/method/service availability and technical server counters have
no historical user-tariff attribution and remain shared, explicitly explained on
their pages. Method/service outcome controls retain Successful as default and
their separate All/Unsuccessful choices. The filter applies to all outcomes and
legacy instantaneous usage fields. Configured service rules stay in the database;
reports contain aggregates only, with UNKNOWN for manual/unrecognized services.

## API and rollout

Existing private `product-analytics`, `app-versions`, `connection-methods`,
`services` and `active-user-speed` endpoints accept optional `plan` enum query.
Omit the query for All; invalid values return 422. Authorization is unchanged.
Responses add `plan`; old dashboards can ignore the additive fields. An old
backend can still serve All in the new dashboard; selected tariff requests fail
closed if the response omits/mismatches `plan`.

Use checked backend migration/deploy before the exact successful develop dashboard
artifact. No VPN-node helper changes, client rebuild or new worker are required.
The existing five-second counter collector writes the additional tariff tag.
Rollback may retain nullable added columns; do not downgrade while new binaries
are running. Runtime identity must come from GET /version and artifact metadata.

## Validation and release evidence

Tests cover inclusive bounds, midnight/start cohorts, late completion, silence
confirmation, missing versus zero observations, window-before-filter deduplication,
historical fallback, authentication and invalid queries. PostgreSQL tests cover
immutable lease plans, both usage outcomes, preserved synthetic checks, read-only
product snapshots, late app writes and filtering before the speed threshold.
Frontend tests cover daily denominators, contract validation and tariff URLs.
Browser checks cover both daily charts, counts/shares, minute refresh, failures,
wrong-tariff rejection, navigation, keyboard access and mobile overflow.

Local Windows unit suite: 884 passed, 20 skipped; four existing deployment-shell
tests cannot invoke `/bin/bash` in this host's WSL. Linux CI is required for those
tests and real PostgreSQL migration/integration checks. Frontend: 53 tests and
TypeScript/Vite production build passed. This file does not claim a deployed build.
The task PR records verified source HEAD, temporary merge SHA, all workflow events
and jobs, actual release SHA/run/attempt/artifact, and live verification results.
