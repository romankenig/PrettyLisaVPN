# Protection UI and daily product analytics

## Versions and compatibility

Windows 0.23.0 → 0.24.0, Android 0.19.0/code36 → 0.20.0/code37,
backend 0.27.0 → 0.28.0, dashboard 0.4.3 → 0.5.0: compatible new UI/features.
Managed engines 0.5.1 → 0.5.2: fixed direct-egress observation for Windows.
Existing traffic rules, authentication, subscriptions and VPN lease contracts
remain compatible. One Android APK; Windows remains an installed application.

## Client behavior

The Home heading/dropdown share a larger font. The turquoise picker button opens
only the selected mode. Each mode preserves its own presets and manual masks.
Custom-mask form is explicit, near the top, with an example placeholder. Top-ten
membership still comes from mode/language/popularity; each group orders saved
selected names alphabetically before other names. Draft toggles keep positions
until Save/reopen. Saving and changing mode stop VPN before committing rules.

Exclude's right location observes physical egress. Android requests an INTERNET,
NOT_VPN Network and binds DNS and fresh sockets to it, without changing process
routing. CHANGE_NETWORK_STATE is a normal permission without a runtime dialog.
Windows sends a fixed private service command to the current engine's protected
direct outbound. Fixed HTTPS providers only, no arbitrary renderer URLs, account
headers, traffic logging or cached-IP fallback. A disconnected/changed runtime
invalidates the observation. Ordinary ifconfig.me traffic still routes through
VPN, preserving the existing diagnostic rule. Include uses VPN-bound ifconfig;
all mode displays only the existing left location.

## Metric definitions and historical limits

Report calendar is GMT+3, while stored timestamps are UTC. Range: today minus
two calendar months through yesterday, including both ends. The first MAU reads
29 additional days. Today never appears as a point.

- DAU/WAU/MAU: distinct accounts with successful authenticated activity in 1/7/30
  inclusive calendar days ending at the point. Login, token refresh, logout,
  authenticated requests and VPN heartbeat count. Multiple devices count once.
- Tariff: effective tariff at the latest recorded activity within that window.
  Each account belongs to one category, so Free + Premium + Platinum + Unknown
  equals the total. Later upgrades never relabel older activity. Expired paid
  subscriptions record Free according to the existing entitlement rules.
- Historical evidence: successful auth events and legacy VPN creation/verified
  heartbeat timestamps only. Legacy sessions provide their creation plan;
  modern free leases prove Free at creation, paid historical leases cannot
  distinguish Premium/Platinum. Other unknown tariffs stay Unknown. Never infer
  activity through delayed cleanup or count legacy ACTIVE as VPN success.
- Before the earliest available activity evidence: null (gap), not zero. Until
  a whole window has daily capture coverage, it is marked incomplete. UI explains
  partial history. Migration-day collection becomes complete on the next day.
- New accounts: registrations by creation date, not repeat logins.
- Verified VPN sessions: customer leases by verified_at date, not peer grants.
- Connection success: verified / settled attempts by creation-date cohort.
  Each fallback candidate is an attempt; pending attempts are excluded. This is
  attempt success, not a final user-journey success rate.
- DAU/MAU: daily share of monthly active audience; null if denominator is zero.
  This is regularity, not cohort retention.

Reserved test domains example.com/net/org and .test/.invalid/.example are excluded.
Current blocked status does not erase legitimate historical activity. No browsing
history, DNS query, destination, packet content or raw credentials enter analytics.
The HTTP dashboard API returns aggregates, never account IDs or email addresses.

## Storage, scheduling and deployment

Migration 0041 adds daily account/plan observations, aggregate snapshots and a
collection-start singleton. Daily rows deduplicate devices; newer timestamps win.
Capture uses a separate bounded best-effort transaction so analytics failure
cannot invalidate authentication. Retention is 180 days for observations/reports.

The main server's Compose `product-analytics` worker uses the same backend image.
It checks for a missing completed-day report every minute, takes a PostgreSQL
advisory lock, publishes one complete snapshot transactionally, and catches up
after restart. It does not depend on Codex or an open browser. API GET only reads
the last successful snapshot; frontend refresh cannot trigger a recalculation.

`GET /admin/monitoring/product-analytics` uses existing fleet monitor/admin bearer
authorization. Caddy exposes only the fixed GET path under existing dashboard
Basic auth, injecting the monitor token server-side. Page:
`/dashboard/product-analytics`; API: `/dashboard/api/product-analytics`.
Existing static files, monitoring and missing-download 404 behavior remain.
Browser displays generation/next-update times, last completed date and delayed
updates, with accessible keyboard/pointer tooltips and formulas below charts.

Deploy backend/migration/worker first, then dashboard built from verified source
using `sites/fleet-dashboard/install.py` and validated Caddy reload. Keep existing
login/password; never publish secrets in artifacts. Verify private 401/authorized
200, snapshot through yesterday, worker health, original dashboard and downloads.

## Rollback and evidence

Rollback clients to retained installers/APKs, dashboard to its previous immutable
site directory, backend to its previous image; stop the new analytics worker when
rolling backend back. Additive tables can remain for forward recovery. A downgrade
deletes analytics history and is not required for ordinary rollback.

Base source: develop `1cc42bc0470628537ea0bff6a70c51d27bb92910`.
Current implementation is not a claim of deployed/native acceptance. The task PR
records final product HEAD, actual build SHA/run/attempt, screenshot/live routing
proof, all Actions/jobs/check suites, publication identities and deployment checks.
Do not reuse earlier client binaries as evidence for these UI/location changes.
