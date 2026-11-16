# Daily connection outcomes — 2026-11-16

Backend 0.49.0 → 0.50.0; dashboard 0.15.0 → 0.16.0. The daily method and
selected-service charts gain independent All / Successful / Unsuccessful controls,
defaulting to Successful. Counts/shares remain a separate control. Clients and VPN
engines are unchanged. No schema change: migration 0052 from the device-limit task
already follows app-version migration 0051. Base develop: `4a82a672`.

## Meaning and evidence

Successful sessions retain the previously accepted daily overlap: one mark per day
from Internet verification to disconnect/removal/expiry, with exclusive midnight
ends. A session that succeeded and later disconnected stays successful.

An unsuccessful attempt is an existing durable lease without verification that
has entered REVOKING/CLOSED, has a recorded disconnect/removal, or has expired.
This includes cancellation before confirmation. It counts once on its creation
day in GMT+3, even when cleanup finishes later. Provisioning/READY without a final
result stays pending; transient node errors do not make it unsuccessful. All is
the union of successful session-days and unsuccessful attempts; pending attempts
are excluded until their result is known. Later settlement can update the creation
day's unsuccessful count. Repeated requests for the same idempotent lease do not
multiply it. Errors before a durable lease is allocated are not available in this
report; this is not a count of all HTTP errors or of every click on Connect.

Methods include every traffic mode and keep direct/relay variants separate.
Services include only include-mode leases, using their saved configured choices
even when connection failed. Each selected service contributes one mark per lease;
manual rules and unrecognized IDs combine into one UNKNOWN mark. This outcome
describes the VPN connection, not whether the service itself was reachable.
Missing legacy choices/modes retain gaps or explicit partial coverage; no browsing
history, URLs, identifiers or raw manual rules enter the report.

Shares use the selected outcome's known category marks separately for each day.
Unsuccessful attempts do not acquire imaginary open days. Successful legacy rows
without a recorded end retain the existing uncertainty rules. No data before
recorded coverage is invented; known empty days are zero with undefined shares.
The eight-day window includes today marked incomplete, refreshed every minute.
Outcome and unit selections persist through refresh and refresh failure.

## Compatibility and rollout

The existing private method/service endpoints add `selection_history.outcomes`
with successful, unsuccessful and all histories. The parent history still means
successful sessions for old dashboards; legacy instantaneous fields are unchanged.
All outcomes use the same category list so switching filters preserves colors.
The new dashboard accepts old responses for Successful and displays unavailable
history for the other outcomes instead of substituting successful counts.

Deploy the checked backend before the exact successful develop dashboard artifact.
No new routes, worker schedules, collection jobs, client changes or VPN-node rollout
are needed. Existing product snapshots and app-version records are read-only here.
The task PR records source HEAD, temporary merge, actual build/deploy SHA,
run/attempt/artifact digests, all CI events/jobs/checks and actual live acceptance.

## Validation

Unit tests cover terminal versus pending status, transient errors, verified cleanup,
future records, per-day overlap, failure on the creation day, unknown service marks
and coverage. PostgreSQL tests exercise both real report endpoints' services,
metadata, late settlement, test-account exclusion and aggregate privacy. Frontend
tests cover outcome denominators, stable colors, missing outcomes and compatibility.
Browser checks cover both default selections, all outcome/unit combinations,
tooltips, midnight/current-day labels, refresh retention and mobile wrapping.
