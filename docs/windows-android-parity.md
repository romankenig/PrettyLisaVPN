# Windows parity — 0.27.0

## Scope and versions

Windows **0.26.1 → 0.27.0** (MINOR): guest admission, legal navigation and plan UI;
backend **0.39.0 → 0.40.0** (MINOR): additive Windows DEMO platform;
managed engine **0.6.1 → 0.6.2** (PATCH): desktop full-tunnel DNS;
website **0.5.0 → 0.5.1** (PATCH): Windows identity disclosure in six languages.
Android, Chrome and Apple client versions are unchanged. Mobile core configuration
is unchanged; no schema migration beyond existing 0047 is needed.

## Behavior and boundaries

- Email login offers a secondary DEMO button and compact legal links. OTP can return
  to the previous email field; the code and request are cleared. About contains the
  same four fixed legal destinations. Native document opening allowlists document
  IDs and locales; renderer-controlled URLs are not accepted.
- DEMO uses an app-scoped SHA-256 of Windows MachineGuid; the raw identifier stays
  inside native code. Backend additionally HMACs it in the Windows namespace.
  Ordinary app reinstall preserves the quota; OS reinstall/cloning is outside this
  guarantee. This is an abuse deterrent, not hardware attestation. Android's existing
  identity derivation remains byte-for-byte compatible.
- Existing server rules enforce 900 seconds/device/UTC day, AUTO and full traffic.
  Windows forces AUTO/full routing even with saved registered-user preferences.
  Devices and advanced method selection remain accessible. Locked country/split
  choices say “недоступно в DEMO” and lead to registration after confirmed cleanup.
  Upgrade opens the plan comparison; Buy returns there after registration. Existing
  FREE usage is never reset by signing in again.
- PREMIUM is the primary plan card, with large RUB/USD price, unlimited access and
  premium servers. FREE and DEMO are quieter. Prices come from the API, with the
  approved display-only 399/499 RUB and 5/7 USD fallback. No fallback offer ID can
  authorize checkout. Actual renewal confirmation uses the immutable contract price
  and currency. Provider readiness and all existing idempotency/receipt checks remain.
- Devices show ACTIVE rows only. Device, subscription and About content can scroll.
  Refresh is an accessible icon. Current access and management actions are separated
  from the plan comparison; payment changes/cancellation stay at the bottom.
- Initial heartbeat/deadline failures now fail the current adapter instead of
  cancelling the entire fallback executor. Every next method waits for confirmed
  local and remote cleanup. Terminal quota/auth/access failures do not try new methods.
  After connection, health checks retain private configuration and verify actual
  tunnel-bound DNS/HTTPS. Two transient failures, a dead local runtime or expired
  access end the session; stale checks cannot stop a newer session. This task does
  not introduce an unlimited automatic reconnection loop.
- Before allocation, native code can exit only a separately installed Kaspersky
  Secure Connection/VPN product with a valid Kaspersky signature, via its own `EXIT`
  CLI. No antivirus task, adapter or service is disabled. Ambiguous installations,
  self-protection/password refusal or persistent routes fail closed with VPN_CONFLICT.
  Other VPN products still require manual disconnection.
- Desktop all-traffic DNS uses the encrypted outbound and IPv4 answers to match the
  existing IPv6 block. System DNS cache is cleared on our tunnel transitions; stale
  split-mode fake addresses cannot escape. No direct bypass for any website is added.
  This fixes identified DNS weaknesses; HTTP rejection by a destination is distinct
  from DNS/TLS/tunnel failure. Browsers may retain their own DNS caches.

## Verification and release handoff

Local checks cover frontend types/lint/unit tests, Rust/native tests and Clippy,
managed engine tests, Python lint/types and actual PostgreSQL DEMO admission/quota
reinstall tests for both Android and Windows. Native UI review builds current
working sources and captures the real Tauri/WebView2 window with loopback fixtures;
this is not real VPN acceptance. Synthetic debug builds use an isolated Credential
Manager namespace so reviews cannot read/overwrite an installed user's session.

Kaspersky policy tests execute the actual script with mocked OS/process boundaries,
including rejection of unsigned files and antivirus directories. Installed Kaspersky
5.27 help/signature were inspected read-only; automatic handoff against the user's
active tunnel has not been exercised. No antivirus configuration was changed.

Exact product HEAD, final source/build/run/attempt, all CI jobs, artifact identities
and current screenshots belong in the task PR after the final push. Do not treat
local baseline SHA or earlier screenshots as evidence for the final binary. The
optional real managed acceptance includes fixed Yandex/RuTracker HTTP probes in
full mode; artifacts contain status only, never page contents or browsing history.

Deploy backend 0.40.0 before publishing Windows 0.27.0. The Windows client checks
the actual API version before sending a guest identity: pre-0.40/unknown APIs cannot
silently interpret it as an Android guest. Email login stays compatible. Existing Android DEMO
principals and quotas require no migration/reset. After separately approved merge,
verify the shared publisher's stable Windows download and website 0.5.1 publication.
The owner authorized merge/publication on 2026-11-09; #74 merged as
`8abd893373cb9f77c6d51b67cb6bf9d98d57b81c`. Actual deployment evidence is recorded in the PR.

## Website publication reconciliation

Pre-publication inspection found that the live website already serves the separately
authorized legal revision `3cc30e87d497e54ab3544a4653e253851e3a2463` from PR #70,
run 42464416970/1. Publishing #74's website artifact would revert those documents.
Preserve that exact legal revision and insert the Windows identity disclosure into
privacy clause 2.4 in each language, retaining generic plan names and numbering.
The combined website is **0.5.1 → 0.5.2** (PATCH); all client/backend versions and
payment gates remain unchanged. This does not merge or change the separate PR #70.

Verify syntax, all website tests, the 96-route build and isolated Caddy checks.
Compare the candidate files with the currently published artifact before switching
the relative website symlink. Record the final source/build SHA, CI run/attempt,
artifact, complete CI audit and live hashes in the publication PR. The previous
relative release remains available for rollback; no database migration is involved.
