# Chrome UI, DEMO and public downloads

Task date: 2026-11-14. Source baseline:
`6868e4849ee1795863e3d6ff1a3caca1c054eb01` (develop).

| Component | Before | After | Reason |
| --- | --- | --- | --- |
| Chrome extension | 0.2.1 | 0.3.0 | Six languages, guest entry, document navigation |
| Backend | 0.40.1 | 0.41.0 | Chrome DEMO admission and shared email identities |
| Public website | 0.5.4 | 0.6.0 | Public Chrome download and publisher version metadata |
| Other clients | unchanged | unchanged | No shipped client code changes |

No database migration: schema remains 0048. Existing OTP/native/paid flows and
browser-only HTTPS proxy transport remain compatible. Chrome DEMO needs backend
0.41.0; the old backend rejects that admission instead of fabricating access.
Backend deployment and PR merge are separate from the owner's explicit website
publication request. Final source HEAD, actual artifact SHA/run/attempt, all CI
runs and publication evidence belong in the task PR.

## Implemented behavior

- Lowercase interface copy on every extension screen; preserve PrettyLisaVPN,
  entered email, identifiers and code. The stored account address remains intact.
- Russian, English, German, French, Spanish and Chinese, matching Android's
  supported set. Small local SVG flags remain visible on Windows without emoji
  font support. The menu supports keyboard focus, Escape and outside dismissal.
- Login and About link to the localized official website, terms, privacy,
  refunds and payment documents. Only fixed HTTPS destinations are generated.
- Guest entry uses the real `POST /auth/demo`, platform `CHROME_EXTENSION`.
  The worker persists the returned session before responding. A local installation
  UUID is namespaced and SHA-256 hashed; no hardware/browser fingerprint is read.
  Reopening the extension or restarting the worker keeps the same guest identity.
- Existing DEMO allowance is 15 minutes per UTC day, AUTO only, one device,
  no split routing. Backend allocation, quota reservation, expected-egress probe
  and confirmed cleanup also apply to guest HTTPS proxy leases.
- Guest country selection, subscription and support lead to registration:
  confirmed connection cleanup and logout precede the existing email OTP screen.
- Removed the explanatory persistence paragraph, sign-in-tab link and redundant
  HTTPS proxy settings card at the owner's request. The former link opened the
  same UI in a normal tab for switching to webmail; the card described browser
  proxy scope. Neither was a second transport or a subscription requirement.
  Scope remains in Home/About. State persistence and the HTTPS proxy still work.
- The public Chrome page offers the fixed `/downloads/chrome-extension.zip`
  file, localized unpacked-install instructions, version, size and SHA-256 from
  the existing publisher's `index.json`. Store publication is still pending.
  No unrelated Windows screenshot appears on this page.

The server namespaces Chrome guest identities separately from Android/Windows.
Clearing extension storage, uninstalling, or using a new browser profile can create
a new identity; this follows the installation-identity model and is not hardware
anti-abuse proof. Local tests do not establish live VPN reachability.

## Validation and release

Local validation includes extension format/lint/types/unit tests/build, installed
Chromium fixtures for six languages, DEMO, OTP and worker/browser restarts;
backend unit/type/lint checks and PostgreSQL/Valkey integration tests for aliases,
guest admission, proxy allocation and quota; website unit/build/Caddy routing
checks and desktop/mobile screenshots for all six Chrome download locales.
Screenshots use API fixtures and identify UI behavior only.

The site and downloads have independent identities. The site displays the version
actually present in the publisher index, never the version promised by this PR.
Successful develop Chrome builds update that index and ZIP through the existing
publisher. This updates the website download; an unpacked installation still needs
the user to replace its files and reload it. This is not Chrome Web Store auto-update.

Retain the previous static release and Caddy config during website publication,
verify their replacements and public ZIP/hash, and keep backend/container identity
unchanged. Record actual observations in the PR, without calling source changes
a deployment. Existing [proxy DNS/rollout work](chrome-extension.md#operator-rollout-and-real-acceptance)
remains separate.

## Deferred task: Chrome disables or hides the unpacked extension

Owner explicitly allowed deferral on 2026-11-14 if diagnosis is not practical.
Reported environment: Google Chrome; unpacked extension loaded from Downloads;
folder and its contents remain intact; no error is shown. Sometimes after closing
the extension window the extensions-page enable toggle is off and the extension
is absent from the puzzle menu. Root cause is **not established or fixed**.

Follow-up acceptance:

1. Record Chrome version, exact extension ID/build/path and whether the enable
   toggle actually changes, or only the toolbar pin / worker activity changes.
2. Reproduce using the action popup, a normal extension tab and a separate clean
   profile; compare with the stable extracted folder documented on the website.
3. At the transition capture extension errors and Chrome's extension-management
   disable reason / relevant policy state, without collecting browsing history.
   Check whether a file update, explicit reload, browser restart or external
   software intervention coincides with it; do not assume a cause from location.
4. Distinguish normal Manifest V3 idle worker termination from disabled extension
   state. Existing automated tests stop/restart the worker and retain auth; they
   do not prove that this user's Chrome enable-toggle issue is solved.
5. Only after evidence, implement the smallest fix and repeat close/reopen,
   worker suspend, browser restart and puzzle-menu checks on the affected build.

Chrome's [service-worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle)
documents normal idle termination; this alone is not evidence of extension removal.
