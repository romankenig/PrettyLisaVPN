# Chrome Extension 0.1.0 / backend 0.34.0

Source baseline: develop `05d945dbd5da35f1c85523d00b4ab57415882a3c`.
New Chrome client 0.1.0; backend 0.33.0 → 0.34.0 for browser-only HTTPS leases.
Windows 0.25.2, Android, Apple and the managed engine versions remain unchanged.
Build SHA/run/attempt, final CI and live evidence belong to the task PR.

## DNS reminder requested by the owner

On the next continuation of Chrome Extension work, remind the owner if these
records are still missing. The owner deferred DE/US on 2026-11-04:

| Record (A, DNS only) | Exit IP | State at task start |
| --- | --- | --- |
| proxy-nl.prettylisavpn.com | 81.31.245.143 | Owner added; publicly resolves correctly |
| proxy-de.prettylisavpn.com | 5.181.49.183 | Awaiting owner DNS change |
| proxy-us.prettylisavpn.com | 204.48.17.50 | Awaiting owner DNS change |

Each exit needs a stable name and publicly trusted certificate. The provided
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

Chrome session state survives MV3 worker suspension, but not browser shutdown.
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
