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
were added in 0.6.0 as documented below. No release tags or public releases
are created. A failed catalog refresh is shown separately from fleet availability.

## Automatic publication

Only successful `push` builds on `develop` call `client-download-publish.yml`.
Android waits for build/unit/lint/packaging and all API 26/35/36 emulator jobs.
Windows waits for its build, UI/unit tests, Rust tests and Clippy. PR builds and
manual workflow dispatches never publish. The reusable job downloads the artifact
from its own parent run, validates build identity, and transfers it over verified
SSH using existing development-environment secrets. No repository token is stored
on the server. Runtime services and hourly monitoring remain on the main server.

The SSH deployment user runs `publish_client_container.sh` with its existing
Docker permission. The helper uses the running backend's immutable local image
ID, with networking disabled and a read-only root filesystem. Capabilities are
dropped except DAC_READ_SEARCH, needed to read the deployment user's private
incoming files. Only the incoming build (read-only) and download store are mounted.
Root inside this short-lived container can update the root-owned downloads;
dashboard credentials remain inaccessible and root SSH is not added to CI.
`fleet.env` must remain owned by the deployment user with mode 0600, like
`deployment.env`, because Compose reads it before starting containers.

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

Publication follow-up: product versions unchanged (backend 0.21.1, Android
0.14.2, Windows 0.17.2, dashboard 0.3.0). The first develop deployment at
`422946f530d7abe5de47b3ede28732fa4532c069` exposed a root-owned `fleet.env`
and a publisher launched directly as the non-root SSH user. Correct the env
ownership and use the restricted container helper. Retain those failed runs
as evidence; final successful source/build/run/attempt identities belong in
the follow-up PR after deployment and publication have actually completed.

## Chrome and Apple downloads — 2026-11-05

Dashboard **0.5.0 → 0.6.0** adds three platforms. Client versions remain
Chrome 0.1.0, iOS 0.1.0, macOS 0.1.0 on the develop baseline; backend 0.34.0,
Windows 0.25.2 and Android 0.21.2 are unchanged. The separate iOS 0.2.0 PR
is not a published develop build and must not be silently substituted.
No API/database/authentication change and no public website change.

| Platform | Permanent authenticated download | Installation |
| --- | --- | --- |
| Chrome Extension | `/dashboard/downloads/chrome-extension.zip` | Extract, enable developer mode at `chrome://extensions`, load the extracted directory. Browser-only HTTPS proxy. |
| iOS | `/dashboard/downloads/ios-unsigned.zip` | Unsigned device app; requires an Apple signature and provisioning profile. Not directly installable from Safari, App Store or TestFlight. |
| macOS | `/dashboard/downloads/macos-unsigned.zip` | Unsigned Release app; real VPN requires appropriate Apple signing and Network Extension provisioning. |

Both Apple downloads have corresponding engine source/license archives at
`/dashboard/downloads/{ios,macos}-sources.tar.gz`. Neither Apple download claims
real-device VPN acceptance. The initial 0.6.0 links excluded Simulator and ad-hoc
UI fixture builds; 0.6.1 adds a distinct Simulator companion as documented below.
The UI reads version/date/size from the shared catalog every minute. Buttons
only appear for validated entries with the expected package kind, and all URLs
remain fixed in code. Existing Android/Windows schema-1 entries stay compatible.

`prepare_client_download.py` normalizes artifacts from their own CI run into the
existing publisher contract. Chrome carries its original build identity inside
the ZIP; Apple preserves exact Release ZIP bytes and original run provenance,
adds a source SHA marker to the matching corresponding-source archive, and reads
the version from the actual app plist rather than hardcoded packaging metadata.
Packaging is deterministic so repeating the same original artifact is idempotent.
The publisher checks MV3/app structure, device SDK (rejecting Simulator), version,
size, SHA256, original SHA/run/attempt and Apple source/license presence.

Successful Chrome build/lint/test/browser checks and both Apple jobs gate the
shared publisher. Only a `push` to `develop` publishes; PR/manual/failed builds
do not. Packaging/publisher/reusable-workflow changes trigger both platform CIs.
The existing lock and atomic snapshot preserve all five platforms. No release
tag, Apple signing identity, store publication or extra server token is introduced.

