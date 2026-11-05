# PrettyLisaVPN Chrome Extension

Manifest V3 browser-only client, version **0.1.0**. The Windows client is the UI
reference: canonical logo, Rubik, purple surfaces, mint actions, sidebar Home /
Settings / About, account, country, devices, billing overview and support screens.

## Build and install

Node 24, pnpm 12.3.4:

```sh
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
node scripts/review.mjs
```

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and
select this package's `dist` directory. Pin PrettyLisaVPN and open its popup.
Chrome 120+ is required. This is an unpacked review build, not a Chrome Web Store
publication. `dist/build-identity.json` identifies the exact artifact.

Sign in using the existing email OTP. Select AUTO or an available country, connect,
and wait for the authenticated expected-egress check. Only then is the status
Connected. Disconnect restores Chrome's previous settings by clearing this
extension's overrides. Other applications and system VPN settings are untouched.

## Security and operating boundaries

- HTTPS forward proxy, never a system WireGuard tunnel or a native helper install.
- Publicly trusted, name-verified TLS; unique short-lived credentials per lease.
- Backend >= this task's 0.34.0 implementation and migration 0043 are required.
  Existing backend 0.33.0 does not admit browser proxy leases.
- Existing five-device limit, paid entitlements and account-wide Free quota apply.
- Session/refresh/proxy credentials live in `chrome.storage.session`, restricted to
  trusted extension contexts. Reopening the browser requires email sign-in again.
  Only installation UUID and language persist in local storage. No browsing data.
- Proxy credentials are provided only to the exact configured proxy host, port and
  realm. There are no content scripts, external message handlers or remote scripts.
- `<all_urls>` is required for proxy authentication on web requests; the listener
  never reads or records destinations. No history/tabs permission is requested.
- Fixed proxy settings have no DIRECT fallback. Errors remove the Connected claim;
  traffic remains blocked by the proxy until recovery or explicit Disconnect.
  Only `api.prettylisavpn.com` is a direct control-plane exception. The authenticated
  egress probe uses a separate, narrowly scoped route on `prettylisavpn.com` and
  therefore still passes through the proxy. Normal websites have no direct fallback.
- WebRTC non-proxied UDP and speculative network prediction are restricted while
  connected. Their previous settings are restored on disconnect. Chrome internal
  services and incognito are outside this extension's scope.
- Server-side DNS resolves public IPv4 only. Private/link-local/IPv6 destinations
  and ports other than 80/443/8080/8443 are rejected. HTTP, HTTPS and WSS work;
  plaintext WebSocket upgrade, arbitrary TCP/UDP and per-app routing are unsupported.
- Browser alarms renew/check every 30 seconds. Missing heartbeats revoke browser
  access after 90 seconds; independent node grants expire within 180 seconds even
  during control-plane failure. Native clients retain their existing sleep policy.
- Billing is read-only. Split routing and account-message UI are not included in
  this first browser client. Support uses the existing private backend delivery API.

## Verification

`scripts/review.mjs` loads the real built MV3 artifact in isolated Chromium. API
responses are clearly named fixtures; it checks OTP/navigation/support and honest
connection failure. Its screenshots do **not** prove live proxy connectivity.
Current live acceptance, deployment identity and required DNS follow-up are in
[the Chrome handoff](../../docs/chrome-extension.md).
