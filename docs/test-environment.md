# Test environment and publication workflow

Owner decision: 2026-11-19. «доработай» means implement/test, update affected clients
and integrate verified changes into `develop`. «опубликуй» means first ask for the
release versions (unless already supplied for this publication), then promote the
latest accepted `develop` into `main` and deploy.
New installers are sufficient; no automatic client updater is included.
Before every change, explicitly name the target environment. Ask for component
versions if the owner did not provide them, including for test changes; wait for
the answer before changing versions or deploying the proposed release.

## Infrastructure inventory

| Resource | Production | Test |
| --- | --- | --- |
| VPS | `95.140.152.42` | `5.129.211.150` |
| Website | `https://prettylisavpn.com` | `https://test.prettylisavpn.com` |
| API/dashboard | `https://api.prettylisavpn.com` | `https://api.test.prettylisavpn.com` |
| PostgreSQL | managed `192.168.0.4:5432/default_db` | local `test-postgres:5432/default_db` |
| Valkey | managed `192.168.0.5:6379/0` | local `test-valkey:6379/0` |
| GitHub deployment environment | `production`, branch `main` | `testing`, branch `develop` |
| Backend runtime channel | `release` on the next authorized publication | `development` |
| VPN control | existing production fleet | disabled until separate test nodes exist |

The default GitHub branch is `develop`. At cutover, `main` is historical and behind
the code actually running in production; it must not be used to reconstruct the live
baseline. The clone preserves actual image/artifact identities independently.
The retired GitHub `development` environment cannot deploy from develop, and the
historical `DEV_DEPLOY_ENABLED` remains false. New backend gates are
`TEST_DEPLOY_ENABLED` and `PRODUCTION_DEPLOY_ENABLED`; branch/environment restrictions
and expected host/data-source checks apply as well.

At the initial clone, production contained seven nodes: FREE Germany
`5.181.49.183`, FREE USA
`204.48.17.50`, FREE Netherlands `81.31.245.143`, intermediate Russia `45.153.68.12`,
Premium Austria `89.58.16.22`, Premium Germany `201.79.12.109`, Premium Japan
`38.180.7.144`. During this task, a parallel enrollment added Premium UK
`38.180.140.18` (`ishost-uk-001`); the production API now lists eight enabled nodes.
This later production enrollment is absent from the initial test snapshot.
The copied database contains the original nodes' historical observations only;
the clone must never control these nodes. DNS is hosted by Timeweb. TLS certificates
renew through Caddy; VPN-node health/cleanup/certificate jobs remain on their nodes.

## Working data and copied baseline

On both VPSs, `/opt/prettylisavpn/current` selects an immutable application release;
`releases/<SHA>-run-<run>-attempt-<attempt>` retains exact deployment configuration,
runtime identity and image ID. Secrets are outside Git in `/opt/prettylisavpn/secrets/`
and `/etc/prettylisavpn/`. Website files live in `/opt/prettylisavpn/public-website/`;
dashboard files in `/opt/prettylisavpn/secrets/dashboard/`; verified installers and
their catalogs in its `downloads/` directory. Atomic pointers retain former releases.

Test PostgreSQL/Valkey are owned by the separate
[data Compose project](../infra/testing/compose.yaml), with persistent Docker volumes
and no host database ports. Private configuration is under
`/opt/prettylisavpn/test-data/`. Both projects share the external network
`prettylisavpn-development_application`, labelled with
`com.docker.compose.project=prettylisavpn-development` and
`com.docker.compose.network=application`. Do not remove its data volumes on redeploy.

The initial database import is a consistent snapshot, not replication: schema
`0053_analytics_plans`, 73 accounts, 88 devices, 7 fleet nodes at import. 29 copied
auth sessions were revoked in the test copy; Valkey starts empty. Separate OTP,
DEMO identity, fleet/admin, dashboard and SSH credentials prevent reuse of production
sessions. The retained private dump is in `/opt/prettylisavpn/imports/`; never expose
it as a CI artifact or website download. Production accounts/payments remain in the
managed database and are never replaced by the test snapshot.