Initial bootstrap candidates are the latest successful develop push artifacts:
Chrome `0c70d8185664d8ca80c4513205acb3b3c0e8e1a6`, run `41984959319/1`;
Apple `05d945dbd5da35f1c85523d00b4ab57415882a3c`, run `41822292829/1`.
Check every job and the artifact's original identity before using them. These
are existing clients, not builds of the new dashboard/publisher source.
The task PR records the verified dashboard HEAD/build run, actual HTTP checks,
artifact hashes, deployment and final CI results; this text alone is not evidence
of a deployment. Automatic future publication starts when the workflow change
reaches develop through an approved merge. Keep these links and this rule current
for subsequent client tasks, as required by the owner and AGENTS.md.

Validation covers five-platform snapshot preservation, immutable/idempotent
replays, wrong SHA/run/attempt/hash/size/version/kind, missing sources, Simulator
rejection and unsafe ZIP paths. Caddy tests cover authentication, attachment and
no-store headers for all new binaries/sources. Dashboard unit tests, TypeScript
and production build cover catalog parsing and fixed destinations.
No backend follow-up is needed for downloads; Apple signing/distribution and
real-device VPN acceptance remain separate work. Restore the retained dashboard
site and download snapshot symlinks for a deliberate rollback under the existing
publication lock; do not overwrite immutable files or catalog coordinates.

## iOS Simulator download — 2026-11-05

Dashboard **0.6.0 → 0.6.1** fixes selection of the wrong SDK package for browser
simulators. iOS **0.1.0 → 0.1.1** also fixes missing Simulator Keychain entitlements
found during exact-archive launch review. macOS remains 0.1.0; backend is 0.34.1
and Chrome 0.1.2 after PR #60; Windows stays 0.25.2 and Android 0.21.2.

Use `/dashboard/downloads/ios-simulator.zip` for Appetize or Apple Simulator
(ARM64, iOS 17+). It contains the original `PrettyLisaVPN.app` built with the
`iphonesimulator` SDK. Upload the ZIP to the browser service's Simulator/ARM
environment. `/dashboard/downloads/ios-unsigned.zip` remains the unsigned physical
iPhone build and cannot be uploaded as a Simulator app. Both links use existing
dashboard authentication; download locally before uploading to an external service.
No external service account or app has been created or changed by this task.

Apple CI packages both archives from its own run, installs and launches the exact
Simulator ZIP, verifies read/write/update/delete through the real Keychain adapter
with a disposable noncredential value, then relaunches without fixture arguments,
records its SHA256 and captures
`simulator-download.png`. This proves native Simulator launch, not an Appetize
upload or a real VPN tunnel. Simulator-only ad-hoc signing supplies the app's own
application identifier/access group through Xcode's Simulator build settings;
packaging preserves that signature. No Apple team, shared native-device group or
plaintext credential fallback is introduced. The diagnostic exists only in Debug
Simulator builds and runs solely with `-verify-keychain`. The earlier 0.1.0 archive
from PR build `75051b7dcf270f0c066ee7d8d7688ea2d3d0475e`, run 42032440782/1,
launched but showed SECURE_STORAGE_UNAVAILABLE; it is not storage acceptance of
0.1.1. Final source/build and native evidence belong in PR #58.
Appetize format requirements:
https://docs.appetize.io/platform/app-management/uploading-apps/ios.

The existing iOS entry has optional `simulator_url`, `simulator_sha256` and
`simulator_bytes`; legacy catalogs remain compatible and show only the device
button. The publisher checks the separate Simulator SDK, version, hash and size,
retains the companion across all platform updates, and rejects conflicting
immutable companions. Device, Simulator and sources share original SHA/run/attempt
and one atomic publication. New Apple packaging requires the Simulator archive;
missing/invalid archives fail the build. Preserve this companion in future changes.

Tests cover swapped SDKs, corrupt/missing companions, legacy catalogs, fixed URLs,
five-platform preservation, immutable replay conflicts and Caddy authentication/
attachment headers. Record exact product HEAD, PR merge/build SHA, run/attempt,
artifact hashes, all CI jobs and deployment evidence in the task PR after checks.
No new endpoint, migration, credential or backend follow-up is required. Install
the new publisher before the next publication; old publishers omit this companion
when recreating snapshots. Follow the existing retained-snapshot rollback process.
