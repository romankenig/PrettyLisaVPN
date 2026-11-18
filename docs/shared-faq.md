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
events/jobs, run/attempt and artifact links after the final push. This document
does not claim deployment. Publishing requires a separate authorized develop
merge/site deployment; client publishers must then be checked against their
original source/run/attempt and stable dashboard/public downloads. Apple labels
remain unsigned. No backend migration or VPN-node follow-up is needed.
