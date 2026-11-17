# Website store mentions — 0.6.2

Owner request on 2026-11-17: remove store mentions from prettylisavpn.com and
leave everything else unchanged. Website 0.6.1 → 0.6.2 (PATCH); all other component
versions are unchanged. Base: `978cfc164b71872d31d1d750c7a1aa63e8ce30a9`.

Remove only the generated store card on each of seven platform download pages
in all six languages. Direct downloads, installation instructions, screenshots,
CSS, navigation, homepage, legal pages and billing remain unchanged. No backend,
database, client, payment or routing changes. Existing translations/store metadata
are retained internally; they are not rendered into the public pages.

Validation: existing Node checks/tests, a 96-page build and exact HTML comparison
against the baseline with only the store card removed. Caddy routing is checked
by CI in its isolated container. Exact product/build SHA, push and PR run/attempt,
artifact and authorized live publication evidence belong in this task's PR.
Publish only the verified push artifact through the existing atomic website
symlink; retain the previous release for rollback. Backend follow-up: none.
