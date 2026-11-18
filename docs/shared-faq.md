# Shared website and app FAQ

## Scope and versions

One editorial catalogue, `content/faq/catalog.json`, supplies the same nine
questions, order, answers and link targets in Russian, English, German, French,
Spanish and Chinese to the website, Windows, Android, Chrome, iOS and macOS.
Linux and Android TV have no separate shipping FAQ screen. No backend, database,
analytics, entitlement, VPN engine or billing behavior changes.

This text/formatting correction is PATCH: website 0.7.0 → 0.7.1;
Windows 0.31.1 → 0.31.2; Android 0.30.1/code 60 → 0.30.2/code 61;
Chrome 0.5.0 → 0.5.1; iOS 0.6.0 → 0.6.1; macOS 0.5.0 → 0.5.1.
Backend remains 0.53.0 and dashboard 0.18.0. Base: develop `4c6055d`.

“How to start?” stays; only the Android/Windows qualifier and those two download
links are removed. PREMIUM retains uppercase and an emoji, with its benefits on
separate paragraphs. The answer identifies benefits also available in FREE.
Protection, missing OTP and payment/refund answers use paragraph breaks. The
connection troubleshooting answer has four numbered steps and a support link.
The simple selective-traffic question explains the home controls, services,
separate lists, custom domain patterns and reconnecting after saving.

The shared copy explicitly distinguishes Windows/Android selective routing,
DEMO all-traffic-only, current Apple full-tunnel routing, and Chrome browser-only
protection. Reset/selection advice is conditional on controls being available.
Manual website renewal replaces the obsolete FAQ about cancelling auto-renewal;
this does not implement or activate payments.

## Maintaining synchronization

Edit the canonical catalogue, then run `python content/faq/sync.py` and commit
the generated copies. `python content/faq/sync.py --check` fails if any locale,
ordering, paragraph text, link count/target or generated platform copy diverges.
The dedicated push/PR workflow enforces this. Bundles contain their own copies,
so installed apps and source archives do not fetch FAQ over the network or depend
on a checkout-relative runtime path. Apple resources remain compatible with the
existing Android-to-Apple resource generator.

Links use semantic targets rather than a question's numeric position. Support
opens the existing native form (Windows DEMO retains its registration guard);
the website uses the existing support mail address. Payment rules open the
localized public document through existing browser integrations. Apple uses
attributed text and intercepts its internal support link before opening URLs.
No user data, browsing destinations or additional API calls are collected.

## Verification and release handoff

Local checks cover catalogue synchronization, six-language Android/Apple
resources, website rendering/build/link tests, Windows/Chrome lint, TypeScript,
unit/component tests and builds. UI checks cover uppercase PREMIUM, paragraphs,
all nine questions and support/document navigation. Current-source Windows
native capture, Android emulator instrumentation and Apple SDK/UI builds run in
CI; browser fixtures do not claim live VPN acceptance.

The PR records final product HEAD, actual temporary merge/build SHA, all Actions
events/jobs, run/attempt and artifact links after the final push. The initial handoff
did not claim deployment; the authorized release is recorded below. Future
publication requires an authorized develop merge/site deployment; client publishers
must then be checked against their original source/run/attempt and stable
dashboard/public downloads. Apple labels
remain unsigned. No backend migration or VPN-node follow-up is needed.

## Development release — 2026-11-18 UTC

The owner authorized merging PR #106 through develop, updating the website and
checking the FAQ in published clients. The reviewed PR head was
`6c197de121f9c14f63f4e4c77d2b77bfefa8bdbb`; the actual merge/build source is
`2ac1e72b31ef66e8caba10cc4391bd759e11fe5c`. All published builds below come from
successful develop **push** runs, attempt **1**; no PR artifact was promoted.

Website **0.7.1** was atomically activated at **2026-11-18 09:37 UTC** from
artifact `14414354794`, run `44277188302/1`, ZIP digest
`sha256:cfc0707e312c1c73f78632755eabf201e50b2084b59c54026a0452d361637a2d`.
Its 127 files are retained in
`/opt/prettylisavpn/public-website/releases/2ac1e72b31ef66e8caba10cc4391bd759e11fe5c-44277188302-1`.
The previous 0.7.0 directory remains available for rollback through the relative
`current` symlink. No Caddy/backend restart was needed.

