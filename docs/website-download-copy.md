# Website download copy and device order — 0.6.3

Owner request on 2026-11-17. Public website 0.6.2 → 0.6.3 (PATCH for copy and
small presentation changes); all other component versions are unchanged.
Base: `3ef65327` (develop after PR #100).

The homepage CTA now says “скачать” and the device heading says “один аккаунт”.
All six languages use equivalent copy. Remove diagonal and back arrows from
links/buttons/cards; retain downward download, section and language-menu arrows.
Ready public downloads appear first: Android, Windows, Chrome. Upcoming cards
follow as TV, iOS, macOS, Linux. TV is a display-label change only: the existing
`/download/android-tv/` route and platform ID remain compatible.

No backend, database, client, payment, analytics or download URL changes. Apple,
Linux and TV availability remains unchanged. Backend follow-up: none.

Verification uses existing Node syntax/tests, the 96-page static build, rendered
desktop/mobile review and the existing six-language browser acceptance suite.
Caddy routing is verified by the isolated CI container. Final product HEAD,
push/PR build SHA/run/attempt, artifact IDs and all CI job results are recorded
in the task PR after the last push; PR merge builds are identified separately.
Merge and production publication remain separate owner actions. Deploy only the
verified push artifact through the existing atomic website symlink when authorized.
