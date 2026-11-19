# Test rollback to the Android 0.30.2 product baseline

Owner request, 2026-11-19: restore all clients and backend to the project state
corresponding to Android 0.30.2, in code and the **test environment only**.
Production and `main` are outside this rollback.

## Source and versions

Baseline: `b90d9685` (PR #110), the last develop product tree before PR #109.
Its application sources match the Android 0.30.2 shared-FAQ release in `84466c97`;
the intervening commits document Austria/Germany node enrollment only.
PR #111 itself was documentation and contained Android 0.30.3, not 0.32.0.

| Component | Before rollback | Restored version |
| --- | --- | --- |
| Android | 0.30.5 / code 64 | 0.30.2 / code 61 |
| Windows | 0.31.5 | 0.31.2 |
| Backend | 0.54.3 | 0.53.0 |
| Chrome Extension | 0.5.3 | 0.5.1 |
| iOS | 0.6.3 | 0.6.1 |
| macOS | 0.5.3 | 0.5.1 |
| Website | 0.7.2 | 0.7.1 |

Fleet dashboard 0.18.0, managed engine and database schema `0053_analytics_plans`
are unchanged. No database downgrade, snapshot restore, node de-enrollment or
payment action is part of this rollback. Existing accounts and records remain.

## Deliberate environment differences

Application/UI/business behavior and its regression tests return to the baseline.
Later locked-Premium country presentation, direct checkout/provider changes and
Windows/Android outage/disconnect changes are reverted.

The current test/production isolation remains: build-selected API/website origins,
CSRF/native handoff origin validation, environment regression tests and deployment
configuration. Test builds use `api.test.prettylisavpn.com` and
`test.prettylisavpn.com`. Current CI, verified publishers, durable deployment config,
private local download catalogs and production protections remain in place.
Do not restore the retired development deployment or route test clients to production.

These are new test-channel builds of the historical product baseline with the
environment adapter, not the original production artifacts. Preserve the actual
new source SHA/run/attempt and checksums; never relabel an older artifact. The owner
explicitly selected historical versions for this rollback. Existing immutable
artifacts/tags are retained. Android's lower versionCode can require an explicit
downgrade installation; automatic updates and removal of user app data are not done.

## Verification and operational handoff

Run existing formatting, lint, type checks and component regression suites; CI
provides Linux integration/database/container tests, Android emulator acceptance,
Apple native builds and Windows native UI captures for the actual rollback source.
After the verified develop integration, check all push/reusable jobs, test backend
health/readiness/version, website identity and each private download's version,
source/run/attempt, API origin and digest. Record final evidence in the task PR so
documentation-only follow-ups do not cause an endless build loop.

Keep test billing, client/managed VPN and fleet workers disabled as required by
[test environment isolation](test-environment.md). Real test VPN acceptance still
requires separate test nodes. Production API, website and installers remain unchanged.
Historical handoffs for the reverted features describe earlier work, not the current
test baseline. [Windows navigation](windows-navigation.md) reflects the restored UI.

Rollback of this operation means restoring the retained pre-rollback test application,
website and download pointers, or reverting this source commit through verified CI;
it does not require changing persistent business data.
