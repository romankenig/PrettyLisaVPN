# Android split-traffic location fallback

Task baseline: develop `f9e69f389124740d83210d650364083c5777a8d6`.
Android 0.27.2/code52 → 0.27.3/code53 (PATCH: missing Home metadata).
Windows 0.28.1, backend 0.40.1 and managed engines are unchanged.
The branch also incorporates develop `f400752d6cc0692aacd44ed158f4a0135e88c10a`
(independent website 0.5.3), preserving both changelog entries.
No API/schema change, migration, dependency or pending backend integration.

## Behavior

The owner's screenshot showed connected WireGuard+ with “selected” traffic but
no location in that card. SecondaryLocation returned immediately when the public
metadata provider returned null, hiding the divider and entire location row.

Connected include/exclude modes now keep the row visible. “Selected” falls back
to the active adapter's allocated session country and first expected egress IP
from the existing backend response. This handles AUTO and relay sessions without
guessing from the country picker or the transport endpoint. Both WireGuard and
managed adapters expose only this small display snapshot; credentials/configuration
are never copied to UI state. Health checks continue to verify the tunnel independently.

“Except selected” falls back to the last direct public location, retained only in
memory. The ordinary Home lookup updates that cache only when no VPN is active
before/after its request; an explicitly physical-network-bound lookup can also
update it. A VPN observation cannot replace the direct fallback. After a network
change that cached location can be old, so fallback data is labelled “expected”.
If no direct observation exists yet, the visible row says determining/unavailable
and keeps retrying; it never borrows the VPN's country for excluded services.

Fresh observations take precedence over fallback. IP-only observations retain
their measured address and can use the expected country, with the expected label.
No city is invented, and a cached city from a different IP is not copied. Failed
periodic refreshes retain the successful observation for that same session/mode.
Changing mode/session, disconnecting or reconnecting discards the VPN observation;
all-traffic/disconnected states continue to hide the secondary row.
The labels are translated in all six catalogs.

## Verification and delivery

JVM regression tests cover AUTO allocation, include/exclude source separation,
missing fallback, partial metadata, real-observation precedence, changed sessions,
and controller health/disconnect propagation. Native instrumentation captures
expected include/exclude locations, successful lookup recovery and unavailable
metadata while checking all/disconnected hiding.

Local validation: six-catalog checker and diff review. Source isolation requires
built APK metadata and therefore runs in CI. No local
JDK/Android SDK is installed; compilation, JVM tests, debug/release lint and native
API 26/35/36 acceptance run through the existing Android Actions workflow.
Exact final product HEAD, actual push/PR merge build SHA, run/attempt, APK and
screenshots are recorded in the task PR after completion; this document alone
does not claim those checks have passed. No live handset/tunnel acceptance or
publication is implied. Rollback uses the previous compatible Android artifact.
