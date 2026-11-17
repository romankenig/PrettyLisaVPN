# Report tariff multiselect

Backend 0.52.1 → 0.53.0 and dashboard 0.17.0 → 0.18.0 add a compatible
multi-tariff filter. Clients and VPN engines are unchanged; schema remains 0053.

All five report pages show native checkboxes for DEMO, Free, Premium, Platinum
and Unknown, plus a master All tariffs checkbox. All are initially selected.
The master checkbox is indeterminate for a subset; clearing all leaves an
explicit empty selection with a visible explanation. Keyboard Space toggles each
checkbox. Controls wrap on narrow screens. Selection survives report navigation,
reload and minute refresh; changing a filter aborts obsolete requests and hides
results for the previous selection. Synthetic checks remain shared.

Selected tariffs form one union of source observations before aggregation.
Audience windows still choose the latest account activity before filtering;
device/version users are deduplicated across the selected tariffs. Speed combines
selected account intervals before applying activity thresholds. Duration bins and
method/service outcomes use the combined daily denominator. Summing separately
rendered tariff reports would not preserve these rules and is not used.

## Compatible API

The existing optional `plan` query accepts comma-separated tariffs, for example
`plan=FREE,PREMIUM`. Repeated parameters are accepted too. Order and duplicates
are normalized. Omitted query means All; `plan=NONE` means no user observations.
An explicit list of all five tariffs normalizes to All. Existing single-tariff
requests retain their behavior and response shape. Invalid/empty values or a
mixture of NONE and tariffs return 422. Authentication is unchanged.

The response `plan` is a canonical key: ALL, NONE, a single tariff, or selected
tariffs joined in DEMO/FREE/PREMIUM/PLATINUM/UNKNOWN order. The dashboard checks
that exact key before displaying data, including nested duration history.
Old backends reject multi-tariff queries rather than silently returning one tariff;
deploy backend before the dashboard. Existing single-tariff bookmarks still work.

## Validation and release evidence

Unit tests cover all 32 subsets, empty versus all, malformed inputs, canonical
URLs, account/device deduplication, combined duration shares and version activity.
All five endpoints have auth and multi-query contract checks. PostgreSQL tests
cover combined successful/failed usage, read-only product history, empty selection,
and combined speed intervals crossing the activity threshold.

The task PR records exact source HEAD, temporary PR merge SHA, all Actions events
and jobs, release SHA/run/attempt, backend runtime/image and dashboard artifact.
Local fixture checks and live checks are recorded separately. This document does
not claim a deployed build or acceptance of an older artifact as the new UI.
