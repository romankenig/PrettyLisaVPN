# Application version usage — 2026-11-16

Backend 0.47.0 → 0.48.0 and dashboard 0.14.0 → 0.15.0 introduce a new private
report and durable observations. Chrome Extension 0.4.0 → 0.4.1 adds compatible
version metadata to existing API requests. Other clients and VPN engines are
unchanged. Baseline: develop `61d03c42a97889ff3a4dde01ebb7d5bc1085b1c0`.

The owner chose **application activity**, not VPN connections: authenticated API
requests, account reads, token refreshes and logout. No anonymous website requests
or install/download counts are treated as active app users.

## Capture and interpretation

Migration `0051_app_versions` creates `product_app_activity_days`, keyed by device
and GMT+3 date, and records the collection start in `product_analytics_collection`.
Account/device/platform identity comes from authenticated backend state. Versions
are client-reported SemVer (maximum 100 characters), with build metadata removed
and prerelease identity retained. Headers never establish identity or authority.

Existing registered Windows, Android and Apple clients already send a version in
the `/messages` contract. Successful, platform-matching message reads now record
it without changing responses. Chrome 0.4.1 sends the manifest version through
`X-PrettyLisaVPN-App-Version` on authenticated control-plane API requests only;
it is not sent to tunnel probes or browsing destinations. A request-scoped context
is reset even on failure. Missing/malformed metadata does not reject an otherwise
valid request. Collection failures/timeouts cannot invalidate authentication.

Each device/day keeps its last reported version and last activity time. Late old
observations cannot overwrite a newer version. Requests without a version do not
erase one already observed that day. Nothing is carried from yesterday: legacy
clients and DEMO clients that do not report a version remain UNKNOWN. Existing
Windows/Android/Apple users acquire known versions when their message list next
refreshes; Chrome users need the updated extension. Guest activity is counted by
its existing DEMO account identity. Reserved test accounts are excluded.

For each platform/day/version, count unique accounts and devices separately.
Multiple devices with the same version do not multiply users. An account using
different versions on different devices belongs to both categories; the percentage
denominator is the sum of category memberships. The current-day table also shows
the unique active account total across versions. Updating the same device within
one day moves its contribution to the last reported version. Versions are grouped
independently per platform; Chrome Extension is never Windows.

No previous version history is reconstructed. Dates before collection are null,
known empty days are zero, and the first collection day starts at the displayed
collection time. The report covers 30 previous days plus today. The existing daily
analytics worker removes observations older than 180 days. No browsing history,
request paths, destination URLs, IP addresses or raw headers are retained. The
private aggregate response exposes no user or device identifiers.

## UI and compatibility

`/dashboard/app-versions` and its trailing-slash variant join the shared private
navigation. `/dashboard/api/app-versions` proxies the monitor-authenticated
`GET /admin/monitoring/app-versions`. The page polls once a minute, keeps platform
and counts/shares selection on refresh, shows the current incomplete day and
retains the prior timestamp/data after a refresh failure. Desktop and mobile
charts have aligned fixed axes, day inspection and horizontal scrolling.

Existing analytics endpoints, stored product snapshots and message responses are
unchanged. Older clients need no protocol update; old backends ignore the Chrome
header. Apply migration/backend first and then install the dashboard/Caddy routes
from the exact successful develop artifact. Chrome publication follows the shared
verified client-download workflow; unpacked installations still require updating.
No VPN-node rollout or new scheduled collector is necessary.

## Validation and release record

Unit and PostgreSQL tests cover SemVer, account/device deduplication, concurrent
upserts, upgrades, late writes, missing metadata, platform ownership, unauthorized
requests, Chrome separation, GMT+3 midnight and privacy. Endpoint authorization,
request-context isolation and non-fatal analytics failures have dedicated tests.
Frontend tests cover daily denominators, absent versus empty data, UNKNOWN and
contract validation. Chrome tests check metadata stays on authenticated API calls.

Record final source HEAD, temporary PR merge, actual develop SHA, all Actions
events/jobs/checks, runtime version, migration, dashboard and Chrome artifacts with
run/attempt/digests and actual live-page acceptance in the task PR after validation.
Do not assert historical adoption or deployment solely from source implementation.
