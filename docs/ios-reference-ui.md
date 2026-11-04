# iOS reference UI — 0.2.0

The owner requested the supplied Android screenshots on iOS: purple content,
Christalle top/bottom chrome, Mercury rounded cards, Viking actions, Rubik type,
and Home / Settings / About tabs. iOS changes **0.1.0 → 0.2.0** for this substantial
UI/navigation task. macOS stays 0.1.0; backend, engine, Android and Windows versions
are unchanged. The website task is independent.

`IOSViews.swift` provides an iOS-only shell over the existing AppModel and VPN
coordinator. The canonical lock asset and licensed Rubik font are copied from the
existing Windows assets into iOS-only resources. Fixed brand colors match the
reference in both system appearances; dynamic text sizes and scrolling remain.
macOS retains its sidebar, theme selector and original screens.

## Screens and transitions

- Home: account/email/plan/devices first, then country and one connect/disconnect
  action, actual connection state/method, verified country/IP when available.
  A Free account also retains its real remaining daily time. Pull to refresh uses
  the existing account API. No screenshot account, IP or connected state is baked in.
- Home protection card displays All. Its info sheet explains IPv4/IPv6 and Apple
  policy. Include/exclude modes from the Android screenshot are not presented as
  working iOS choices; this visual task does not implement split routing.
- Settings opens subscription, devices or advanced settings; logout uses the
  existing confirmation and server cleanup. Advanced settings retain connection
  methods and language. The top language menu supports all six existing locales.
- Devices shows current-device badge, status, UUID, added/last-login dates and
  revoke confirmation. Missing last-login remains unavailable; fixtures cannot revoke.
- About shows actual frontend and GET /version data, connection FAQ with Home
  action, support form entry, attribution, service link and license/policy details.
- Nested pages show Back and the version footer; the three tabs remain on the
  top-level pages. Messages are still reachable from Home when present.
- OTP/auth guard, Keychain, billing read-only contract, support delivery,
  confirmation dialogs and real tunnel acceptance gate are preserved.

## Verification and handoff

Local: resource synchronization, structural/localization/entitlement checks,
whitespace/diff review. Apple CI compiles all four SDK targets, runs the 18 core
tests plus native macOS regression tests and iOS navigation/connection/UI tests on
two iPhones in both appearances. The new tests capture Home, Settings, Devices and
About, verify fixture connection cannot become a real VPN, and exercise back,
advanced-method and support navigation. Debug banners stay visible in captures.

The task PR records the exact product HEAD, build SHA/run/attempt, final CI audit
and native screenshot artifacts after completion; earlier 0.1.0 screenshots are
not evidence for 0.2.0. No backend follow-up is needed for this visual change.

Real iPhone and signed macOS tunnel acceptance remains separate and unconfirmed:
see [Apple VPN handoff](apple-vpn-handoff.md) and [signing/setup](../apps/apple/README.md).
No Apple Team, provisioning profile or physical iPhone is available in this
Windows workspace or the unsigned CI environment. Simulator UI success does not
verify tunneling, egress IP, DNS, disconnection or network-change recovery.
