# Windows server outage disconnection

Windows 0.31.3 → 0.31.4 (PATCH). Backend 0.54.1 and all other clients: version
unchanged. Existing managed lease APIs and schema remain compatible.

## Behavior and cleanup boundary

The shared session adapter notifies the executor only after native.stop succeeds.
Home then shows «ОТКЛЮЧЕНО», clears connection details and offers Connect while
remote removal completes. An unsuccessful remote request produces a localized
server-connectivity notice, not a local-stop failure. The lease/ambiguous allocation
remains owned by the adapter; reconnect retries its cleanup before creating any
new grant or trying another transport. Startup recovery also retains failed lookup.
Remote cleanup errors still reject the manager operation so account/logout flows
cannot silently discard their recovery credentials. The Home disconnect handler
uses the precise manager state instead of adding a misleading connection error.

An established connection ends on its first failed health check, including API
transport/5xx, native service loss or failed tunnel verification. Detection still
uses the existing 30-second heartbeat and bounded native/HTTP requests; this is
not an instantaneous server-push notification. Once detected, local shutdown is
independent of remote cleanup latency. Initial setup retains sequential fallback.
No automatic reconnect or browsing telemetry is added.

The country dropdown stays openable during loading, refresh, server outage and
active connections; opening it uses a pointer, not a waiting cursor. All server
catalog countries are shown, including currently unavailable and Premium-locked
entries. The latest successful catalog is cached per API/account/plan for browsing
after navigation or restart. Cached availability is explicitly unknown, has no
live quality bars and cannot authorize selection. Changing an active connection
remains blocked. With no saved catalog, the dropdown explains that the list has
not loaded instead of inventing countries. A failed/disabled local storage does
not prevent using the live catalog. Profile refresh no longer restarts the country
request merely because the session object changed.

If native shutdown fails, the UI cannot claim disconnection: it shows the local
shutdown error and allows another Disconnect attempt. Remote revocation is still
attempted, and local errors take priority if both operations fail. No Free quota
is refunded locally; only the existing backend confirmation rules may release it.

## Validation and distribution

Regression tests cover slow and failed removal, retry fencing, simultaneous local
and remote failure, startup outage, the first connected health failure, and Home's
status/button/message. The Windows UI review exercises remote outage/recovery
through synthetic adapters in the actual Tauri/WebView2 window and captures
`04h-home-server-unavailable-disconnected.png`. It is UI evidence, not a real
VPN outage or live traffic acceptance test.
Additional native captures cover cached countries during a server outage,
unavailable countries and read-only browsing while connected. Regression tests
cover loading/keyboard access, cached refresh failure, cache validation, plan
isolation, storage failure and continued Premium/DEMO selection rules.

Exact verified product HEAD, PR merge build SHA, workflow run/attempt identities,
artifacts and final check results are recorded in the task PR after the final push.
No production deploy or distribution is claimed by this source change. Merge
and release remain separate instructions; after an approved develop merge, verify
[the shared client publisher](dashboard-client-downloads.md) and stable dashboard
Windows URL. No backend follow-up is required.
