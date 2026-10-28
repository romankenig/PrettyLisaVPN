# Dashboard downloads and GMT+3 — 2026-10-28

Dashboard 0.2.0 → 0.3.0 (new capability). Android remains 0.14.0/code 25,
Windows 0.17.0. Backend 0.20.0 → 0.21.0 adds durable rating history (migration 0033).
No VPN transport, entitlement or client behavior changes. All frontend dates use fixed GMT+3, including midnight rollover;
API/DB timestamps, monitoring slots and daily Free accounting remain UTC.

## Historical measurements

Download/upload speed already belongs to each PostgreSQL fleet observation JSON.
Migration 0033 adds nullable `quality` (0–100). The main-server worker calculates it
once when finishing a check, using the same rating function, preceding 24 hours,
capacity and configured weights/targets that determine current country ranking.
The observation and score commit in the same fenced transaction. Current ranking
still reflects current health and load; a stored historical rating never changes
with later configuration or capacity edits. No fabricated backfill: old ratings
are null while their original speed measurements remain usable.

The existing authenticated availability response adds `history[].measurements[]`
with check timestamp, status/mode/code, down/up Mbps, connection ms, active count
and nullable rating. No new backend endpoint or network probe is introduced.
Selecting an hour in the overall/group timeline shows individual checks from the
selected servers; a server-row hour scopes the detail to that server. All checks
within the hour are retained, not averaged into a fictional single measurement.
The existing seven-day display/eight-day observation retention remains unchanged.
No peer identities, destinations or browsing activity are stored.

The chart switches between speed (download/solid, upload/dashed) and rating. Each
server retains its own series; every point is an actual observation. Missing values
and gaps over 75 minutes break lines. Zero remains zero, not missing. Selecting a
point opens that server's hourly measurements; group/server filters apply to both
chart and details. No fabricated pre-upgrade rating series is generated.

## Rating parameters

The operator changed default and existing node capacity to **20** and the speed
target to **30 Mbps**. This changes admission/rating, not network traffic shaping.
The existing admin PATCH accepts optional validated capacity; omitted capacity
preserves the previous value. Lowering it does not revoke existing sessions.

`R = round(100 × (0.50 × S + 0.20 × L + 0.15 × C + 0.15 × V))`:

- `S`: weighted healthy-check fraction over 24 hours, UNKNOWN excluded, weight
  `2^(-age_hours/6)`; DEGRADED/FAILED count as non-success.
- `L = max(0, 1 - active_connections/capacity)`, now capacity 20 per node.
- `C = min(1, 1000/max(1, connection_ms))`.
- `V = min(1, min(download_mbps, upload_mbps)/30)`.

Connection and speed come from the last successful full synthetic observation
within that window; absent measurements contribute zero. Latest FAILED/UNKNOWN,
unconfirmed cleanup, no observation within 75 minutes, or an unready method means
rating zero/unavailable. Full capacity makes a node unavailable without forcing
its numeric quality to zero. Country score is capacity-weighted over eligible
exit nodes (INTERMEDIATE excluded; Free sees FREE only). AUTO uses the best
available country. These weights are unchanged; the 30 Mbps target is configurable
in the durable main-server fleet environment. Historical ratings retain parameters
effective at their check time, even after later changes.

## Downloads

- Dashboard: https://api.prettylisavpn.com/dashboard/
- Android: https://api.prettylisavpn.com/dashboard/downloads/android.apk
- Windows: https://api.prettylisavpn.com/dashboard/downloads/windows.exe
- Metadata: https://api.prettylisavpn.com/dashboard/downloads/index.json

All routes require the existing dashboard login/password over HTTPS. Downloads
are development builds: one Android debug APK installed over the existing app,
and the Windows development EXE. They do not require GitHub login. Other platforms
have no current binaries and are not shown. No release tags or public releases
are created. A failed catalog refresh is shown separately from fleet availability.

## Automatic publication

Only successful `push` builds on `develop` call `client-download-publish.yml`.
Android waits for build/unit/lint/packaging and all API 26/35/36 emulator jobs.
Windows waits for its build, UI/unit tests, Rust tests and Clippy. PR builds and
manual workflow dispatches never publish. The reusable job downloads the artifact
from its own parent run, validates build identity, and transfers it over verified
SSH using existing development-environment secrets. No repository token is stored
on the server. Runtime services and hourly monitoring remain on the main server.

