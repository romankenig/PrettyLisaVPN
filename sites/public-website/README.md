# PrettyLisaVPN website · 0.5.1

The privacy policy and terms now follow the owner's supplied templates, with
numbered sections, contents links and six synchronized translations. See the
[legal revision handoff](../../docs/public-website-legal.md) for adaptations,
validation and the distinction between editing and legal approval/publication.

Minimal static website on https://prettylisavpn.com. Five homepage sections,
seven platform pages, four documents, a billing portal and six translated languages.
The informational website was previously authorized for publication. The new billing
portal is implemented, but real Platega payments remain disabled pending merchant
credentials and live acceptance. See [billing handoff](../../docs/platega-billing.md).
This revision preserves the deployed 0.3.1 moderation copy, document buttons,
currency layout and native Android capture from PR #52. Its prices now come from
the database API, and purchase/manage links open the authenticated billing portal.

## Run and verify

Node.js 24, no external npm dependencies. From this directory:

```text
npm run dev
npm run check
npm test
npm run build
python3 tests/test_caddy.py
```

Preview listens only on http://127.0.0.1:4180. `PORT` selects another port.
Rebuild and reload after edits. Caddy integration tests require Docker and use an
isolated disposable container without host ports or production changes.

`npm run check:release` / `SITE_RELEASE=1` intentionally fail while commercial
requirements remain unresolved. They do not block the authorized informational
website publication and do not activate payments.

## Structure

- `src/locales/*.json`: complete ru/en/de/fr/es/zh UI and legal content.
- `src/structure.mjs`, `src/pages.mjs`: 96 static pages; contextual language links.
- `src/app.js`, `src/downloads.mjs`: accessible language menu and safe optional
  version/size/hash metadata; no browsing analytics.
- `src/portal.mjs`: OTP/cookie-authenticated billing portal; prices and payment
  operations come only from the backend API. The browser holds no provider secrets
  or card details. Its account-scoped local journal stores only operation/request
  identifiers and the original command for safe retries; the session cookie is
  Secure, HttpOnly and SameSite=Strict. Bank agreement happens on Platega's page.
- `src/model.mjs`: internal commercial readiness; not shipped to browsers.
- `assets/screenshots/`: unchanged native captures and exact CI provenance.
- `scripts/build.mjs`: clean static output, local Rubik/brand assets and build ID.
- `tests/`: Node and real Caddy checks, including public-file/private-path boundary.

`Public website preview` checks and packages a CI ZIP; it never deploys. Deployment
uses the verified push artifact and an atomic website symlink on the main server.
The existing verified client publisher supplies `/downloads/android.apk` and
`/downloads/windows.exe`, source archives, licenses and metadata automatically.
Only those exact files become public; dashboard authentication is preserved.

See [handoff](../../docs/public-website-redesign.md) for versions, validation,
commercial follow-up, publication evidence and rollback. Build identity records
source SHA/run/attempt; live deployment evidence is separate and recorded in PR50.
