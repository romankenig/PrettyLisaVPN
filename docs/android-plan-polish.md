# Android plan comparison and sign-in polish

## Versions and compatibility

Android 0.25.0 → **0.26.0**, versionCode 47 → 48: substantial subscription UI and
navigation changes. Backend 0.37.0 → **0.38.0**: authenticated guest device list
and revocation are now available. Schema remains **0047_active_user_speed** from develop; no additional schema
change. Windows, Apple, Chrome, dashboard and website versions are unchanged.
Initial base: `990e4de46f5faa7e9e7627e3699f055df039b0bf`; synchronized with
`13dc5039d72146a15e52daa75a9f4702d0d61b5d` after PR #67. Its backend 0.37.0
requires this independent task to use 0.38.0. These changes are not published.

## Behavior and boundaries

- Email is the primary sign-in action. The larger outlined guest action is
  secondary; verbose DEMO/privacy paragraphs are removed. Localized document
  links stay at the bottom of the content area and scroll on short/IME screens.
- Home Upgrade opens subscription for both DEMO and FREE. PREMIUM is the first,
  strongest card with a large price, currency switch, concise benefits and Buy.
  FREE 🕊️ follows with registration for guests; DEMO ⏳ is quieter and explicitly
  states 15 minutes/day, this device, AUTO and full traffic only. All tier names
  are uppercase. Current-plan text/badges remain visible in the comparison.
- Guest Buy closes the guest session through the existing logout/cleanup path,
  opens email OTP and returns to subscription after registration. The session
  ViewModel retains this intent across Activity recreation, not process death.
  FREE registration instead returns to Home with its independent daily allowance.
- Guest pricing uses unauthenticated GET /billing/catalog. It keeps last-known
  public prices in memory or displays 399/499 RUB and 5/7 USD on first failure.
  These display values never authorize a payment. Registered buying still needs
  a live permitted route, fresh overview/revision, server offer and confirmation.
  Disabled checkout has a visible Buy button with an honest unavailable dialog.
  Existing contract amount/currency remain immutable; failed contract loading
  never substitutes a current market price as the agreed amount.
- DEMO may manage its own device and choose enabled connection methods.
  Country AUTO and full traffic are still enforced in client and backend.
  Device revocation invalidates authentication and triggers existing durable VPN
  cleanup. Rejoining retains the device principal and spent quota.
- Reset methods is a small translucent icon beside the current protocol in
  connected/checking/waiting/reconnecting states; absent without that protocol.
  Its existing reset, cleanup and reconnect behavior is unchanged.

## Verification and rollout

Local PostgreSQL/Valkey integration verifies guest list, foreign-device rejection,
own-device revocation, VPN grant removal and quota retention after login. Android
tests cover catalog recovery without credentials, guest payment fences, all plan
states, registration navigation, device/settings access and reset visibility.
Native CI captures Russian sign-in, DEMO Home, all comparison cards, FREE purchase,
double font scale and existing IME/navigation scenarios.

Final product HEAD, build SHA/run/attempt, all workflow/job conclusions and native
artifact evidence are recorded in the PR after verification. Native Android builds
use CI because this workstation has no configured Android SDK/JDK. Backend follow-up:
deploy 0.38.0 before distributing 0.26.0 for guest device management; retain the
existing DEMO identity key and 0046 data. Merge/publication require owner approval.

## Android 0.26.1 — plan copy follow-up

Android **0.26.0 → 0.26.1**, versionCode **48 → 49**: small presentation/copy fix.
Backend 0.38.0, schema 0047, website and other clients are unchanged. Base develop:
`0214867dae715db946f66acde73f6ca7b861c5c3`. No new API or migration is needed.

The shared lock hint reads “недоступно в DEMO” everywhere, with equivalents in all
six locales. PREMIUM emphasizes no time/data quotas, premium servers and all
available VPN locations. FREE shows its daily hour and free-only servers; the
five-device comparison row is omitted without changing that entitlement. Paid
access still ends at the paid deadline; no speed, uptime or priority guarantee is
added. Existing registration/checkout guards, prices and actions are preserved.

Existing native acceptance now also captures the Russian DEMO country menu beside
the plan comparison, including larger font scenarios. Localization, build, lint,
unit tests and API 26/35/36 acceptance run against the current source. Final product
HEAD, actual build SHA/run/attempt, artifacts and complete CI audit belong in the
task PR after verification. No backend follow-up is required. Publication remains
the existing approved-merge/develop pipeline; a PR artifact is not a published APK.
