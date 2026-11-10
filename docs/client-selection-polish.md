# Windows and Android selection / FREE upgrade polish

## Scope and versions

User requested parity on Windows and Android. Windows 0.27.1 → **0.28.0** adds a
previously absent reset-and-reconnect action. Android 0.27.0 / code 50 →
**0.27.1 / code 51** corrects existing lists, quota UX and reset presentation.
Backend **0.40.1**, website **0.5.2**, managed engine **0.6.2** unchanged.
No schema migration, new endpoint, payment activation or new data collection.

## Behavior

- Each catalog ID appears once. Selected services sort by localized name, followed
  by the unselected original top ten in popularity order, then the alphabetical
  remainder. Selecting a top service does not pull an eleventh into the top group.
  Russian exclude mode retains its whitelist category. Other modes retain popular
  classification. Search filters each group; independent drafts still save/cancel.
- FREE explicitly says “after registration”; DEMO “without registration”.
  PREMIUM retains primary placement and its unlimited-access benefits.
- Only a fresh (at most 60 seconds), valid zero usable FREE balance before its UTC
  reset prevents a redundant Connect request and opens Subscription. Reserved
  seconds on another device are usable, not exhausted. Unknown/stale/reset balances
  proceed to authoritative backend admission. API quota rejection ends protocol
  attempts after cleanup. Windows opens Subscription; Android offers Buy PREMIUM.
  Payment still requires explicit user action and a live provider capability.
- The subtle text action beside the current protocol says “reset settings”.
  It resets learned method preference, not country, split traffic or allowed
  methods. Windows waits for cleanup, fences reconnect against account changes,
  disposal and explicit cancellation. Android reuses its existing reset controller.
  The control is absent without a displayed current protocol.
- Android's new internal FREE_LIMIT UI state maps to existing support code ACCESS;
  no support-v2 schema incompatibility is introduced.

## Validation and release evidence

Local Windows checks: TypeScript, ESLint and all 376 frontend tests passed before
the initial push. Tests cover grouping/search-independent order, duplicate IDs,
quota freshness/reservations/UTC reset, Connect routing, method preference reset,
cleanup failure and cancellation/account-change/disposal races.
Android unit coverage includes quota parsing, terminal rejection and support
compatibility, grouping and freshness. The host has no configured Android JDK/SDK;
Gradle debug/release builds, unit tests, lint and installed-APK acceptance run in CI.

Current-source native Windows review includes unique service rows, exhausted FREE
→ PREMIUM, registration labels, and a synthetic successful protocol/reset scenario
in addition to all timed failures/cancellation. Android installed-APK scenarios
cover the same cards, reset label and exhausted FREE Connect without VPN/payment.
These are native UI/fixture checks, not new live-network tunnel verification.

The task PR records final product HEAD, every push/pull_request workflow and job,
actual build SHA/run/attempt and native artifacts. PR temporary merge builds are
distinguished from source HEAD; no historical installer/APK is used for review.
Merge/publication requires the owner's separate instruction. After authorized
merge, verify develop workflows, permanent download catalog and installer/APK hashes.
No additional backend rollout is required beyond the already live 0.40.1 API.
