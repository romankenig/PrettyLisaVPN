# Dashboard group metrics — 2026-10-29

## Proportional availability history — 2026-11-06

Dashboard 0.6.1 → 0.6.2: PATCH correcting the fleet/group history display.
Backend, client versions, API and schema are unchanged. Based on develop
`df97054f54274ad2a2773294632fa47848964d34`, after billing PR #61.

Each hour uses a CSS linear gradient with proportional, clearly separated color
stops. Every selected server has equal weight regardless of its check count.
Two healthy servers and one failed server produce two-thirds turquoise and
one-third red, not a fully red hour. Full red means all servers registered during
that hour failed. Degraded, unknown and pending states keep their own colors;
missing evidence is not treated as success or failure. Not-yet-registered servers
are excluded from the proportion and listed separately in the tooltip. If none
were registered, the hour remains light gray.

Hours align by UTC timestamp rather than array position. A missing hour for a
selected server is unknown. Group/server filters apply before aggregation.
Hover and keyboard labels report exact counts; clicking retains the existing
per-server measurement details. Individual server timelines retain their colors.

Verification covers partial/full outage, all healthy, degraded/unknown/pending,
registration boundaries, missing/misaligned hours, equal weighting and filters.
Run `npm test` and `npm run build` in `sites/fleet-dashboard`; browser review uses
synthetic mixed-state history at desktop/mobile sizes. Product/build SHA, all
Actions results and artifact links are recorded in the task PR after the final
push. This document does not claim deployment; the existing dashboard install
procedure is a separate publication action.

## Scope and versions

Dashboard 0.3.0 → 0.4.0 (new aggregate calculations and chart placement).
This commit changes no backend, Windows or Android source or binary. The larger
multi-protocol task continues separately; this dashboard is not evidence of new
VPN methods being implemented or deployed.

Individual charts are contained by the corresponding server card, with their
own speed/rating/activity selector. Selecting a measurement opens that server's
hour details inside the same card. The shared chart has no per-server lines;
it aggregates only the currently selected group and server filters.

## Calculations

- Speed: median of valid measurements, separately for download/upload (dashboard 0.6.3). For even N, average the two middle values.
- Rating: median, with the arithmetic mean of the two middle values for even N.
- Active connections: sum across selected FREE/PREMIUM servers; repeated checks never increase weight.
- History uses the latest observation for each server in each UTC hour. Display
  timezone remains GMT+3. Current tiles use latest observations/current ratings.
- Unknown/nonfinite values are omitted and coverage N/M is shown. A later null
  does not fall back to an earlier valid sample in that hour. Empty selections
  show no data. Real zero is retained. Missing hours break aggregate lines.
- Since dashboard 0.4.3, a relay connection is counted only on its exit in the
  aggregate. The intermediate card retains its own transit chart, excluded from
  the shared total. Empty eligible selection has no client total.

## Verification and delivery

Local `npm test`: 10 passed (filtering, mean/median/sum, odd/even median, zero,
missing values, gaps, last-per-hour deduplication, timezone and downloads).
`npm run build`: TypeScript and Vite passed.
Browser verification uses a current read-only snapshot from the main server:
FREE filter recalculates the overview for two nodes; US/DE cards each own their
chart controls; DE has nonzero activity bars. No dashboard credentials are
exported to the browser preview or bundled assets.

Product/build SHA, Actions run and artifact are recorded in the PR after push.
No deployment is claimed by this document. Rollback can restore the preceding
dashboard artifact without changing the backend schema or VPN sessions.

## Separate operator action

At the owner's request, the private server CLI reset today's Free allowance for
`kenromka@yandex.com` at 2026-10-29 08:44:34 UTC, returning `available_seconds=3600`.
The CLI confirmed no outstanding grants before resetting. Existing consumption
history was retained. This is an operational action, not a source-code migration.
