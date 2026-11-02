# Home polish — Windows 0.24.1 / Android 0.20.1

Task baseline: develop `66c26f243d6890686beb1e0d94271b5d7b849764`.
Windows 0.24.0 → 0.24.1 and Android 0.20.0/code37 → 0.20.1/code38.
PATCH: presentation changes and a shortcut to an existing subscription screen.
Backend 0.28.0, dashboard 0.5.0 and engines 0.5.2 are unchanged; no migration,
new endpoint, dependency or VPN/billing contract change is required.

## Behavior

- Windows shows only the negotiated protocol after confirmed connection.
  Addresses, encryption, MTU, keys and expandable technical details are removed
  from Home. Existing native connection diagnostics and verification remain.
- Windows interface captions, language controls, traffic selectors, connection
  attempts and method choices follow lowercase typography. PrettyLisaVPN retains
  its exact spelling; entered text, email/device identity, filenames and diagnostic
  content retain their original case.
- Android Home and subscription show Free 🆓, Premium ⭐ and Platinum 💎.
- Free accounts see a turquoise upgrade button on Home in both clients. It opens
  the existing authenticated subscription screen. Paid accounts do not see it;
  the next successful profile refresh reflects plan changes.
- The shortcut does not start a payment, disconnect VPN or change entitlement.
  Existing LIVE/provider capability checks still control purchasing. Enabling
  payment processing is outside this UI task.

## Verification and delivery

Unit/UI checks cover protocol-only output, plan-dependent button visibility,
subscription navigation, profile refresh, and Android plan labels. Native Windows
review captures the Free button and subscription destination and checks lowercase
computed styles while preserving the product name. Android instrumentation
captures all three plans and the subscription destination on supported API levels.

Source HEAD, actual CI build/merge SHA, run/attempt, jobs, screenshots and binary
artifacts are recorded in the task PR after validation. The versions above do not
by themselves claim a completed build, deployment or fresh live VPN acceptance.
No new live VPN attempt is required for this presentation-only change.
Rollback uses the previous Windows 0.24.0 / Android 0.20.0 artifacts; backend data
and client settings remain compatible.
