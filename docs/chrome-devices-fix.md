# Chrome device list and connection feedback fixes — 0.3.2

User report: 2026-11-15. Opening Devices with a DEMO account produced
`Cannot read properties of undefined (reading 'map')` in popup.html. Follow-up:
`proxy_network_error` appeared despite working traffic, and the DEMO registration
hint did not say that only location selection requires registration.
Baseline: `a8ea1bb2` (develop after PR #87).

Chrome **0.3.1 → 0.3.2** is a PATCH for an existing screen. Backend **0.42.0**,
the public website and all other client versions remain unchanged. No migration,
endpoint, entitlement or proxy configuration change; existing backend versions
remain compatible.

## Root cause and correction

`GET /devices` has always returned a top-level `list[DeviceResponse]`, including
for DEMO. The popup incorrectly read `response.devices` both when entering the
screen and after revoking a device. That assigned undefined to React state, and
the following render called `.map()` on it.

The installed-browser fixture also used the incorrect object wrapper, hiding
the mismatch. Correcting that fixture first reproduced the exact reported error
against the unmodified 0.3.1 client. This is not a DEMO access restriction.

- A small parser at the worker/API boundary accepts the real array, validates
  fields used by the screen and returns only the client device model.
- Nullable (or omitted legacy) last_login_at becomes null; an empty list is valid.
  Invalid payloads produce the existing handled INVALID_RESPONSE error rather
  than entering React state or being silently treated as an empty account.
- Initial load and post-revocation refresh use Device[] directly. Stale cards
  are cleared before loading; errors leave navigation available for another try.
- Revoking the current device retains the existing confirmed cleanup/sign-out
  behavior and avoids another authenticated list request after session removal.
  Other-device revocation reloads and displays the returned list.

## Proxy feedback and location hint

The old onProxyError listener unconditionally changed the entire connection to
FAILED. Chrome's event reports proxy transaction errors; even its fatal flag
describes a transaction, not the complete lease. See the
[official API contract](https://developer.chrome.com/docs/extensions/reference/api/proxy#event-onProxyError).
The screenshot alone does not identify the network cause of that transaction.

Events now queue a check of actual proxy/privacy ownership and the existing
authenticated end-to-end probe. A matching exit IP keeps CONNECTED without
reapplying settings or restarting the lease. A failed probe, wrong IP, lost
ownership or expired lease still displays an error and clears the displayed IP.
No event is dismissed based on fatal=false; proxy policy and the lack of DIRECT
fallback are unchanged. An in-flight check coalesces further events, including
errors from its own probe. Disconnect cancellation prevents stale error feedback.
Event descriptions, URLs and browsing destinations are never inspected or stored.

The six-language DEMO hint now explicitly names location selection. Autopilot
remains selected and Connect enabled; the existing registration transition is
unchanged.

## Verification and delivery evidence

Unit tests cover the actual list, guest null login time, optional legacy time,
empty results, malformed payloads/rows, auth headers and recovery after an error.
Installed Chromium checks DEMO and registered lists, current-device marking,
missing login time, malformed/503/empty responses and recovery, another-device
revocation/refresh, and current-device exit without a post-logout list request.
Every reopened page is observed for uncaught exceptions. Controller and worker
tests cover healthy rechecks, real failures and recovery, event coalescing,
disconnected/provisioning states and cancellation during a probe. Installed UI
checks the location hint, AUTO selection and enabled DEMO Connect button.

The screenshot fixture follows backend/devices/router.py. Fixture browser tests
do not establish live server behavior; any separate real DEMO check must record
its exact source/build identity and cleanup of the owned synthetic account.
Final product SHA, actual CI SHA/run/attempt, all jobs and artifacts are recorded
in the task PR. Commit/push alone does not publish this new ZIP or merge the PR.
The existing deferred enable-toggle/puzzle-menu diagnosis remains separate in
[the Chrome handoff](chrome-ui-demo.md).
