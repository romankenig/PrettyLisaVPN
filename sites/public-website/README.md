# PrettyLisaVPN website · 0.2.0

Minimal static website on https://prettylisavpn.com. Four homepage sections,
seven platform pages, four documents and six fully translated languages.
The owner authorized public publication. Commercial checkout remains separate.

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
- `src/structure.mjs`, `src/pages.mjs`: 78 static pages; contextual language links.
- `src/app.js`, `src/downloads.mjs`: accessible language menu and safe optional
  version/size/hash metadata. No cookies, local storage, tracking or payment forms.
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
