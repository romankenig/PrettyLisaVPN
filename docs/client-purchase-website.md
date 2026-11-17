# Website-owned client checkout

## Scope and compatibility

Windows **0.31.0 → 0.31.1** and Android **0.30.0 → 0.30.1**, versionCode **59 → 60**
(PATCH): correct existing purchase navigation. Backend **0.53.0**, website **0.7.0**,
iOS **0.6.0**, macOS **0.5.0**, Chrome **0.5.0** and managed engine are unchanged.
No schema migration or API contract change. The base is develop
`af15f29e96a674e43a6900b752442dbca220bb69`.

Buy, renew and subscription management always open the website, including when
billing is DISABLED or SANDBOX. Native clients show account facts and display
prices, but no longer select payment methods, confirm contracts, start/cancel
payments or open provider redirects. The website owns those decisions and the
currently published unavailable-payment page. Existing pending operation reads
and wire methods are retained for compatibility; timeout never creates a charge.

Registered accounts use the existing authenticated `POST /billing/portal` and
validated HTTPS `/account/#handoff=…` destination. The opaque single-use handoff
is not logged or placed in review artifacts. Windows refreshes on browser return.
Android retains its existing refresh and lifecycle behavior. Errors are retryable;
late responses from a previous account/session cannot open its portal.

DEMO Buy opens exactly `https://prettylisavpn.com/account/` without a token or
portal API call, preserving the guest session and tunnel. Website email login
establishes a separate registered account. The explicit FREE registration action
still performs native cleanup before OTP. Identity derivation, reinstall quota,
UTC budgets and FREE/DEMO separation are unchanged. This supersedes the old Buy
registration transition in the Android plan and Windows parity documents.

iOS/macOS and Chrome already use the backend portal and need no release for this
task. Linux/TV have no shipping account screens. Existing Windows/Android users
must install this update once; later website payment UX changes require no app
update. Connecting the real provider still requires backend/merchant configuration;
the website's promised notification email is separate work, not implemented here.

## Validation and publication handoff

Windows checks cover TypeScript, ESLint, production build, 390 unit/component
tests, provider-mode-independent navigation, paid management, pending recovery,
failed/stale handoffs, exact guest URL validation and DEMO session preservation.
Native review captures the current Tauri window and checks that every payment
action opens the account destination without a native operation or confirmation.
Android instrumentation intercepts the real browser intent and verifies the
DEMO, Free, paid, disabled/sandbox/live and failed-retry paths without a charge.
Localization checks cover all six languages.

Local Rust tests require the packaged managed engine, and local Android checks
require JDK/SDK build outputs; the complete build, native tests/lint and emulator
checks run in required CI. Review screenshots are synthetic fixtures, not live
payment or VPN acceptance. No real payment or notification email is sent.

After the final push, the task PR records the verified product SHA, temporary PR
merge/build SHA, every workflow/job result, original run/attempt and artifacts.
After the owner's authorized merge, verify both shared client publishers and the
stable dashboard/public downloads against the exact develop build, including
versions, SHA-256 and matching managed sources. PR evidence is updated without
another source commit; this document alone is not a deployment claim.
