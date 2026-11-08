# PrettyLisaVPN — iOS and macOS

**Реализовано, работа реального VPN ещё не подтверждена.** SDK builds and
Simulator screenshots are not physical VPN acceptance. See the
[acceptance record](../../docs/apple-vpn-handoff.md).

Native SwiftUI applications, shared Swift session/API logic, and real Network
Extension providers link the existing Go transports: WireGuard, AmneziaWG, SSTP,
SoftEther, SS2022, VMess, VLESS, REALITY, Hysteria 1/2, Salamander and relay variants.
Network Extension alone owns system routes/DNS. A bounded socketpair transports
packets between the **public** NEPacketTunnelFlow API and the pinned Darwin TUN
implementation; no private descriptor lookup, companion app or success timer.

## Build and run

Requirements: macOS 14+, Xcode with iOS 17+ SDK/Simulator, Python 3, Go **1.27.3**
(matching `engines/managed/go.mod`), XcodeGen **2.44.1+**. Install XcodeGen with
`brew install xcodegen`; select Xcode with
`sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.

```bash
cd apps/apple
bash scripts/build.sh simulator CODE_SIGNING_ALLOWED=NO
open PrettyLisaVPN.xcodeproj
# Select PrettyLisaVPN-iOS, an iPhone Simulator, then Run.
swift test
swift run LiveAPIProbe # real unauthenticated health/version/auth fence; no VPN proof
python3 scripts/check-project.py
bash scripts/ui-review.sh
```

Default launches use real HTTPS API/OTP at **https://api.prettylisavpn.com**.
Simulator Connect reports the physical-device requirement before reserving quota.
For explicit **Debug Simulator simulation**, add `-simulate-vpn` and `YES` as two
separate scheme Run → Arguments. A persistent localized banner says **«Симуляция VPN — трафик не защищён»**;
Settings exposes disconnected/connecting/connected/disconnecting/error/reconnecting
scenarios. Separately add `-ui-fixtures` and `YES` for synthetic account UI tests.
Keep each defaults flag paired with its value, especially before `-theme light`
or `-theme dark`: AppKit can treat an orphan value as a document-open request. Neither
flag is active in Release. Fixture data never enables a real tunnel.

## Signing — perform locally, never send private keys/passwords in chat

iOS targets use `App-iOS.entitlements` / `Tunnel-iOS.entitlements`; the macOS
App Sandbox permissions stay in `App.entitlements` / `Tunnel.entitlements`.
The Mac provider enables both network client and server permissions because
[sandboxed UDP needs receive permission](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.network.client).

1. Copy `Config/Local.xcconfig.example` to gitignored `Config/Local.xcconfig`.
   Set `DEVELOPMENT_TEAM` and a `BUNDLE_ID_PREFIX` you own. API overrides must use
   HTTPS; no ATS exception or TLS bypass is provided.
2. Register `<prefix>.ios`, `<prefix>.ios.tunnel`, `<prefix>.macos` and
   `<prefix>.macos.tunnel`. Enable **Network Extensions / Packet Tunnel** on all
   app/provider identifiers, and **Keychain Sharing** with common access group
   `$(AppIdentifierPrefix)<prefix>.apple.shared`. Sign each app/provider pair with
   the same Team. App Groups are unnecessary: configuration uses Keychain, not
   shared files/defaults. Refresh credentials never reach the provider.
3. Select the Team in Xcode Signing & Capabilities for all four targets. Let Xcode
   create development provisioning profiles. Include the physical iPhone UDID;
   enable Developer Mode on the phone if requested.
4. iPhone: `bash scripts/build.sh ios -allowProvisioningUpdates`, then select the
   physical device in Xcode and Run. Mac: `bash scripts/build.sh macos
   -allowProvisioningUpdates`, then run `PrettyLisaVPN-macOS` / My Mac.
5. Remove debug arguments, sign in with your own email OTP, choose a country,
   Connect and approve the OS VPN-configuration prompt. Denial remains an error.

macOS uses an embedded **app extension (.appex) for Xcode development / Mac App
Store distribution**. It is not a notarized Developer ID installer. Direct
Developer ID distribution requires system-extension packaging/activation; do not
ship this `.appex` build as such. No SIP/security disabling is required. See
[Apple TN3134](https://developer.apple.com/documentation/technotes/tn3134-network-extension-provider-deployment).
A VM must actually support signed Network Extensions and network access.

Backend **0.33.0** is required before live Apple VPN tests: previous backend
source only admits ANDROID/WINDOWS VPN principals. OTP and account pages working
on an older backend do not prove Apple VPN admission. The additive gate change
requires no database migration. PR #51 was merged into develop on 2026-11-04;
run `41822292784` deployed `05d945dbd5da35f1c85523d00b4ab57415882a3c`, and the
public `/version` returned `0.33.0-dev.41822292784+g05d945dbd5da35f1c85523d00b4ab57415882a3c`.
This clears the backend admission prerequisite, not physical VPN acceptance.

## Required live acceptance on BOTH platforms

Record source/build SHA, CI run/attempt, OS/device, signing channel, protocol and
country. Do not attach raw configuration, OTPs, tokens, private keys, packet
captures or browsing history. Free acceptance sessions consume real quota.

| Step | Required evidence |
| --- | --- |
| Baseline | Ordinary internet works; note original public IPv4. |
| OTP → country → Connect | Real lease READY, consent granted, provider starts. |
| Tunnel | Connected requires OS status, bidirectional packet counters and fresh authenticated probe matching `expected_egress_ips`; independent browser IP check matches. |
| Traffic | Safari websites and another internet app work; exercise TCP/UDP. |
| DNS | A fresh name resolves using configured tunnel DNS. Check leaks on the upstream test network without collecting browsing history. |
| IPv4/IPv6 | IPv4 goes through VPN; IPv6 is captured/blocked because current nodes are IPv4-only. Repeat on an IPv6-capable upstream. |
| Sleep | Lock iPhone >5 minutes, sleep/wake Mac, repeat internet/IP checks. |
| Network change | Wi-Fi → cellular → Wi-Fi on iPhone; alternate uplink on Mac. Reasserting remains until encrypted connectivity recovers. |
| Failure | Unreachable server/network produces a truthful error/reconnecting state. |
| Disconnect | VPN goes down; original routes/DNS/egress and internet return; peer removal reaches CLOSED before another allocation. |
| Reconnect | Repeat 3 times, one peer at a time, no stale routes or double reservation. |
| Expiry/revocation | Free deadline/UTC midnight/device revocation stop server access; UI reconciles on foreground. |

## Boundaries and security

- iOS **0.3.0**: `Config/iOS.xcconfig`; macOS **0.2.2**:
  `Config/macOS.xcconfig`. UI reads `CFBundleShortVersionString`; build number is
  `CURRENT_PROJECT_VERSION`, distinct from SemVer/SHA/run/attempt.
- Backend owns access, quota and country availability. CryptoKit generates keys
  locally. Keychain holds credentials/configuration with device-only accessibility.
  No tokens/keys/destinations/DNS queries are logged. API redirects are rejected.
- Refresh rotation is serialized and durably marked before submission. Ambiguous
  rotation requires OTP instead of replay. Timed-out connection creation discovers
  `/current` and confirms cleanup before allocating another peer.
- Extension owns expiry and path-change recovery without account tokens. Current
  backend advertises `heartbeat_required=false`; legacy heartbeat-required leases
  are rejected rather than silently expiring when iOS suspends the UI.
- Full IPv4 tunnel, captured/blocked IPv6. Domain/per-app split routing from the
  newest Android/Windows clients is **not exposed** in this Apple build. Apple's
  per-app mode requires managed deployment; arbitrary direct forwarding needs a
  separate Apple-policy-compatible design.
- Real subscription/pricing/paid period/Platinum data are displayed. Subscription
  management opens the protected web portal via a one-use authenticated handoff.
  Provider configuration remains disabled until merchant acceptance; App Store
  distribution/StoreKit decisions remain separate. No invented payment success.
  See [billing contract](../../docs/platega-billing.md).
- Support uses the real multipart/status contract and an account-scoped AES-GCM
  journal with a Keychain key, deleted after acceptance; expired drafts are removed
  on their next access after 30 days. No Windows-only diagnostics. Account messages ACK account/revision only
  after explicit action. Supported actions route to subscription/settings/about.
- Six existing locales derive from Android. New copy is in `Config/AppleStrings.json`;
  regenerate with Python + Pillow: `python3 scripts/sync-resources.py`.
- MIT engine, pinned Xray MPL-2.0 corresponding source and dependency notices
  accompany CI artifacts. Keep that exact source archive with every distributed
  binary. Go's memory limit is a GC target, not an iOS memory guarantee; device
  stress/jetsam checks remain mandatory.

CI `.xcresult` attachments are native UI screenshots with explicit fixtures.
Unsigned/ad-hoc device builds cannot establish a signed production tunnel.
