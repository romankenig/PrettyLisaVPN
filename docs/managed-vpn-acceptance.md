# Managed VPN development acceptance

Owner target (2026-10-24): at least one real Android **or** Windows connection,
verified by DNS and HTTPS through the owned tunnel. Stop after the first verified
success or after three real client attempts. Builds, unit tests and server
preparation do not count. Initial counter: **0/3**. Final attempt evidence, exact
product/build SHA, run/attempt and artifacts belong in PR #29.

## Versions and compatibility

- Backend 0.13.0 → 0.14.0: opt-in authenticated managed access, migration 0028.
- Node agent 0.1.0 → 0.2.0: isolated native authorization lifecycle.
- Android remains 0.9.0/code17 and companion 0.1.0 within the unfinished transport
  task; Binder protocol v2 requires both APKs from this task, signed identically.
- Windows remains 0.13.0. Its managed-engine integration is still pending.

Deploy node agent/binary and migrate the backend before installing the companion.
Production/default settings leave managed issuance disabled. Only explicit
`VPN_MANAGED_NODES` UUIDs in development/test with a separate 32+ character
`VPN_MANAGED_SECRET` may issue it. This preview chooses VLESS/REALITY/Vision TCP
through an existing DE/US session. The existing account/device/quota admission
remains authoritative. Without the companion Android keeps the existing WG path.
The other article methods are still not enabled on the fleet.

## Authorization and cleanup

`POST /vpn/sessions/{session_id}/managed` authenticates ownership and returns a
private typed profile with `Cache-Control: no-store`. A dedicated HMAC key derives
an unpredictable session/node-scoped UUID credential; PostgreSQL stores intent,
deadline, issue/revoke timestamps and node acknowledgement, never the credential.
The intent commits before the node call. Exact retries reuse the deadline and
credential. Concurrent issuance/removal serialize on the session lock.

The development lease is capped at 15 minutes or the existing session deadline,
whichever is earlier. This is a preview authorization cap, not an account plan
change. The session expiry is shortened to match; quota returns only after the
existing confirmed-cleanup flow. Each native process independently enforces its
deadline even if the API or reconciler is unavailable. Do not rotate the HMAC key
while leases are active; drain them first.

The mTLS node agent uses one unprivileged Xray process per lease, with at most 64
configured high TCP ports. Private settings arrive over stdin; stdout contains
only READY. On removal the SQLite tombstone commits before process termination.
Killing the process closes established sockets too. A late PUT cannot resurrect
the lease. EOF, hard expiry and systemd control-group shutdown also close it.
Restart recovery checks executable/lease argv via pidfd before killing an orphan;
failure never produces a removal acknowledgement. Tombstones are retained in this
bounded preview; production retention and larger shared-listener capacity remain
follow-up work. No browsing/destination/DNS/payload logging is enabled.

Managed removal must be acknowledged before WG removal and session cleanup.
A missing WG peer alone cannot acknowledge managed cleanup. Agent outages retain
pending cleanup and block false success. Rollback: disable new managed issuance,
drain/confirm existing leases, retain the additive database table, then roll back
binaries. Never roll back the cleanup implementation while managed leases remain.

## Android and artifacts

The main APK checks the companion package/signature and owns control via Binder;
the companion owns system consent, foreground service, one TUN and protected
uplink sockets. Main-process death closes the companion tunnel. Background
survival of the main coordinator is a remaining endurance-test item.

The companion independently verifies an owned VPN network, its TUN address,
default route and DNS server. A fresh IPv4 DNS lookup and HTTPS 204 request bind
to that network with no proxy, pool reuse or physical fallback. The main client
publishes Connected plus VLESS/REALITY only after this succeeds and its backend
session still exists. Consent is obtained through the real Android dialog.

Managed-engine CI produces the current-source companion APK, Linux server binary,
node-agent wheel, dependency notices and corresponding Go/vendor sources. These
are development artifacts, not release publication. Main-APK artifacts come from
Android debug CI. Use artifacts from the same source SHA; never substitute a
historical binary. Keep the source/license archive alongside any shared APK.

Kaspersky VPN on the Windows host must remain enabled because the user depends
on it for this session. Initial device acceptance therefore targets Android.
Do not count a health request over the host's existing VPN as PrettyLisaVPN success.
