# Android subscription layout — 2026-11-07

Android **0.22.1/code 43 → 0.23.0/code 44**. MINOR: substantial subscription-screen
redesign and accessible pull-to-refresh. Other component versions are unchanged;
backend API and schema remain unchanged. This task follows merged PR #63 and does
not replace its price-resilience publication. The owner's subsequent, independent
[optional-location correction](android-optional-location.md) advances the final
branch to Android 0.23.1/code 45 without another subscription-task bump.

The live subscription screen separates access, monthly price, payment details and
management into cards. Prices use localized separators, preserve actual cents and
omit unnecessary decimal zeros. The monthly amount is prominent; two compact dark
purple currency controls sit immediately beside a new-offer/reference price with
48dp touch targets. At large font scales the layout stacks; the amount fits its
available width using Compose text autosizing (32–48sp, still respecting the system
font scale) instead of clipping or splitting the currency onto another line.

An existing Premium contract displays its own immutable amount and locked currency,
never the acquisition offer. Legacy unconfirmed contract prices remain unknown.
Free/Platinum and canceled contracts requiring a new subscription show current API
offers. Manually assigned Platinum explicitly has no recurring payment; absence of
a contract is not rendered as “current price unavailable”. The approved fallback
399 RUB/5 USD (499/7 reference) remains display-only after an overview outage.

Unavailable payment routes and provider actions are omitted. A usable route is
selected automatically; only provider-authorized routes for the selected currency
are shown. Pending operations, stale data, unknown outcomes, frozen revision,
idempotent retries and backend action guards retain their existing behavior.

There is no bottom refresh button. Pull down at the top refreshes billing with the
existing PhoneScreen indicator; pulling at the bottom does not refresh. An
accessibility custom action provides the same refresh without a gesture. Existing
data stays visible while refreshing and mutations remain disabled until ready.

Management is last: “change subscription” uses the existing authenticated,
single-use billing portal. Available payment-method replacement retains its native
confirmation. “delete subscription” is a red CANCEL action, requires confirmation,
and preserves paid access until the existing deadline; it does not delete the
account or revoke manually assigned Platinum. No cancellation is invented when
the backend does not authorize it. Resume from the browser reloads billing.

All six Android catalogs are updated. Eight retired Android labels are removed;
two still used by Apple are copied verbatim to its AppleStrings source catalog,
with a synchronization assertion. Generated Apple UI resources and versions remain
unchanged. Tests cover currency/cent formatting,
contract-price preservation, allowed-route visibility, no payment authority from
reference amounts, pull-to-refresh, Platinum, cancellation confirmation and large
text. Subscription work brings AccountScreensTest to 20 methods; the subsequent
location correction adds one more (21 total), with the exact CI gate updated. Native
screenshots include Russian RUB/USD/management cards, a contract price, cancellation
confirmation and 2x text. Final source/build SHAs, every CI run/attempt and screenshots
belong in the task PR. New source is not yet merged or published; payments remain
disabled until the separately authorized merchant setup.

CI also exposed pre-existing wall-clock races in ServerConnectionTest: its 1 ms
poll could run again before the collector resumed on a busy runner, producing
two probes instead of one or three instead of two. All polling tests now use the
existing coroutine virtual clock and retain their exact probe-count, recovery,
offline and cancellation assertions. Runtime polling is unchanged; these test-only
corrections do not add a version bump.