`infra/deployment/publish_client.py` validates platform, version, exact source SHA,
run/attempt, size, format signature and SHA256. It rejects PR identities. A shared
Linux file lock serializes updates across platforms. Immutable releases are stored
at `/opt/prettylisavpn/secrets/dashboard/downloads/releases/<platform>/<run>-<attempt>`.
Snapshots contain the catalog and links to both platform binaries. One atomic
`current` symlink replacement publishes a complete snapshot. Readers never receive
half-copied files; publishing one platform preserves the other. Interrupted writes
leave the previous pointer usable. Snapshots and binaries are retained for rollback.

“Latest” means the newest successfully published development version, ordered by
SemVer, then CI run and attempt. A late older build cannot replace it. Same identity
is idempotent; conflicting bytes/source are rejected. A failed build leaves the last
successful download available. Cache-Control is private/no-store; the browser gets
attachments directly from Caddy, outside the backend API. Catalog URLs are fixed
in UI code; metadata cannot inject an external download destination.

## Installation and rollback

Install the exact successful dashboard artifact using existing `install.py` and
its source SHA; preserve `login.json`. The new Caddy template adds downloads before
the static dashboard handler. Validate and reload Caddy after updating this route.
The durable dashboard directory is already mounted read-only in Caddy and survives
backend deployment. Authentication protects UI, API, catalog and binaries equally.

Initial binaries can be bootstrapped with this publisher from fully successful
develop runs and their exact build identity. After merge, CI owns future updates.
For a deliberate download rollback, pause publication, take the same `publish.lock`,
and atomically point `current` to a retained known-good snapshot; do not edit catalog
fields or overwrite immutable binaries. Resume only with an appropriate fixed build.
To revert the dashboard UI, restore its previous `site` symlink and Caddy route,
validate/reload. Migration 0033 is additive and older backend code can run with it
left in place. Downgrading 0033 removes only the newly stored ratings; back up this
history first if an explicit schema rollback is needed. Running VPN sessions and
the 0031/0032 relay/quota schema are unchanged.

## Verification and handoff

- Unit tests: invalid identity/hash/size, concurrent platform publication, stale
  runs, idempotency, conflicts and interrupted publication retaining the old snapshot.
- Docker/Caddy HTTP checks: anonymous/wrong-password 401, authenticated UI/API/catalog
  and APK/EXE 200, no-store/attachment headers, missing file 404, no directory listing.
- Frontend tests: fixed GMT+3 in winter/summer and at midnight; incomplete/invalid
  catalogs, fixed links, individual hourly measurements and node/group filtering.
  TypeScript and production build must pass. PostgreSQL integration verifies that
  scores/speeds persist, changed weights do not rewrite history, and legacy null
  scores remain null. Alembic upgrade/check and backend lint/types must pass.
- Deployment acceptance: compare downloaded binary hashes with catalog and original
  CI artifacts; confirm anonymous access is denied; inspect desktop/mobile layout.
- Record exact product HEAD, actual build SHA/run/attempt, artifacts, deployment and
  all final CI outcomes in the task PR. A branch artifact does not prove publication.
  The first automatic develop publication after merge is the final CI acceptance.

Bootstrap candidates (must retain their original build identities): develop
`c1f9b18bcebc43aec96abc4f43a21eecb5b3f4a7`, Android run 40687449383/1,
Windows run 40687449446/1. Both workflows completed successfully. These are not
builds of the new dashboard commit. See the task PR for final published identities.

## Active device history (same dashboard 0.3.0 task)

The chart switch also includes active devices, using each stored observation's
active_connections. Counts are per-node VPN connections at check time, not
registered devices or a globally deduplicated count. A relay connection appears
on both participating nodes. Integer zero is retained, missing values and gaps
are not filled, and server/group filters and point-to-hour details apply equally.
Final client patches in this PR are Android 0.14.2 and Windows 0.17.2; backend
0.21.1 includes quota/cleanup migration 0034 after the history migration 0033.
See [quota/cleanup handoff](free-quota-cleanup.md).
