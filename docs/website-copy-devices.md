# Website copy and device presentation — 0.5.5

## Scope and versions

Owner request dated 2026-11-14. Website **0.5.4 → 0.5.5** (PATCH): copy,
typography and device presentation in existing pages. Backend **0.40.1**,
Windows **0.28.1**, Android **0.27.3** and Chrome **0.2.1** remain unchanged.
Base source: `6868e4849ee1795863e3d6ff1a3caca1c054eb01`.
No API, database, authentication, payment-provider or download route changes.

Owner follow-up in the same review keeps version **0.5.5** unchanged: every tab
is titled exactly `PrettyLisaVPN`. Build-time favicon variants preserve the
canonical lock geometry: Christalle `#2c016d` for light themes and Mercury
`#e4e4e4` for dark themes. The existing external script follows the browser's
`prefers-color-scheme` preference on initial load and live changes. Separate SVG
files avoid inline styles and keep CSP unchanged; the page's logo is untouched.
Browser acceptance verifies both initial themes and switching in both directions.
Node/Caddy checks cover both generated assets and all 96 titles. Custom browser
themes can only be detected when the browser exposes their color scheme.

The final product HEAD, push build SHA/run/attempt, separate PR merge build,
artifacts and all CI jobs are recorded in the task PR after the final push.
Neither the baseline build nor the native screenshot builds verify the new
website code. Merge and production publication remain separate owner actions.

## Implemented presentation

- Plain “запуск скоро”; hero “ваш интернет. ваши правила.” with the requested
  everyday/multiple-devices subtitle.
- Owner-approved “меньше настроек. больше свободы.” with one-tap connection,
  automatic **or manual** server choice, selective protection and five devices.
- A shared CSS laptop/phone composition in both homepage sections. The images
  are native captures; device frames are decorative HTML/CSS, with no image
  generation, cropping, retouching or invented connected state.
- “1 аккаунт” is emphasized within “1 аккаунт объединит их все”.
- “доступные тарифы”; `premium ⭐`, `free 🕊️`, `demo ⏳`. Benefits and daily
  limits are copied from Android's localized `plan_*` strings. The homepage and
  purchase portal share the same Premium benefits, checked against Android.
- Decorative section labels, screenshot captions and visible reference-price
  explanations are removed. Portal controls, result pages, document titles and
  headings use lowercase copy. `PrettyLisaVPN` keeps its required spelling.
- All six site languages are updated. The privacy policy retains its separate
  consent rule; only its informational-label phrase is removed.

Public catalog/cache display fallback and immutable subscription prices are
unchanged. A live payment still requires a fresh account offer and explicit
provider capabilities. Existing payment-preview disclosures, recurring consent,
pending-operation recovery and server verification remain intact.

## Native asset provenance

Exact hashes, sizes, original paths and URLs are in
[`sources.json`](../sites/public-website/assets/screenshots/sources.json).

- Android **0.27.3**, API 35 native Compose capture, run **43598763038/1**,
  source/build `6868e4849ee1795863e3d6ff1a3caca1c054eb01`, artifact **14115439477**,
  `account-api/home-windows-connection.png`.
- Windows **0.28.1**, native Tauri window, run **42827276053/1**,
  product source `c14e67783d5b522686c4f0ae6eb78dac34bf7f82`, PR merge build
  `400b13a30038d515127e3329b33d389caaccdc73`, artifact **13770172745**,
  `13-home-en.png`.

Both show synthetic accounts and a disconnected UI. No real personal data,
credentials or live VPN claims are introduced. No native application code changed.

## Verification and follow-up

- Website syntax checks, 25 Node tests and a build of all 96 localized pages.
- Tests compare all localized plan benefits with Android, check device pairs,
  exact capture hashes, links, escaping, routes and payment authority.
- Existing browser acceptance covers all six languages at 320/390/1280 px,
  RUB/USD, OTP, account states, payment preview, consent, response recovery,
  immutable prices, cancellation, outages and blocked optional storage.
- Interactive desktop/mobile review verifies the hero, device frames and account
  emphasis. Browser captures are in the Chrome workflow's `review/billing/`,
  including `00-features-*`, `00-download-*`, pricing and purchase screens.
- JavaScript/JSON formatting, acceptance-script lint, diff review and isolated
  Caddy routing checks are required before final CI sign-off in the PR.

Backend follow-up: none for this presentation task. Real merchant activation
and actual payment acceptance retain their existing separate scope.
