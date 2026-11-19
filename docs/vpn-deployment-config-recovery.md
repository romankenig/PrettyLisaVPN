# VPN configuration recovery — 2026-11-19

## Scope and cause

Infrastructure, tests and documentation only: **version unchanged**. Source baseline
is develop `6dba22f987475fbc7d14ff1ea3372d13143c4d1c` (backend 0.54.2); the recovered
server continues to run backend **0.54.1**, with no binary replacement or migration.
Client versions and API contracts are unchanged.

At 11:28:21 UTC the backend was recreated using its release env. The earlier CI
deployment supplied `FLEET_ENV_FILE`, `FLEET_CREDENTIALS_DIR` and `DASHBOARD_DIR`
only as shell exports; neither retained env contained those paths. The actual
fleet file was `/opt/prettylisavpn/secrets/fleet.env`, whereas plain Compose fell
back to absent `/etc/prettylisavpn/fleet.env` with `required: false`. Backend started
with fleet/client/managed VPN disabled. Auth, databases and health probes still
worked; the separate fleet-worker retained its correct configuration and continued
renewing existing node grants. VPN control requests returned `503 VPN_UNAVAILABLE`.

## Live recovery and evidence

Owner authorized restoration and backend recreation. At 12:22 UTC the fleet,
credentials and dashboard paths were persisted in both release and canonical env.
Before recreation the resolved image and every existing environment value were
compared in memory; only the omitted fleet settings were added. Only backend was
recreated, with `--no-deps --force-recreate --pull never`. It became healthy and
all three VPN flags were true. Payment and DEMO configuration were preserved.

- Runtime: `0.54.1-dev.44513423200+gafcf94dd20f22a6027da55a89b491a56acd09620`.
- Original source/build SHA: `afcf94dd20f22a6027da55a89b491a56acd09620`,
  [Backend run 44513423200](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44513423200), attempt 1.
- Retained image ID: `sha256:80a9f37b6f2cf0898a92950d9621b87cc4c70bb4f02f96fd6bcc20a300b5d1e2`.
- Protected pre-recovery env backup:
  `/opt/prettylisavpn/recovery/vpn-config-20261119T122218Z/`.
- Public readiness passed. An invalid-token session lookup changed from VPN-disabled
  503 to the expected authentication 401; this alone is not traffic acceptance.
- Owner confirmed both Windows and Android now connect and disconnect.
- Independent database evidence: Android's old lease was removed at 12:23:48 UTC,
  Windows' at 12:24:30 UTC. New Android/Windows leases reached READY and passed
  the egress probe at 12:23:55 / 12:24:48 UTC respectively.

The installed Windows window could not be captured: two Computer Use attempts
failed with capture timeouts. No new native screenshot or new-client-build acceptance
is claimed. The user-operated client test and server records are separate evidence.

## Permanent correction and validation

The prepare step retains absolute owner configuration paths and remembers which
files are required, without copying their credentials into CI. Future releases
inherit those settings before saving their env. Both backend and fleet-worker use
the same required fleet file. A fresh installation can keep unconfigured optional
features disabled; a previously present file cannot silently disappear on update.
CI and manual deploy use the retained release env. Post-deploy verification compares
running image/environment with resolved configuration without printing values.

Regression checks cover preparation, subsequent releases, lost files, permissions,
shell-free Compose rendering, runtime drift, missing workers and rollback/migration
ordering. Tests use synthetic credentials and never start test containers on the
live server. Final product HEAD, full CI runs/jobs, and any operational installation
of the infrastructure files are recorded in the task PR after the final push.

Do not restore the broken pre-recovery env without its required fleet paths. Keep
the existing application image and schema when rolling back this infrastructure
change; no account, subscription, VPN-lease or node records need rewriting. Merge
of the workflow correction remains a separate owner action. Until merged, future
CI uses the older workflow, so it must not be treated as protected by this PR.
