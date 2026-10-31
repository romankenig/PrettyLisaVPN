# PrettyLisaVPN monitoring dashboard — 0.4.3

Managed client downloads include corresponding engine source/license archives.
Their links appear only when the verified publisher reports matching sources.
Existing binaries remain available until a newer successful develop build is published.

Standalone read-only React dashboard at `/dashboard/` on the main server.
The scheduler, probes, history and acceptance timer run independently of this UI.
No ChatGPT account, Sites runtime or browser polling is required for monitoring.

Build with `npm ci` and `npm run build` in this directory. The `dist/` artifact
contains no credentials. `install.py <dist.tar.gz> <source-sha>` installs it on the
main server and generates a random password on first use. Subsequent installations
preserve that login. Caddy validates the generated route before it is installed.

The deployment Caddyfile imports the optional operator-managed `dashboard/*.caddy`
route. Both assets and `/dashboard/api/availability` require HTTP Basic credentials
over HTTPS. The proxy substitutes a read-only backend monitoring token; that token
and the password hash never enter JavaScript or repository files. The operator's
login is kept in `/opt/prettylisavpn/secrets/dashboard/login.json` (mode 0600).
Keep this directory across releases; do not place it in CI artifacts.

The generic OTP login of VPN customers is unchanged. This password protects only
the administrative monitoring dashboard. Unknown/missing history remains unknown;
the dashboard shows coverage separately from successful known hours.

All displayed timestamps use fixed GMT+3 (`Etc/GMT-3`), independent of browser
timezone. API timestamps and monitoring slots stay UTC.
Click an hour to inspect every stored speed measurement and rating at check time.
Overall/group selection retains per-server detail. Legacy observations have no
rating snapshot; their speeds remain visible and missing values use a dash.

Individual speed/rating/activity charts live inside each server card. Active
connections are hourly bars using the last observation per server/hour, not a
sum of repeated checks. The shared chart contains only the selected servers'
aggregate: arithmetic mean download/upload speed, median rating (mean of the
two middle values for an even count), and summed active connections. Current
summary tiles use the same rules on latest observations. Each server has equal
weight regardless of check frequency. Filters apply before aggregation.
Missing values are omitted, never carried forward or replaced by zero; tooltips
and current tiles report coverage. Partial sums are not complete group totals.
Active totals include only selected FREE and PREMIUM exits, excluding transit
nodes to avoid counting a relay connection twice. Intermediate-only selection
has no client total; its own card still displays transit activity. Hover or focus
a point/bar to see its date/time in GMT+3 and metric value immediately.
See [implementation and verification](../../docs/dashboard-group-metrics.md).

Client downloads use `/dashboard/downloads/android.apk` and
`/dashboard/downloads/windows.exe`, protected by the same password. The catalog
at `/dashboard/downloads/index.json` identifies the latest successfully published
development build of each platform. These files are stored on the main server;
GitHub login and artifact retention do not affect downloads. See
[publication, validation and rollback](../../docs/dashboard-client-downloads.md).
