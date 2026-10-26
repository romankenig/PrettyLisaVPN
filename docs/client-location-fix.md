# Current location and compact backend version

Independent PATCH task following the VPN reset in PR #30:
Windows 0.14.0 → 0.14.1; Android 0.11.0/code19 → 0.11.1/code20.
Backend remains 0.16.0; API and schema 0028 are unchanged.
The prior product checkpoint is `177a078abd4f1e60fcba49f8acc849da622939f7`.
The [VPN reset handoff](vpn-placeholder-reset.md) retains the earlier full-system
rollback instructions; reverting this patch alone does not restore VPN engines.

## Diagnosis and implementation

On the owner's Windows network, DNS for `ipwho.is` returned `0.0.0.0` and HTTPS
could not connect. Both clients previously relied exclusively on that provider.
The new native Windows/Android path tries ipwho.is, then `https://ipinfo.io/json`
after DNS/connect/TLS/HTTP/JSON/invalid-IP failure. A real request to the fallback
returned HTTP 200 with IP, city and country on the same network.

The native Windows command accepts no URL or account data and allows only these
two built-in destinations. Requests have no account headers, cookies or WebView
Origin, disable redirects, validate IP addresses and bound bodies to 16 KiB.
Timeouts: 8 seconds per Windows provider, with a 17-second frontend deadline;
5 seconds per Android provider. Late Windows results cannot replace a newer
network observation; Android cancellation prevents starting the next provider.
Only IP, city and country enter UI state, without persistent location history.
Android location refresh runs independently of account/country API refresh.
Browser previews retain their existing HTTP provider; shipped Windows uses native.

This is public IP geolocation, so an already active third-party VPN changes the
displayed location. It is not GPS or a claim that the selected DE/US placeholder
connected. The reset's 14 cancellable VPN placeholders are unchanged.

IPinfo's [documented unauthenticated legacy API](https://ipinfo.io/missingauth)
currently supports this fallback; it has provider rate limits and may change.
If both services fail or limit the caller, location remains unavailable and the
existing periodic refresh retries. No fixed or selected-server location is used.

Windows now shares Android's strict display rule: show only the SemVer core from
the actual GET /version response. For example, `0.16.0-dev.123+gSHA` displays
`0.16.0`. Invalid/unavailable metadata displays unavailable. Raw backend metadata
remains intact for diagnostics and build/deployment evidence.

## Verification and delivery

Local checks cover the native provider failover, first-success stopping, invalid
responses, anonymous fixed requests, frontend deadlines/cancellation and SemVer
display. Android MockWebServer tests cover fallback, failure, IPv6 and cancellation.
Native UI capture now receives a long runtime version and asserts the short core.

CI must build the final pushed source and run all Android emulator/API variants,
Windows native UI review and backend checks before merge. Exact verified product
SHA, build SHA/run/attempt, client artifact links and final merge/development
deployment evidence are recorded in [PR #30](https://github.com/romankenig/PrettyLisaVPN/pull/30)
after completion, avoiding a documentation-only push that retriggers all builds.
No Android handset is attached; emulator evidence and real Windows public lookup
must be distinguished from a test on the owner's phone.
