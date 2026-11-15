# Current product analytics day — 2026-11-15

Backend 0.45.0 → 0.46.0; dashboard 0.12.0 → 0.13.0. This extends the live
device day to every product report chart and the summary cards. Clients and
managed engine 0.8.0 are unchanged. Schema remains 0050 and saved metric revision 3.

The existing private GET adds `live`: `partial=true`, UTC `updated_at`, today's
`point`, period `from_date`, and duration `summary`. The GMT+3 day includes evidence
up to the request time. DAU/WAU/MAU retain calendar windows of 1/7/30 days ending
today and the latest observed tariff within each window. Historical subscription
cohorts are never inferred from a user's current subscription. Registrations,
verified connections, settled attempts, engagement and disconnect-day mean
duration use the same domain calculations as daily history.

Period histograms include sessions verified during the two-month window through
now, including today. Only actual disconnections and confirmed first silence
(10 seconds of unchanged counters) contribute durations. Open sessions and
unobserved silence remain explicitly unobserved. Sessions started before today
and disconnected today contribute to today's mean; pending attempts do not enter
the connection-success denominator. Future evidence and reserved test accounts
are excluded; DEMO remains a separate activity cohort, not a new registration.

All live aggregates come from one read-only repeatable-read PostgreSQL transaction.
Reads reuse the existing bounded evidence queries and calculate only one daily
point plus period histograms. They never publish or alter saved snapshots.
`device_today` remains for dashboard 0.12 compatibility and comes from that same
point. Existing top-level aggregates still describe the completed-day snapshot.
Older responses remain readable during rollout.

The page requests fresh data every 60 seconds after each response, including
after errors. Every chart and current summary card labels today «неполный день»;
time-series charts also highlight the current point and mark its tooltip. The
duration histograms label their inclusion of today's incomplete observations.
Selected display modes survive polling. Failed requests retain the previous
result with an error notice and its actual update timestamp. At midnight a new
current point replaces the old one; gaps awaiting daily publication stay null.
No new destinations, browsing data, account identifiers or emails enter the API.

Validation covers rolling calendar windows and tariff changes, exact time cutoff,
cross-midnight disconnects, confirmed silence, null versus zero, unchanged saved
history, live PostgreSQL rereads, test-account exclusion and legacy parsing.
Browser review covers every chart, minute polling, error recovery, midnight gaps
and desktop/mobile layouts. This changes no client routes or navigation.

Release through develop: deploy backend first, then the dashboard artifact built
from the exact successful merge SHA. No VPN-node update or migration is needed.
Record product HEAD separately from PR temporary merge/build SHA, all workflow
runs/attempts and artifacts, actual `/version` and live report evidence in the PR
handoff. Source implementation alone is not deployment evidence.
