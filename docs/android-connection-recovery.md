# Android connection recovery — 2026-11-07

Android **0.23.1/code 45 → 0.24.0/code 46** (MINOR): background data-plane health,
bounded automatic recovery, adaptive method preference and a manual reset control.
Backend/API/schema, VPN engine binaries and other clients keep their versions.
This is the owner's third independent Android task in PR #64, after subscription
presentation (0.23.0) and optional-location presentation (0.23.1).

## Health and lifecycle

Initial connection still requires the real adapter's authenticated egress check.
While connected, a process-owned coroutine checks every 30 seconds. Failed checks
repeat at 5-second intervals; three consecutive transport failures or wrong observed
egress results trigger recovery. A native tunnel-loss signal requests an early
check. The status becomes checking on suspicion, waiting for network when Android
has no physical network or a failure cannot be separated from unvalidated physical
Internet, and reconnecting during cleanup/reselection. A healthy tunnel probe is
accepted even when Android's own Internet-validation origin is blocked; validation
does not prevent probing an available network.
Single failures, provider errors and offline periods do not penalize a method.

Anonymous, size-bounded HTTPS requests bind DNS and sockets to the adapter's exact
VPN Network, disable redirects/replay and are cancellable. ifconfig.me reports the
exit IP; api.prettylisavpn.com/version is a fallback for metadata-provider failure.
Both origins already have mandatory VPN routes in split mode. A valid but wrong
exit cannot be overridden by the fallback. Two transport failures are unreachable;
HTTP/provider/invalid-body ambiguity is unknown, not proof of a broken tunnel.
No browsing destinations, packet contents, account headers or location history are
collected or logged. No physical-network fallback is used for these probes.

The original country request is retained for recovery; server admission remains
backend-owned. Every old local tunnel and remote lease must close before another
adapter starts. Failed cleanup fences recovery. There are at most three automatic
recoveries in ten minutes; exhausting methods or the budget stops with an error.
There is no reboot/force-stop resurrection. Android may defer timers in deep sleep;
PowerManager deep-idle suspends probes, retains the last real status and resets
failure confirmation. A request finishing during deep idle is also disregarded.
Elapsed sleep alone is never counted as a failed probe.

AndroidVpnHost now owns foreground-service shutdown after an idle or terminal
non-cleanup state. Adapters no longer stop it between fallback/recovery attempts.
This preserves the existing ongoing notification and background execution context.
App and notification disconnect, logout, revocation and paid/free lease deadlines
cancel monitoring and pending reset; they cannot be undone by a late probe result.
The existing access heartbeat remains authoritative and does not auto-renew access.

## Method selection and UI

The last verified method remains saved. On a new connection, a 10% exploration
decision tries one eligible alternative before the known successful method. No
working tunnel is interrupted for exploration. A confirmed delayed failure puts
that method behind other eligible methods for 30 minutes, across app restarts.
Only method IDs and failure timestamps are stored locally. User-disabled methods
remain disabled; cooled-down methods remain available as a last resort.

The 48dp reset icon beside Connect clears preference/failure history, closes the
current attempt/session, then starts selection for the displayed country. It has
a localized accessibility label in all six languages. It does not change traffic
rules, selected allowed methods, authentication or server-side entitlements. A
manual disconnect during cleanup cancels the queued reconnect.

## Verification and delivery

Unit scenarios use a virtual coroutine clock for repeated failure, transient loss,
network return, unknown responses, cleanup barriers, owner changes, cancellation,
manual reset and bounded flapping. MockWebServer covers exact egress, secondary
provider, wrong egress, bounded bodies, anonymous headers and cancellation. Method
tests cover exploration ordering, persisted cooldown expiry and reset. Existing
traffic-change cleanup tests now include all recovering states.

Native controller/UI tests cover reset, offline/healthy recovery, delayed failure
and an alternate method, plus app/notification state labels and screenshots. The
placeholder executor suite now has two tests; AccountScreensTest remains 21.
These fixtures do not claim a real remote tunnel failure or a test on the owner's
phone. Actual source SHA, build SHA/run/attempt, full CI and any opt-in live-tunnel
acceptance evidence are recorded in [PR #64](https://github.com/romankenig/PrettyLisaVPN/pull/64).
Merge/publication is separate; no merchant activation or production deploy is
implied by this change.
