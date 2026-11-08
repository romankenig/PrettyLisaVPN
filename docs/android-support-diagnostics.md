# Android support diagnostics

Android **0.26.1 → 0.27.0**, code **49 → 50**; backend **0.38.0 → 0.39.0**.
This adds a diagnostic contract and local collection, so both are MINOR changes.
Base: `6b6e44c4b91525f02065c100d4617e8bf7a924be`. Schema remains 0047; no database
migration. Windows, Apple, Chrome, website and dashboard versions are unchanged.

## Sender and delivery

The reply address previously existed only in Reply-To. New email bodies display
the authenticated account email (snapshotted by the server), chosen reply email,
account ID and request ID. Clients cannot submit or override account_email.
Legacy queued requests still show their reply address; an unavailable historical
account email is explicitly labelled. SMTP sender/recipient remain fixed.

Android sends diagnostics as a separate v2 `ANDROID` projection in the existing
POST /support/requests report. The description retains its full 4000-character
budget. The mailer attaches Android data as `diagnostics.json`; Windows v1 remains
accepted and retains its existing email representation. JSON report capacity is
256 KiB, total multipart capacity is 10 MiB + 320 KiB; image limits stay unchanged.
Both diagnostic variants reject unknown fields and verify supplied session IDs.
The accepted report/attachments retain the existing 30-day server retention.

## On-device collection

Only explicit event fields are collected, never arbitrary logcat/library output:

- device manufacturer/model, Android release/API/security patch/build ID/ABIs;
- app version, code, source SHA/debug mode and actual GET /version backend value;
- interface language/timezone, plan and selected routing mode/methods;
- available memory/storage, charge, power saving, Doze and battery optimization;
- active network transports, validation/captive portal/metered state;
- VPN phases, attempted methods/country, fixed setup/verification stages,
  durations, health outcomes, reset/disconnect/recovery events;
- API operation category, status, duration and allowlisted machine error code;
- foreground/background/start and crashes with normalized failure categories
  and at most 24 frames from PrettyLisaVPN's own Android code (no error message).

The private no-backup journal is limited to 2 MiB. It expires records older than
seven days during collection/export and discards oldest records when full.
Collection writes run on a bounded background queue; failure cannot break VPN or
auth. Queue/storage loss and unavailable collection are explicit in the export.
Logout/account changes clear queued history and stored events; a new account
cannot attach another account's journal. Uninstall removes the private logs.

No OTP, token, WireGuard key, tunnel configuration, browsing destination, DNS query,
packet content, SSID, hardware ID, contact, raw API body/header or exception text
is recorded. DNS/HTTPS stage labels describe checks without their destinations.
No background diagnostic upload exists. Account email is server-owned support
metadata, not a journal field. User-entered text/images remain explicit content.

## Sending and verification

The form defaults to including diagnostics and explains what this means. The
user may disable it or inspect the exact bounded JSON. A request includes the
newest 400 events within a 128 KiB event budget; omitted retained events are counted.
Submission deep-copies the snapshot into the existing encrypted operation journal.
Network uncertainty/restart retries the same request ID, payload and image bytes;
it does not regenerate timestamps/events or send a second ticket.

Backend tests share Android's wire fixture and cover bounds, rejected sensitive
fields, visible email, JSON delivery, ownership and idempotency. Android tests
cover bounded retention/restart, safe crash projection, observer failures,
fallback timing, request serialization/frozen retries and native opt-out/preview.
Full local checks, product/build SHA/run/attempt, native artifacts and all current
HEAD workflow results are recorded in the task PR after verification.

Deploy backend 0.39.0 before distributing Android 0.27.0. Old clients remain
compatible; rolling the API back below this schema requires keeping the v2 parser
or disabling diagnostic sending in the newer client. No live support email is
sent by acceptance tests; SMTP is mocked. Publication requires the owner's
separate merge/deploy authorization; implementation is not proof of deployment.
