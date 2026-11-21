# Production standby: deployed mirroring, takeover pending

## Scope and current state

**Продакшен**, authorized by the owner. Backend, website and client versions are
unchanged; no product sources, contracts, schema or migrations change. The owner
requires one existing PostgreSQL and one existing Valkey shared by both hosts.
No database copy or additional paid infrastructure was created. The separate test
host `5.129.211.150` is outside this task.

| Role | Host | Observed state on 2026-11-19 |
| --- | --- | --- |
| Active primary | `95.140.152.42` | Existing containers continue serving requests |
| Inactive standby | `130.0.234.51` | Images loaded; verified snapshots staged; app stopped |
| PostgreSQL | Existing Timeweb cluster `4206497` | Independent read-only TLS query from standby succeeded |
| Valkey | Existing cluster `4206507`, `192.168.0.5:6379` | Private network only; unreachable independently from standby |

**Automatic failover is not implemented or enabled.** This work provides continuous
inactive mirroring, not the full availability goal. DNS still points to the primary.
A successful mirror job is not a successful failover test.

## Deployed mirroring

The primary runs `prettylisavpn-standby-prepare.timer`; the standby runs
`prettylisavpn-standby-pull.timer`. Both run 60 seconds after the previous job ends,
with up to five seconds of timer coalescing. This is asynchronous: new deployments
need preparation, transfer and verification time, not a fixed one-minute recovery
point guarantee. Large initial images take longer.

`infra/standby/mirror.py` captures `backend`, `caddy`, `fleet-worker` and
`product-analytics` from the historical Compose project `prettylisavpn-development`.
That name and the runtime channel do not identify the separate test environment.
It captures actual effective Docker configuration and image IDs, including owner
settings absent from older Compose files. Included contents:

- Running images, container definitions, current release metadata, Compose/Caddy.
- `/etc/prettylisavpn/*.env`, active application secrets and allowlisted live mounts.
- Current dashboard, public website and client downloads. Publisher links within
  each artifact store are materialized; archived download history is excluded.
  Original build/release identity files are preserved.
- Existing Caddy certificate data/config and fleet credential mounts.

Secrets stay in root-only directories and travel over pinned SSH; they are not
committed, printed or included in CI artifacts. The dedicated key only reads
`/opt/prettylisavpn/standby-export` using `rrsync -ro`, only from the standby IP.
It has no general shell or write access. Hashes do not replace SSH authentication.

Hashes, sizes, ownership and file permissions are verified before changing the
standby `current` pointer. Images are loaded but no application starts. Unchanged
snapshots do not retransfer payloads; new ones reuse equal files. Three snapshots
are retained. Only images imported by this automation and no longer referenced by
retained snapshots are eligible for non-forced Docker removal. Pre-existing or
in-use images are preserved. Failed transfers leave the last good snapshot intact.

An `ACTIVE` marker fences imports. Future activation must take the same
`/run/prettylisavpn-standby-mirror.lock` and set the marker before starting services.
This is a local copy safeguard, not distributed split-brain fencing.

## Future changes must reach both servers

Every production deployment must verify that the standby has the new runtime
identity, images, artifacts and settings before reporting redundancy as current.
The timers cover the above sources, including rollbacks, without manual per-release
copies. Extend the allowlist and tests when adding a service, mount, secret path
or publisher layout. OS packages, firewall, users and system services are not
whole-machine replicated: apply equivalent role-appropriate changes through
Ansible to both hosts. Never copy primary IP/network identity onto the standby.
After takeover, stop the old replication direction and explicitly select the
authoritative deployment host before resuming paired releases.

## Installation and verification

Run from a trusted Linux Ansible controller with administrator SSH access and
verified host keys. The example inventory contains no credentials:

```sh
ansible-playbook -i infra/standby/inventory.example.ini infra/standby/bootstrap.yml
ansible-playbook -i infra/standby/inventory.example.ini infra/standby/mirror.yml \
  -e primary_known_hosts_file=/secure/path/to/verified-primary-known-hosts
```

Initial installation used pinned administrator SSH. The bootstrap playbook was
applied on the standby, then repeated with `changed=0`. The equivalent multi-host
mirror playbook is syntax-checked, not yet replayed end to end from a controller.
Installation does not start the app, publish ports or change DNS.

On the primary:

```sh
systemctl status prettylisavpn-standby-prepare.timer
systemctl show prettylisavpn-standby-prepare.service -p Result -p ExecMainStatus
cat /opt/prettylisavpn/standby-export/latest.json
```

