# Separate stability reports and daily usage — 2026-11-16

Backend 0.46.0 → 0.47.0; dashboard 0.13.0 → 0.14.0. New report pages and
historical distributions; clients and engine 0.8.0 unchanged. No new storage or
migration: existing schema 0050 holds the required lease lifecycle and configured
service-selection evidence. Product analytics revision 3 is unchanged.

## Pages

- `/dashboard/`: server stability, speed, server history and client downloads.
- `/dashboard/connection-methods`: connection-method availability and daily usage.
- `/dashboard/services`: service availability and daily configured selections.
- `/dashboard/product-analytics`: existing product analytics.

Every page shares navigation with an active-page marker. Direct URLs, trailing
slashes, reload and browser Back/Forward work through the existing private Caddy
route. Authentication remains mandatory for pages and their API aliases. The
server page no longer embeds method/service reports or their traffic-mode selector;
the service page directly describes «защита выбранного трафика» in its distribution.
Each report polls its own endpoint once a minute; unrelated report endpoints are
not fetched. Product analytics and download URLs retain their contracts.

## Daily distributions

The owner selected **sessions open during each day**, not average concurrency.
Each chart contains seven completed days plus today's incomplete day in GMT+3.
One confirmed session counts once on every day overlapping its open interval.
The interval starts at Internet verification and ends at the earliest recorded
disconnect, peer removal or expiry. A midnight end does not enter the next day.
A confirmed instantaneous session belongs to its verification day. Future and
unverified evidence is excluded; repeated sessions count separately.

Method distributions include all traffic modes and keep direct/relay methods
separate. Service distributions count each selected catalog service once per
include-mode session/day. Duplicate IDs are deduplicated. Manual rules and unknown
catalog IDs contribute one UNKNOWN per session. Known disabled catalog entries
retain their names in history. The report contains no raw rules or browsing data.
Rules remain in their existing private DB fields with existing retention.

Counts and percentages share the same daily evidence; percentages divide by the
sum of known category marks that day. Service marks can exceed the session count.
Known empty days have zero counts and undefined percentages. Before the earliest
recorded evidence, counts remain null. Unknown traffic modes, missing service
metadata and terminal legacy leases without an end timestamp are disclosed in
coverage. Such terminal rows prove their verification day only; later possible
days are uncertain and never invented as open sessions. A partial known subset
is graphed with dashed coverage outlines; entirely unobserved data stays a gap.
The current partial day has a separate purple outline and label.

Both private report endpoints add `selection_history` with ordered daily counts,
categories, totals and coverage. Existing instantaneous `selection` fields remain
for compatibility. The frontend accepts older responses without fabricating a
daily series from the instantaneous total. All data is read from existing durable
records; refreshing the page does not rewrite history or create collection jobs.

## Verification and release handoff

Unit tests cover multi-day overlap, exact midnight, expiry, future/zero-length
observations, missing evidence, UNKNOWN deduplication, daily shares and routes.
PostgreSQL tests cover both report contracts, closed-today versus currently-open
sessions, JSON null metadata, fresh reads, privacy and reserved test accounts.
Browser acceptance covers direct navigation/reload/back, isolation of endpoint
requests, eight daily bars, both unit modes, real minute refresh, error recovery,
keyboard inspection and mobile horizontal scrolling.

Deploy backend first, then the dashboard artifact and Caddy routes from the exact
successful develop merge. Preserve the previous dashboard/config for rollback.
Record source HEAD, PR temporary merge, release build SHA, run/attempt, artifact
digest, all CI checks and actual live-page verification in the task PR. No node
engine rollout or client publication is needed for these report-only changes.