| Component | Version | Successful run / attempt | Artifact |
| --- | --- | --- | --- |
| Website | 0.7.1 | [44277188302](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188302) / 1 | 14414354794 |
| Windows | 0.31.2 | [44277188368](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188368) / 1 | 14416270633 |
| Android | 0.30.2 / code 61 | [44277188375](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188375) / 1 | 14414923161 |
| Chrome | 0.5.1 | [44277188280](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188280) / 1 | 14415671119 |
| iOS | 0.6.1 | [44277188354](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188354) / 1 | 14417346368 |
| macOS | 0.5.1 | [44277188354](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188354) / 1 | 14417630680 |

The final release audit covered **6 workflows, 17 jobs,
17 check-runs and 6 check suites**, including all five client publishers.
The only skipped jobs were the explicitly dispatched Android real-tunnel probes;
this FAQ release does not claim live VPN/payment acceptance. Shared FAQ
synchronization also passed in [run 44277188365](https://github.com/romankenig/PrettyLisaVPN/actions/runs/44277188365).

### Published-byte verification

The authenticated dashboard and public download catalogs matched. Every binary,
source archive, license companion and iOS Simulator archive was fetched through
its stable HTTP route and matched its catalog hash/size. Public Windows, Android
and Chrome files matched the authenticated copies. The exact published bytes
also matched the original successful CI artifacts and their build identities.

| Published file | SHA-256 |
| --- | --- |
| `android.apk` | `6327d7fa79e4af4c4ee56e6caab0fc65a4f310eb2183171625063c51f81d11d4` |
| `android-sources.tar.gz` | `be5d3d6346f55c991d6b86010cb83445d204f5160d8af925b86fe976b7672720` |
| `windows.exe` | `0ac03c114f2db96920cddf4ee55e52cfb9e5336c423db33b4c8c40e38af9e422` |
| `windows-sources.tar.gz` | `f1ca3f49aa9e9fe6ab66e9924a603933f312f1e72a381d4bfd5817eabd91ff9d` |
| `windows-licenses.txt` | `183adac21e7d96c508c8fd34d394b7b6708bc81564ad1bad61ab66143a008cd2` |
| `chrome-extension.zip` | `4840be55b45cc2f6f95e13572cc8e068f3a3302811c249facd89f61264aa2391` |
| `ios-unsigned.zip` | `123f6ef008e3e1522c5e702937ab65d90e272c489af878ca034a6348f1d7d69e` |
| `ios-sources.tar.gz` | `34898608573e7a2cd07cddbeea1e2e39221a341e381344a9e3e9b303ad91de5c` |
| `ios-simulator.zip` | `050599826cd4cb065c35f3760d8407262e7855eb220d937736933d524452f2be` |
| `macos-unsigned.zip` | `cb0631683241131dd66a19a7fc72ab5f253a11415f401e8484763c208b2538e0` |
| `macos-sources.tar.gz` | `34898608573e7a2cd07cddbeea1e2e39221a341e381344a9e3e9b303ad91de5c` |

### FAQ equality and presentation

- Live website: all nine questions, complete answers, paragraph boundaries and
  support/payment links matched the catalogue in ru/en/de/fr/es/zh. Browser
  review at 375 and 1280 px found no horizontal overflow or page errors.
- Windows: read the Tauri asset map from the executable inside the published
  NSIS installer, decompress the bundled JavaScript and compare all six FAQ
  arrays, including order and semantic links. No user account or VPN was opened.
- Chrome: compare the six FAQ arrays in the JavaScript from the published ZIP.
- Android: official aapt2 8.11.1-12782657 read the published arm64 APK; all
  108 compiled question/answer strings matched the catalogue exactly.
- iOS device, iOS Simulator and macOS: read the actual bundled localization
  files in each published ZIP; all 108 FAQ strings matched in every package.

The Apple downloads retain their existing **unsigned device/macOS** labels.
The iOS Simulator ZIP is a distinct companion and is not a physical-device
package. No App Store/TestFlight publication or Apple signing is claimed.
Linux/Android TV have no separate shipping FAQ screen in this repository.

Server-side receipts and original CI ZIPs are retained under
`/opt/prettylisavpn/incoming/faq-106-evidence`; the website activation receipt is
under `/opt/prettylisavpn/website-deployments/faq-2ac1e72b31ef66e8caba10cc4391bd759e11fe5c-44277188302-1`.
This release-record change is docs-only, with versions unchanged. Backend remains
0.53.0, dashboard 0.18.0; no database migration or VPN-node update is needed.
