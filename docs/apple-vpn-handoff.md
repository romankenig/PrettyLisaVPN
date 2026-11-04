# Apple VPN port — acceptance record

**Реализовано, работа реального VPN ещё не подтверждена.** Full acceptance requires
real tunnels on a physical iPhone and a suitable signed macOS environment.
Implementation, SDK compilation and UI screenshots are distinct evidence.

Baseline: `600988831c100c8d6db96477346b37ec407deb3e` (previous task's merged PR #50).
Independent branch: `codex/apple-vpn`. iOS absent → **0.1.0**, macOS absent →
**0.1.0**, managed engine **0.5.2 → 0.6.0**, backend **0.32.0 → 0.33.0**.
Windows **0.25.2**, Android **0.21.2**, website **0.2.2** unchanged.

Android is Kotlin and Windows React/Rust, so native SwiftUI with shared Swift
session/API code replaces neither existing UI. The repository's real Go engine
is reused through a Darwin C archive and Network Extension. This preserves wire
protocols, server-issued profiles and relay methods. No backend schema change.

Existing OTP/session, `/me`, `/devices`, `/vpn/countries`, `/vpn/sessions` and
`/probe`, billing overview, messages and support APIs are used. Apple sends real
IOS/MACOS device identities. The backend's old principal allowlist would reject
them; 0.33.0 extends the same admission/renewal fences, with unit and PostgreSQL
integration coverage. **The reviewed backend patch must actually be deployed**
before live Apple VPN testing; implementing or pushing it is not deployment.

Public HTTPS checked on 2026-11-03: `/health` reports `ok`; `/version` reports
`0.32.0-dev.41623185534+g34e496f0fa71bd4f636dd814664f46ae3f931d0b` in development.
The Swift `LiveAPIProbe` command checks health/version and the unauthenticated
401 fence using the production Apple HTTP adapter. This does not verify OTP,
account data or a VPN tunnel. Final CI results belong in the PR evidence record.

The initiating environment is Windows with no Xcode, physical iPhone, Apple Team
or provisioning profiles. No private credentials are requested in chat. Exact
local setup and acceptance steps: [Apple README](../apps/apple/README.md).
macOS `.appex` targets signed Xcode development / Mac App Store. Developer ID
direct distribution needs a system-extension package; see
[Apple TN3134](https://developer.apple.com/documentation/technotes/tn3134-network-extension-provider-deployment).

[PR #51](https://github.com/romankenig/PrettyLisaVPN/pull/51) records final checked HEAD, all Actions events/jobs and exact build
SHA/run/attempt after the last push. PR temporary merge SHA is distinct from the
source head. CI emits `build-identity.json` with `real_vpn_verified=false`.
No historical Android/Windows artifact proves Apple behavior. Native UI reviews
use explicit fixtures. Local backend tests/format/lint and portable Apple source
checks do not prove Apple compilation or packet routing.

| Source feature | iOS | macOS | Verification | Limitation |
| --- | --- | --- | --- | --- |
| OTP/restore/refresh/logout | Shared Swift | Shared Swift | Concurrency, rotation ambiguity, 401 tests | Live owner login pending |
| Profile/Free/Premium/Platinum | Native API UI | Native API UI | Typed models, labeled fixtures | Live quota refresh pending |
| Countries/configuration | Existing API | Same | Config/route/key validation tests | Deploy Apple admission patch |
| VPN and relay protocols | Packet Tunnel + Go | Packet Tunnel + Go | SDK/core CI when successful | Physical/signed tunnels unverified |
| Connected/IP/DNS | OS + counters + egress proof | Same | Lifecycle test | Live leak/routing tests pending |
| Disconnect/reconnect | Stop + confirmed removal | Same | Duplicate start/cleanup tests | Real sleep/network changes pending |
| Devices | List/revoke/confirmation | Same | API + backend fencing tests | Live revoke pending |
| Subscription/prices | Read-only API overview | Read-only API overview | Contract projection | Purchases/management not exposed |
| Messages | JSON v1/account-revision ACK | Same | Typed projection | Live publication pending |
| Support/images | Multipart/status/journal | Same + native file picker | Multipart privacy tests | Delivery depends on backend SMTP |
| Native UI | Dynamic Type, adaptive navigation | Sidebar, resize, menus/settings | Native CI screenshots when successful | Physical accessibility pending |
| Localization | Six existing locales | Same | Generated resource checks | Native layout review pending |
| Split routing | Full tunnel only | Full tunnel only | Core IPv6-block policy | Domain/per-app controls not ported |

Owner actions: configure Apple Team/profiles locally, install on a real iPhone
and signed Mac, approve VPN, deploy the reviewed backend gate through the normal
separate workflow, then record **every** live checklist row on both platforms.
No source-only feature is presented as a successfully tested real VPN.

Signing configuration separates iOS from macOS App Sandbox entitlements. The Mac
provider grants both outgoing and incoming networking for encrypted UDP transport;
unsigned/ad-hoc UI checks do not validate these entitlements against owner profiles.

Native validation reached source `2464d5ec5417931eceeec55cd0dc31c76de53c38`
in Apple run `41810681639`, attempt 1: 18 shared Swift tests, four Apple SDK
builds and all four Mac UI tests passed (OTP launch, fixtures, forced appearance,
navigation and window resizing). Native screenshots exposed a remaining AppKit
chrome appearance mismatch; its correction must be checked by subsequent runs.
The PR contains the final evidence, including any superseding source/build SHA.
