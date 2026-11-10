# PrettyLisaVPN website 0.2.0 — minimalist multilingual revision

Later legal revision: [website 0.5.1](public-website-legal.md) follows the owner's
supplied templates and supersedes the brief terms/privacy copy described below.
This document otherwise records the historical 0.2.0 task.

## Scope and versions

Owner request dated 2026-11-03: four main sections, real screenshots, all platforms,
separate downloads, six client languages, four short documents, one planned launch
notice for November 15. Existing authorization to publish on the main domain applies.
No additional site, hosting vendor, payment integration, merge or client release.

Website **0.1.0 → 0.2.0**: substantial UI/navigation/localization features.
Backend **0.31.0**, Windows **0.25.0**, Android **0.21.0** unchanged. No database or
API changes; Caddy serves verified existing binaries. Product/source HEAD, actual
CI build SHA/run/attempt, artifacts and live verification are recorded in PR50
after the final push. No earlier artifact proves this revision's verification.

## Implemented routes

- `/`: exactly four sections (hero; features/screenshots; platforms/downloads;
  FAQ/problems/support). A single planned launch notice, no readiness dump.
- `/download/{android,windows,ios,macos,linux,android-tv,chrome}/`: individual
  platform pages. Android/Windows have direct files and instructions; all stores
  disabled. Future platforms are muted and labelled soon, without fake files.
- `/legal/{terms,privacy,refunds,payments}/`: original concise content, real seller
  details, manual renewal and no invented refund guarantee or provider approval.
- Russian at `/`; English, German, French, Spanish and Chinese under
  `/en/`, `/de/`, `/fr/`, `/es/`, `/zh/`. All UI and documents translated.
  The language picker preserves the current platform/document. No browser storage.
- `/support[/]` → `/#help`, `/setup[/]` → `/#download` (308). Obsolete pricing,
  account, checkout/readiness and extra legal pages removed. Old payment returns
  remain backend-owned. `POST /checkout[/]` still fails closed with 503.

The public site is static Node-generated HTML/CSS/JS with no new dependencies.
Rubik, official lock mark and the purple/mint palette are reused. UI is lowercase;
`PrettyLisaVPN` and the legal seller name retain their exact casing.

## Real app assets and direct delivery

Screenshots are unchanged native CI captures with synthetic demo data, clearly
captioned as interface examples. They are not live connection evidence. Exact
capture source/build SHA, run/artifact and file hashes are in
`sites/public-website/assets/screenshots/sources.json`.

Public files use the existing verified publisher snapshot:
`/opt/prettylisavpn/secrets/dashboard/downloads/current`, mounted separately as
`/srv/client-downloads` (downloads subdirectory only, read-only). Only six exact files are
exposed on the apex domain: Android APK, Windows NSIS installer, corresponding
source archives, Windows license notices and the metadata index. No directory
listing, dashboard configuration, secret or private API becomes public. API-host
Basic auth remains intact. Future verified client publications update these links.

The download page validates version/size/hash metadata and uses textContent.
Metadata URLs cannot redirect a download; file URLs are fixed in source. A metadata
outage does not break the file link. Public distribution includes corresponding
sources/licenses, rather than exposing only binaries. Downloads do not install or
execute software automatically.

## Verification

- Seven Node test groups: complete language schema, exact four sections/seven
  platforms, all 78 pages and links/anchors, disabled stores/future files, safe
  metadata, original screenshot hashes, commercial activation guard, clean build,
  HTTP/security headers/payment denial and secret non-reflection.
- Four real Caddy integration groups in a disposable `--network=none` container,
  without host ports: every page/asset, six public files, download disposition,
  forbidden paths/methods, removed routes and preserved return/redirect behavior.
- Browser QA: six homepages at widths 320, 390 and 1280 with no horizontal overflow;
  download pages, language context, Escape, FAQ expansion and fixed support mailto.
- Node syntax, Prettier, Python Ruff and git diff checks. No payment performed,
  no support email sent, no new VPN validation claimed for this website-only task.

Publication uses the successful current push artifact, validates candidate Caddy,
retains previous static release/config and atomically changes the website symlink.
Only Caddy is recreated if routing changes. Backend/VPN/database containers and
runtime identity must stay unchanged. Verify live HTTPS, download hashes and 401
on the private dashboard. See [deployment/rollback](../infra/deployment/README.md#public-draft-website).
Until PR50 merges, a backend deployment from older develop can restore older
Caddy routing; inspect this configuration before that deployment.

## Internal commercial follow-up — not public placeholders

This revision removes visible draft warnings by explicit owner request. It does
not turn generic informational documents into a legally reviewed sales offer or
enable payment. Before commercial launch, still obtain/approve:

1. Seller's postal address for claims, final offer and contract acceptance/version.
2. Refund calculation/process, claim handling and NPD receipt issuance/delivery.
3. Complete data processor/region/backup/log retention/deletion inventory and legal
   bases. Known daily analytics retention 180 days and support working-DB content
   retention 30 days do not imply full account/mailbox/backup erasure.
4. Paid-access delivery timing, support terms and confirmed commercial limitations.
5. Cardlink acceptance of this VPN/NPD seller, currencies/fees, authenticated
   callbacks/status reconciliation, refunds and tested account-scoped order flow.

Recurring payments, Stripe and Cryptomus remain deferred. Manual renewal is not
called automatic renewal. Confirmed draft prices (199 RUB / 2.99 USD per calendar
month) remain internal; no unsupported checkout or available provider badges.

Legal structure was informed by official [FNS NPD receipt guidance](https://www.nalog.gov.ru/rn19/news/activities_fts/16641439/)
and [Rospotrebnadzor's NPD explanation](https://62.rospotrebnadzor.ru/content/o-zashchite-prav-potrebiteley-pri-okazanii-uslug-samozanyatymi-grazhdanami).
[Mullvad](https://mullvad.net/en/help/terms-service) and [Proton](https://proton.me/legal/terms)
were structural references only: their guarantees, retention and refunds were not
copied. The owner's visual reference was LibertyVPN's download page, not a source
of PrettyLisaVPN capability claims.
