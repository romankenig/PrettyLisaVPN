# Website payment-unavailable page — 0.7.0

## Scope and versions

Website **0.6.4 → 0.7.0** (MINOR: dedicated checkout outcome page). Backend,
dashboard and native/browser client product versions are unchanged. The Chrome
browser acceptance script is updated only to exercise the website. No schema,
API, provider configuration or payment activation changes are required.

The owner requested this Russian copy:

> временно оплата недоступна. мы напишем вам на почту, как заработает

The heading and supporting paragraph use that text, with matching translations
in English, German, French, Spanish and Chinese. No demonstration wording,
success checkmark or simulated receipt is shown.

## Behavior and compatibility

- Homepage Pay keeps the selected currency through email/OTP authentication.
- The authenticated purchase button opens `/account/unavailable/` (with the
  language prefix) when live checkout is unavailable. Back returns to the same
  localized account/currency; Home returns to the localized homepage.
- Reload and language changes retain the unavailable route. Legacy
  `/account/success/?preview=1` URLs canonicalize to it; the old flag is removed.
- Session expiry still shows sign-in. Pending operations and original saved
  commands retain recovery precedence, so this page cannot misrepresent an
  unresolved real payment. Ordinary provider-result URLs are unchanged.
- Disabled/sandbox providers, unsupported currency, missing offers, blocked
  optional storage and overview outages cannot authorize a new payment. A fresh
  LIVE capability/quote continues to use the existing consent and provider flow.
- The page sends no payment command, creates no journal or entitlement, and does
  not send mail now. Notification delivery when the provider becomes available
  remains operational follow-up; no mailing-list endpoint or automation is added.

## Verification and publication

Validation covers the static routes, six-language copy, desktop/mobile rendered
purchase path, reload, legacy URLs, authentication, pending recovery and absence
of payment side effects. Existing LIVE fixture checkout, cancellation and retry
coverage remains in the browser acceptance script. Caddy checks use an isolated
container; no real payment is used for tests.

Local results: website syntax checks, all 25 Node tests and the 102-page build
passed. The existing billing browser acceptance passed OTP → Pay → unavailable,
six languages at 320/390/1280px, reload/Back, legacy preview links, blocked storage,
overview outages, pending precedence and real-provider fixture recovery. ESLint
and targeted Prettier checks passed. Desktop and mobile renders were inspected.
The local Docker Linux engine was unavailable; isolated Caddy execution is
required in both website CI runs before completion.

The task PR records the verified product HEAD, actual build SHA/run/attempt,
artifacts, all Actions runs/jobs and publication status. PR merge builds and push
artifacts are distinct. Only a verified push artifact may be published; this
document alone does not claim deployment or provider activation.
