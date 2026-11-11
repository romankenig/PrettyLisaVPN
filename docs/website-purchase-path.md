# Website purchase path — 0.5.3

## Scope and compatibility

Website 0.5.2 → 0.5.3 (PATCH): restore a missing purchase action in the existing
subscription portal. Backend 0.40.1, Windows 0.28.1, Android 0.27.2 and Chrome 0.2.1
are unchanged. Only the Chrome browser acceptance script changes, not its shipped
application. No schema, API contract, payment-provider activation or client build
change is required.

Previously, disabled billing could leave a signed-in user with only the current
plan. Offer rendering depended on backend actions, and Pay disappeared unless a
live payment route was available. The presentation now remains useful independently
of payment availability.

## Implemented path

1. Homepage shows PREMIUM, RUB/USD monthly price and Pay.
2. Pay opens the localized account page with the selected currency in the query.
   The sign-in screen shows the same product and price beside the email/OTP form.
3. After authentication, FREE, DEMO and PLATINUM see a prominent PREMIUM purchase
   card before any detailed current-access information. Existing PREMIUM keeps
   its accepted contract, renewal and payment-method details; a new offer is shown
   only when a new contract or renewal is relevant.
4. The purchase card has short benefits, a large monthly price, compact currency
   controls and Pay. Currency changes do not clear the OTP/email form.
5. When eligible live billing is unavailable, Pay opens “Payment unavailable” with
   the selected product/price and Back. The copy explains that this button does
   not charge or change the subscription. It does not claim that older pending
   operations have failed or were unpaid.
6. A fresh, eligible LIVE RUB/SBP offer follows the existing consent, server
   operation, provider redirect and verified result flow. Pending-operation
   recovery still takes precedence over starting another checkout.

The unavailable-payment screen is the owner-authorized temporary placeholder,
not a fake payment or success page. Real merchant setup and live acceptance remain
separate work. All six supported languages have the same path.

## Price authority and privacy

- Current account offers come from the API. If unavailable, show the last valid
  public catalog price or 399 ₽ (was 499 ₽) / $5 (was $7), as already authorized.
- Cached/reference prices are informational and cannot authorize a payment.
  The pure `purchasePresentation` helper requires a fresh LIVE overview, enabled
  operations, an allowed action, a matching offer/revision and recurring RUB/SBP
  capability before checkout. USD never silently becomes a RUB charge.
- Renewal uses the immutable accepted contract amount and currency. A different
  current offer cannot replace it; stale contract information is display-only.
- The placeholder issues no payment POST, creates no operation journal and does
  not mutate access. Existing LIVE commands keep their API validation,
  idempotency, consent and lost-response recovery.
- Query persistence contains only a whitelisted currency. Client handoff fragments
  are still removed immediately. No provider secret, raw card data, new analytics
  or browsing history is collected.
- If optional browser storage is blocked, the reference offer and placeholder
  still work. Live checkout continues to require its existing durable local
  request journal before issuing a command.

## Verification and release boundary

Local checks: website syntax check, 23 Node tests, build of 96 pages, Chrome
acceptance-script lint/format and the actual built portal in Playwright. Browser
coverage includes homepage → USD → OTP → Pay, all six languages at 320/390/1280px,
disabled/empty catalogs, sandbox, unavailable storage/API, immutable contract
prices and the original LIVE fixture consent/idempotency/cancel/retry flow.
Native clients are unchanged, so no native capture is claimed for this task.
Browser screenshots use fixture accounts and do not demonstrate a live charge.
The local Caddy attempt could not start because the Docker Desktop Linux daemon
was unavailable; the unchanged isolated Caddy suite is required in both website
CI runs. On this Windows checkout, formatting is also checked with end-of-line
`auto` to accommodate Git's CRLF checkout; CI checks canonical repository files.

The task PR records the verified product HEAD, all Actions runs/jobs, isolated
Caddy results, artifact source/build SHA, run/attempt and visual evidence. Branch
push and pull-request merge builds are distinct; publication must use the verified
push artifact corresponding to the reviewed product source.

At implementation time, the public website is 0.5.2, source
`29f7eaaa456c803b4f2b8dff6568b4120d4552fc`, run `42615086389`, attempt `1`.
Version 0.5.3 is not claimed deployed by this document. Merge and website
publication need a separate owner instruction. Backend follow-up: none for the
placeholder; real payments remain disabled pending merchant configuration.
