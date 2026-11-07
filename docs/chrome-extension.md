# Chrome Extension 0.1.0 / backend 0.34.0

Provider-independent node enrollment, including the choice between DNS and a
public IP certificate: [server enrollment](server-enrollment.md). The original
DNS-only steps below are historical; the current IP path remains supported.

Source baseline: develop `05d945dbd5da35f1c85523d00b4ab57415882a3c`.
New Chrome client 0.1.0; backend 0.33.0 → 0.34.0 for browser-only HTTPS leases.
Windows 0.25.2, Android, Apple and the managed engine versions remain unchanged.
Build SHA/run/attempt, final CI and live evidence belong to the task PR.

## Current IP fallback — 2026-11-05

Chrome **0.1.1 → 0.1.2**, backend **0.34.0 → 0.34.1**: compatible PATCH fixes
address validation for the existing HTTPS proxy. Schema remains 0043; Windows,
Android, Apple and the managed engine versions are unchanged. Baseline is
`ce3c97ea59c1c1877be842636593c37c6c29d0d7` (merged auth/OTP PR #59).
The owner cannot add DE/US DNS records now. These records are optional when using
the IP certificate path below; do not block continuation on another DNS request.

Chrome sends `X-PrettyLisaVPN-Proxy-IP: 1` on authenticated VPN requests. Backend
uses it for country filtering and new allocations only; missing/unknown values
preserve the original DNS-only selection. Old backend versions ignore the header,
so either deployment order remains compatible. Idempotent replay still returns
the same lease, and all existing account, device, Free/Premium and cleanup rules
remain in force. The client accepts a canonical public IPv4 only if it is also
listed in the lease's expected egress addresses. The node requires it to match
its enrolled address and verifies the exact IP SAN against the system CA store.
There is no plaintext or certificate-validation fallback.

Use `infra/ansible/browser-proxy-ip-certificate.yml -e proxy_ip=<enrolled IPv4>`
with the existing pinned SSH inventory. It installs isolated Certbot 5.4.0,
requests the `shortlived` profile via HTTP-01 and enables
`prettylisa-proxy-certificate.timer` every four hours with up to 30 minutes jitter.
Keep port 80 reachable for renewal. TLS private keys stay on the exit. Existing
managed supervision detects certificate replacement and restarts proxy processes
on their next grant; normal client verification/recovery applies. Existing native
listeners and their keys are not replaced.

DE (`5.181.49.183`, root) and US (`204.48.17.50`, vpnadmin/sudo) certificate
preparation and renewal dry-runs succeeded on 2026-11-05. OpenSSL verified public
trust and exact IP SAN; both timers were enabled/active. Certificates expire on
2026-11-12 around 04:11/04:18 UTC, so automatic renewal is required. At preparation
time no new backend/helper was deployed and no node capability was activated.
Certificate issuance alone is not a successful browser VPN connection.

Direct data-plane acceptance on DE succeeded with product source
`471597c7a0a73a205d33c1589166d55c36641845`, exact Chrome push artifact
`13417913079` from run `42034982600` attempt 1. Inner ZIP SHA-256:
`805c17360f5b3efbe29fdee8fa5c5f549d5a5a861e8eea834d7e8cd7fe9ace8e`.
Installed Chromium confirmed HTTP/HTTPS exit IP `5.181.49.183`, a full HTTPS page,
WSS echo, private/IPv6 destination rejection, offline/online recovery and original
IP restoration on Disconnect. No SSH forward or certificate exception. Auth/lease
API responses were fixtures, and the backend proof remained explicitly unverified;
this does not prove real OTP/allocation/Connected on backend 0.34.1.

US direct HTTP/HTTPS IP checks reached `204.48.17.50`, but a full page stalled;
curl independently received only 8151 of 16426 bytes before timeout. An isolated
MSS diagnostic did not fix it and is not part of the shipped code. Keep US proxy
capability disabled until complete direct acceptance succeeds. Temporary test
processes/files were removed and ports released on both nodes; native sessions
were untouched. DE can be enabled after approved backend/helper rollout.

Validation: 19 Chrome unit tests, TypeScript/Vite, ESLint/Prettier and installed
isolated Chromium review; 136 targeted backend tests including real disposable
PostgreSQL allocation/country filtering and lifecycle, Ruff, strict mypy and
Alembic upgrade/check. Final product SHA, CI build SHA/run/attempt, artifact hashes,
all workflow results and direct transport/live API evidence belong to the task PR.
Do not attribute the older NL SSH-forward test below to direct DE/US acceptance.

After approved merge/development deployment, configure managed DE/US with their
existing server_name/reality_target plus `proxy_host` equal to the enrolled IP.
Verify helper hashes and an actual OTP → allocation → browser egress chain using
the exact published Chrome ZIP, then confirm cleanup. The existing shared publisher
updates `/dashboard/downloads/chrome-extension.zip` after successful develop CI.
Rollback preserves certificate timers/history and existing leases; avoid assigning
IP endpoints to old extensions. The capability header does not add native protocols:
independent Chrome remains a browser-only HTTPS proxy client.

References: [Let's Encrypt IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability),
[Certbot IP support and renewal](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).

## Historical DNS setup at 0.1.0

The owner deferred DE/US DNS on 2026-11-04 and again on 2026-11-05. The IP path
above supersedes the original requirement to wait for those records:

| Record (A, DNS only) | Exit IP | State at task start |
| --- | --- | --- |
| proxy-nl.prettylisavpn.com | 81.31.245.143 | Owner added; publicly resolves correctly |
| proxy-de.prettylisavpn.com | 5.181.49.183 | Awaiting owner DNS change |
| proxy-us.prettylisavpn.com | 204.48.17.50 | Awaiting owner DNS change |

The original DNS path needs a stable name and publicly trusted certificate. The provided
Ansible playbook automates issuance/renewal after DNS exists. Future DNS automation
can use the owner's provider API; no credentials should be sent in chat. The RU
INTERMEDIATE node is not advertised as a direct exit. Chrome relay mode is not
implemented in this first release.

## Architecture and compatibility

The extension uses real passwordless auth and CHROME_EXTENSION device identity.
It obtains `/vpn/countries?method=https_proxy`, then creates an idempotent lease
through `/vpn/sessions`. It never accepts native engine profiles or plaintext
proxy configuration. Chrome alone can request `https_proxy`; native clients keep
their existing methods. Existing paths, schemas and native heartbeat policy remain
compatible. Migration 0043 only extends the method constraint. Downgrade is refused
after proxy lease history exists; never erase quota/authorization history to roll back.

The existing worker owns quota reservation, principal validation, node locks,
short grants, process cleanup and retry. HTTPS proxy is an unprivileged per-lease
Python process on the VPN exit, supervised by the existing managed node helper.
TLS keys stay on the node. No API server carries user traffic. Public trust,
hostname/key pairing and certificate validity are checked before grants; a missing
certificate cannot become a working proxy. Each lease has separate credentials
and port. The existing firewall deadline and autonomous cleanup remain in force.

`proxy_host` is optional in managed node configuration. Only nodes configured with
this capability appear in Chrome country selection. Configure it only after DNS,
certificate and the helper are prepared. Changing it with active proxy leases is
refused. Existing native transports and their node-owned identities are preserved.

In 0.1.0, Chrome session state survived MV3 worker suspension, but not browser shutdown.
Version 0.1.1 preserves authentication across shutdown as documented below.
The restored worker revalidates Chrome proxy ownership and authenticated egress
before Connected. No direct fallback is configured; user Disconnect clears only
this extension's overrides. Unknown allocation retries preserve the original UUID.
The exact control-plane host `api.prettylisavpn.com` is an explicit direct
exception, so the backend remains reachable during a proxy outage. Egress proof
uses `https://prettylisavpn.com/vpn/sessions/{UUID}/probe`: Caddy forwards only GET
on that exact route to the same authenticated/owned lease handler, without access
logging. Other public-site API routes stay closed. Ordinary sites have no direct
fallback. Failed verification retries after network recovery; confirmed heartbeat
expiry may create a fresh lease only after old cleanup is confirmed.
Failed cleanup remains visible and prevents creating another lease. Missing browser
heartbeats terminate access; no background session is charged indefinitely after exit.

Scope and limitations are listed in [the client README](../apps/chrome-extension/README.md).
Support is real API delivery, billing read-only; no payment-provider changes.
No history, URLs, DNS queries, packet contents or OTP/credential values are logged.

## Verified on 2026-11-05

Product implementation: `93ae093be799ccf37a7c48a08bb5f410206aeb60`;
tested branch head: `6a855fcfeaef7bcd79877fa80600160b39ba7423` (only the
country-monitoring test fixture changed after the product commit). Chrome 0.1.0
was loaded as an unpacked local build in isolated Chromium 156.0.8078.4. The node
helper matched the source with SHA-256
`e224547860fd2cad5414acce3e2b18b97f42c8ceafd9c709752531a117bea865`.
Final distributable build SHA/run/attempt and all workflow results are recorded in
[PR #55](https://github.com/romankenig/PrettyLisaVPN/pull/55), separately from this
local transport acceptance.

| Check | Observed result |
| --- | --- |
| Browser HTTP and HTTPS external IP | `81.31.245.143`, the NL exit |
| HTTPS page content | Public PrettyLisaVPN website loaded through the proxy |
| WSS | Encrypted WebSocket echo round trip passed |
| Private destinations | IPv4 loopback, link-local and IPv6 loopback requests rejected |
| Temporary offline / online | Data path resumed with the NL exit IP |
| Disconnect | Previous browser exit IP restored |
| Invalid proxy password | HTTP 407, no authenticated tunnel |
| Invalid TLS hostname | Certificate validation rejected the connection |

The browser test used fixture auth/lease API responses and the real proxy process
with disposable credentials. Direct TCP from this workstation to the NL proxy
port timed out, so its isolated browser used an SSH TCP forward through the main
host. TLS still validated `proxy-nl.prettylisavpn.com` against the public CA store;
no certificate exception was used. Independent curl checks from the main host
connected directly to the NL proxy and confirmed HTTP/HTTPS exit IP, authentication
rejection and hostname rejection. The temporary process, grant credentials,
forward, helper copy and isolated browser profile were removed; the port was
confirmed released. Existing native sessions and managed grants were not changed.

This proves the implemented data transport, **not** the complete live
OTP → backend allocation → authenticated Connected chain. Live backend remains
0.33.0; migration 0043, the new worker/helper, proxy node capability and the Caddy
probe alias still require rollout. Full live quota/device revocation, lease renewal
and direct workstation reachability must be checked after rollout. Unit and
integration tests cover these lifecycle rules but do not replace live acceptance.

The repository certificate playbook completed successfully on NL. Its publicly
trusted Let's Encrypt certificate is valid from 2026-11-05 to 2027-02-03;
`certbot.timer` is enabled and active. Private TLS keys stayed on the node. The
existing Timeweb Ubuntu package mirror was switched from HTTP to HTTPS because
HTTP timed out; the original source file was retained as
`/etc/apt/sources.list.d/ubuntu.sources.before-chrome-tls`, with Ubuntu signature
verification unchanged. DE/US DNS and certificates are still pending.

## Operator rollout and real acceptance

1. Review/merge and deploy backend 0.34.0 with migration 0043 using the normal
   development pipeline; this PR alone does not imply a deployment.
   Include its Caddy config for the dedicated browser-probe route; preserve the
   independently published static website release.
2. Add the DNS records above. Run `infra/ansible/browser-proxy-certificate.yml`
   against enrolled exits using the existing pinned SSH inventory. Keep HTTP-01
   port 80 available and `certbot.timer` enabled; never copy TLS private keys out.
3. Reconfigure managed nodes using their current server_name/reality_target plus
   their exact proxy_host. Bootstrap installs the new helper, preserving active
   native leases. Verify certificate validity and installed helper hashes.
4. Load the exact CI `dist` artifact in isolated Chrome; record its build identity.
   Use the real OTP flow. Verify NL, then DE/US when their DNS is ready.
5. Confirm authenticated probe IP, HTTPS and HTTP pages, WSS, remote DNS behavior,
   IPv6/private-target block, wrong credentials/certificate rejection, disconnect
   restoration, reconnect, lost network, worker suspend/restart, expiry, device
   revocation and Free quota release. Keep the user's personal browser/VPN intact.
6. Record real outcomes separately from unit tests and API-fixture screenshots.
   Web Store publishing and production deployment are separate owner actions.

Official platform references: [Chrome proxy](https://developer.chrome.com/docs/extensions/reference/api/proxy),
[proxy authentication](https://developer.chrome.com/docs/extensions/reference/api/webRequest),
[privacy settings](https://developer.chrome.com/docs/extensions/reference/api/privacy),
[MV3 lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).

## Authentication recovery — 2026-11-05

Chrome **0.1.0 → 0.1.1** fixes login loss at browser exit and OTP screen loss when
the popup closes. Backend remains 0.34.0, Windows 0.25.2, Android 0.21.2 and Apple
clients 0.1.0. No schema, API, entitlement or proxy-protocol change.

Only auth tokens persist in local profile storage, restricted to trusted extension
contexts (no content scripts, Chrome Sync, new permissions or OS-keychain claim).
Session storage still holds lease credentials/pending allocations and the requested
OTP email. Never store the OTP itself. Successful OTP sending commits its state in
the worker before responding to the popup; another email clears it, successful
login removes it. A tab can host the same `popup.html` login flow without losing
state when the user switches to webmail. Snapshots expose neither auth nor proxy
secrets. Existing active auth migrates when the worker next runs.

After a browser restart, retain sign-in but clear Chrome proxy overrides because
their ephemeral credentials are gone. Connect retrieves any previous lease and
confirms cleanup before allocating again. Token rotation persists before volatile
state; a null durable marker prevents stale session storage from restoring a logged
out account. Definitive revocation clears auth; transient network errors retain it.

Validation includes 18 unit tests, lint/types/format/build and installed Chromium
tests of popup close/reopen, sign-in tab, real browser/profile restart and existing
screens. API fixtures prove UI/storage behavior only. Record the final product HEAD,
actual CI build SHA/run/attempt and artifact in the PR; publishing the updated ZIP
still uses the successful develop build and authenticated dashboard link.

Read-only rollout inspection on 2026-11-05 confirmed backend
`0.34.0-dev.42021407979+g46ed711e8df85bcceff66e34c9374ca1f6ba5ab5`, migration
0043, and the NL managed method READY with its proxy hostname. Earlier complete
OTP/lease tests used an SSH forward and did not prove direct workstation reachability.
Current direct TCP checks to NL ports 22/8443 time out; DE/US SSH is reachable but
`proxy-de`/`proxy-us` DNS is missing. This is a transport rollout dependency, not
evidence that the new login code repairs reachability. Add the documented A records,
issue trusted certificates and enable corresponding node capabilities, then verify
real browser traffic directly. The owner selected an independent browser-only
extension; native Windows tunnels/helpers are outside this task.
