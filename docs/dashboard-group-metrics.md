# Dashboard group metrics — 2026-10-29

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

- Speed: arithmetic mean of valid measurements, separately for download/upload.
- Rating: median, with the arithmetic mean of the two middle values for even N.
- Active connections: sum across servers; repeated checks never increase weight.
- History uses the latest observation for each server in each UTC hour. Display
  timezone remains GMT+3. Current tiles use latest observations/current ratings.
- Unknown/nonfinite values are omitted and coverage N/M is shown. A later null
  does not fall back to an earlier valid sample in that hour. Empty selections
  show no data. Real zero is retained. Missing hours break aggregate lines.
- A relay connection appears on the exit and intermediate nodes. The sum is
  node connection count, not a count of distinct devices across the service.

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