The exact baseline backend image is
`prettylisavpn-backend:d6e4c1d537ae6bdcee7c5ccc6f8829cd2dffd5c6-run-44347588791-attempt-1`,
image ID `sha256:882a46d4a69b719d813c322392b9f8f89eda24ed2fa173e6e1be75b8ecca95f6`.
Baseline website: 0.7.1, source `2ac1e72b31ef66e8caba10cc4391bd759e11fe5c`, run
44277188302/1. The later Platega backend 0.54.1 changes were incorporated from
develop `afcf94dd20f22a6027da55a89b491a56acd09620` before this task's PATCH.
Old copied installers retain their original production targets and are archived;
only newly built test-targeted installers enter the active test download catalog.

## What updates automatically

- A successful `develop` push deploys changed backend components and changed static
  website files to the test server. Affected Windows/Android/Chrome/Apple workflows
  build against `api.test.prettylisavpn.com` and publish after their required checks
  and the compatible backend readiness gate succeed. Failed builds leave previous
  downloads intact. PR/manual builds are never published as downloadable releases.
- The owner's existing private `api.prettylisavpn.com/dashboard/downloads/*` URLs
  serve test installers through authenticated server-side proxying. Production
  `/downloads/*` files remain in their independent store. Dashboard monitoring still
  reads its original server; only the private download routes are redirected.
- An authorized `main` promotion uses production credentials and production API
  origins, deploys backend/website and publishes installers. Runtime backend changes
  apply immediately; installed client behavior changes after installing a new build.
- Artifact identity includes original source SHA/run/attempt, binary checksums and
  expected API origin. Apple remains honestly labelled unsigned; device, Simulator
  and corresponding-source packages are distinct. No signing identity is invented.

The initial test installation was checked over HTTPS for health/readiness/version,
website/account rendering, anonymous dashboard rejection and authenticated dashboard
history. Docker/PostgreSQL restored successfully. This verifies the baseline only;
new source/build/deploy identities and full CI evidence belong in this task's PR.

## Isolation configuration and remaining work

The test backend uses `PUBLIC_WEBSITE_ORIGIN=https://test.prettylisavpn.com`, so both
CSRF checks and native-client handoffs stay in the test environment. Test client
probes, control APIs and billing portal targets follow the selected build channel.
Existing public read-only legal-document links remain unchanged.

`BILLING_PROVIDER=disabled`; live payment secrets are absent. Support SMTP credentials
are omitted to avoid resending imported requests. Only explicitly requested OTPs
use the configured auth mailbox. `CLIENT_VPN_ENABLED=false`, `MANAGED_VPN_ENABLED=false`
and `FLEET_WORKER_ENABLED=false`; production node keys/inventory were not installed.
The clone can display copied monitoring history but cannot provide real VPN tunnels.

For real VPN testing, provide one additional VPS (IP and root/SSH access); it will be
enrolled only into the test fleet. No further DNS access is needed for the approved
test domains. Apple signing/notarization needs the owner's Apple team/profiles if
installable signed releases are desired later. Existing unsigned delivery remains.
The current task retains an initial private database backup; scheduled off-server
backup/restore drills are a separate operational follow-up.

Access is already available: GitHub administration/Actions, verified root and deploy
SSH identities for both VPSs, production data access through its private network,
test database credentials, DNS records and auth SMTP. Local ignored credentials:
`keys/test-server-admin`, `keys/testing-ci-deploy`, `keys/production-ci-deploy`,
`keys/test-dashboard-login.json`. Do not paste their contents into reports.
Upload multiline OpenSSH keys/known-host files to GitHub as exact UTF-8 bytes with
LF endings. Windows text-mode subprocess input can introduce CRLF and break the
Linux SSH parser. Verify the test diagnostic before relying on a new CI identity.
Compose also reads `/etc/prettylisavpn/demo.env` as the deployment user: on the test
server it is owned by `prettylisa-deploy:prettylisa-deploy`, mode `0600`. Keep
owner-managed env files readable by that existing deployment identity without
making their contents public.