On the standby:

```sh
systemctl status prettylisavpn-standby-pull.timer
systemctl show prettylisavpn-standby-pull.service -p Result -p ExecMainStatus
cat /opt/prettylisavpn-standby/status.json
docker ps --format '{{.Names}} {{.Status}}'
df -h /opt/prettylisavpn-standby
```

Expect fresh `primary_checked_at_unix` and `synced_at_unix`, `STAGED_NOT_ACTIVE`,
matching snapshot IDs after convergence and no running application containers on
the standby. Do not print `containers.json` or mirrored environment files: they
contain secrets. An enabled timer does not prove the last job succeeded. Journald
records redacted structured events; external alert delivery is not configured.
To stop copying, disable the corresponding timer with `systemctl disable --now`;
this does not stop the production application.

## Shared storage and remaining failover work

PostgreSQL is reachable through its existing public TLS hostname
`0148034f362b3d411dbc6922.twc1.net:5432`. The standby successfully executed only
`SELECT 1` and a TLS-state query with a read-only connection. The CA came from the
[provider certificate URL](https://st.timeweb.com/cloud-static/ca.crt) published in
[Timeweb's connection documentation](https://timeweb.cloud/docs/dbaas/postgresql/connect-to-database).
Python 3.13's extra `VERIFY_X509_STRICT` flag rejects this legacy CA with code 85
(missing authority key identifier). The probe cleared only that flag, retaining
`CERT_REQUIRED`, chain validation and hostname checking. This is not yet a
deployed standby application TLS configuration.

Valkey has no public address or configured TLS. The standby is outside its private
Timeweb network. A tunnel through the primary fails with the primary and cannot
satisfy this task. Do not expose plaintext Valkey credentials/traffic publicly or
duplicate either storage service. A network-only gateway was proposed but not
authorized; no new recurring cost was incurred.

Before enabling takeover:

1. Establish owner-approved independent protected access to the **same** Valkey:
   place the standby in the network or use an independent protected gateway.
   Verify authenticated PING without writing application data.
2. Prepare role-specific configuration for the same storage and exact mirrored
   images. Do not warm-run the API for healthchecks: its lifespan starts background
   support and billing work even without client requests.
3. Implement activation with primary fencing, repeated independent health evidence,
   fresh snapshot checks, readiness and durable state. DNS alone does not stop
   old workers or cached client traffic during a network partition.
4. Update DNS only after readiness; verify authoritative answers. Existing apex/API
   A records are `95612935`/`92177763`, primary IP, observed TTL 600 seconds.
   Neither DNS values nor TTLs were changed. Caching prevents instant failover.
5. Exercise failures, partial activation and recovery in an agreed outage drill.
   Keep failback deliberate; never overwrite an active host from a stale primary.

Shared PostgreSQL and Valkey remain single dependencies by owner choice. Application
host redundancy does not cover failure of these services or VPN data-plane nodes.

## Evidence and handoff

Observed baseline, copied without rebuilding the application:

- Product source SHA: `afcf94dd20f22a6027da55a89b491a56acd09620`.
- Runtime: `0.54.1-dev.44513423200+gafcf94dd20f22a6027da55a89b491a56acd09620`.
- Build run/attempt: `44513423200 / 1`; release
  `afcf94dd20f22a6027da55a89b491a56acd09620-run-44513423200-attempt-1`.
- Backend/worker image:
  `sha256:80a9f37b6f2cf0898a92950d9621b87cc4c70bb4f02f96fd6bcc20a300b5d1e2`.
- Caddy image:
  `sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d`.
- First staged snapshot:
  `4dc577ad8af95a5732e1eda32a10092ae3c6bd8b21819cb2cc3020f96f16770e`.
  Later snapshot identities naturally change with configuration/artifacts.

The infrastructure PR HEAD differs from the application build SHA. Record final
infrastructure HEAD and all Actions runs/jobs/links in the PR after the last push.
No application rebuild, merge, release tag, migration, outage drill or traffic
switch is claimed by infrastructure checks.

Checks: Ruff format/lint, strict mypy, 15 integrity and inactivity tests on both
real Linux hosts, Ansible syntax and systemd validation. A harmless task-owned
`.env` file not loaded by any application propagated automatically; it was then
removed; its removal also propagated automatically. Compare the installed mirror
program's SHA-256 with the reviewed file.
