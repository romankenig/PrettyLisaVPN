# Chrome countries/settings polish — 0.4.0 / website 0.6.1

Task baseline: `4e4a79feb721416c6236ab472c1933b9961b979f` (the verified 0.3.2
fixes in PR #88). This separate UI task adds Advanced Settings and a custom
country picker: Chrome **0.3.2 → 0.4.0 MINOR**. Website **0.6.0 → 0.6.1 PATCH**
adds factual browser privacy disclosure. Backend started at **0.42.0**; the later
sync with develop `ea1498a1` inherits **0.44.0** from the independently merged
analytics PR #86. This task does not change backend/schema or other client versions.
The earlier device/proxy fixes remain included. The 0.4.0 push artifact at
`57f94292` passed real DEMO/device/Advanced Settings acceptance on that deployed
0.44.0 backend; final merged-head CI identity is recorded separately in PR #88.

## Interface and compatibility

- Reuse the existing licensed Circle Flags sprite from the Windows client, bundled
  locally. No remote flag requests and no dependence on Windows emoji flag support.
- A keyboard-accessible destination picker renders the existing API countries,
  preserves availability, and opens above the trigger when below would be clipped.
  Autopilot remains a globe. The connection row uses the same localized name/flag.
- Advanced Settings follows Android's connection-method grouping and navigation.
  Only HTTPS proxy is supported in independent Chrome, so it is selected/read-only.
  No invented native methods, ineffective toggles or transport/backend changes.
- The Home transport caption and About privacy accordion are removed. Existing
  scope/FAQ and localized document links remain. Plans use shared Android labels:
  DEMO ⏳, FREE 🕊️, PREMIUM ⭐ and PLATINUM 💎, including subscription headings.

## Live US investigation — 2026-11-15

Read-only inspection of the running fleet confirmed US is enabled/FREE with
READY managed/native methods, but its managed configuration has no proxy_host.
DE has the IP proxy address and NL the proxy hostname. The country API filters
by browser capability, so US is absent by design rather than dropped by the UI.
The [earlier transport handoff](chrome-extension.md#current-ip-fallback--2026-11-05)
records a stalled full-page transfer on US; its proxy capability remains disabled
until complete direct acceptance succeeds. Do not advertise US as working or
enable it merely to populate a menu. The browser fixture includes US to prove
that a country advertised by the API appears with the proper flag and name.

Follow-up: investigate the US data-plane stall, repeat complete HTTPS/WSS and
cleanup acceptance, then enable proxy_host and verify real Chrome allocation.
This task inspected fleet state only; no node/configuration rollout occurred.

## Privacy policy

The live six-language policies were checked on 2026-11-15. Clause 2.3 already
excluded browsing history, destinations, DNS queries and packet contents. The
removed extension text also explained all-sites permission and WebRTC, which
were missing from the policy. New localized clause 2.6 carries those facts plus
network-prefetch suppression and restoration of the applicable browser settings.
Legal/commercial approval flags are unchanged; adding source text does not prove
website publication. The policy link remains available from Login and About.

## Separately authorized account maintenance

The owner's legacy Yandex aliases existed as distinct accounts before alias
support: the first held PLATINUM and the later held FREE. This explained the
displayed FREE entitlement; changing only the label would have been incorrect.
The owner explicitly approved consolidation into the first address with PLATINUM.

After a private backup, source auth was revoked and its one lease was confirmed
CLOSED with node removal. A transactional rehearsal performed the transfer and
rolled back, checking restored source rows. The final transaction transferred
two devices/auth sessions, one closed lease and seven product events; daily
observations used the existing newest-observation rule. The empty duplicate FREE
subscription was removed only after proving no subscription/payment dependents.
All other source references were checked empty before removing the duplicate user.
No financial operation or charge was performed.

Post-commit checks confirmed a single account, all provider aliases resolving to
its first address, five active devices, unchanged PLATINUM dates and canonical
sessions, and preserved historical rows. The source sessions require a fresh OTP
login. Restricted operational backups remain on the host; no account IDs, tokens,
private backup contents or temporary maintenance scripts enter repository artifacts.
This is a scoped data reconciliation, not a new general account-merge endpoint.

## Verification and release evidence

Extension formatting/lint/types, 52 existing lifecycle/parser/worker tests and
the production build are required. Installed Chromium covers selection by mouse
and keyboard, unavailable countries, dismissal, six-language connected labels,
all plan emojis/casing, Advanced Settings and return navigation, document links,
and absence of removed text. Connected presentation screenshots are explicit
fixtures, not evidence of live proxy traffic. Existing full lifecycle and billing
portal browser scenarios still run. Website checks/tests/build cover all 96 pages
and six numbered policy translations; CI additionally verifies Caddy routing.

Final source SHA, actual push/temporary merge build SHA, run/attempt, artifacts and
all workflows are recorded in PR #88 after its final push. This task does not
merge the PR or publish Chrome 0.4.0 / website 0.6.1 without the release instruction.