Timeweb initially blocked outbound SMTP at provider level. Its server API listed
465/587 among `blocked_ports`, while local OUTPUT rules allowed them. These two
ports were unblocked during acceptance; TLS/authentication against the configured
mailbox passed on both. This diagnostic does not send an email. A future new VPS
may need the same provider-side change through its dashboard or support; changing
Ubuntu firewall rules cannot remove this provider restriction.

## Completed deployment acceptance — 2026-11-19

PR [#114](https://github.com/romankenig/PrettyLisaVPN/pull/114) is merged into
`develop`. Product/deployment source is `bca9c2a2fbaa54a5ed56738afd94ae37b4c53c57`;
subsequent handoff commits change documentation only. No main promotion or
production application publication was performed.

| Component | Version | Successful build/deploy run and attempt |
| --- | --- | --- |
| Backend | 0.54.3 | 44531573162 / 3 |
| Website | 0.7.2 | 44531573025 / 2 |
| Windows | 0.31.5 | 44531573047 / 1 |
| Android | 0.30.4, code 63 | 44531573139 / 1 |
| Chrome | 0.5.3 | 44531573249 / 1 |
| iOS | 0.6.3 | 44531573228 / 1 |
| macOS | 0.5.3 | 44531573228 / 1 |

Live test `/version` reports
`0.54.3-dev.44531573162+gbca9c2a2fbaa54a5ed56738afd94ae37b4c53c57`.
HTTPS health/readiness and website/account checks passed; the running backend uses
`test-postgres`, `test-valkey`, the test website origin and disabled live billing,
client VPN, managed VPN and support delivery. No fleet worker is running there.

All five published client entries target `https://api.test.prettylisavpn.com`
and preserve that exact product SHA and their original run/attempt. Authenticated
downloads from the existing production dashboard URL verified all eleven file
hashes: five clients, four source packages, Windows licenses and iOS Simulator.
Anonymous UI/catalog/binary requests return 401; authenticated UI/downloads return
200 with private/no-store downloads. Apple device/macOS packages remain unsigned.

The private-download route was activated with one production Caddy restart.
Before/after checks confirmed the production backend container ID, website release
and content hash, and every public installer/source/catalog hash were unchanged.
The previous route is retained in `monitoring.before-test-downloads`; the existing
dashboard login and production fleet monitoring remain in use.

All eleven PR-head workflow runs and all ten product-merge push workflows completed
successfully, including reusable publisher jobs. Initial SSH timeout/key-format,
test env-file ownership, runner UDP timing and provider SMTP failures were resolved;
their failed attempts are retained. The PR records the complete workflow/job links
and native Windows evidence. Real test VPN sessions and signed Apple distribution
remain outside this acceptance until their separate resources are supplied.

## Publication and rollback checklist

1. On «опубликуй», ask for release version(s) unless already supplied, confirm affected
   components and the accepted develop HEAD, then verify all Actions events/jobs
   and source identities.
2. Back up current production business data, retain its active image/configuration
   and review forward migrations/backwards compatibility. No schema change is
   introduced by this environment task.
3. Promote accepted source to main and rebuild for production; do not reuse test
   binaries by changing metadata. Keep production domains, data and credentials.
4. Verify live version/readiness, fleet, website and every published download.
   Roll back application/static pointers using retained artifacts if needed;
   database downgrades/restores require a separate explicit data-loss assessment.

Component changes in this task: backend 0.54.2 → 0.54.3; Windows 0.31.4 → 0.31.5;
Android 0.30.3 → 0.30.4/code 63; Chrome 0.5.2 → 0.5.3; iOS 0.6.2 → 0.6.3;
macOS 0.5.2 → 0.5.3. Website 0.7.2 from #115 is retained; schema 0053 is unchanged.

PR coordination: Windows 0.31.4 is the outage/country-browsing fix from #113.
This independent environment task follows it at 0.31.5; source manifests stay
synchronized. The documentation from Japan enrollment #111 is retained as well.

PR #115 was merged concurrently during coordination. Preserve its recurring
checkout and explicit-rejection recovery; backend 0.54.3 now follows its 0.54.2.
The environment-specific PUBLIC_WEBSITE_ORIGIN remains configured.
