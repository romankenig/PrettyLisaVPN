# Android optional location — 2026-11-07

Android **0.23.0/code 44 → 0.23.1/code 45**, an independent PATCH requested after
the subscription redesign in the same PR. Backend, schema, engines and all other
client versions remain unchanged.

The owner's screenshot shows a connected tunnel with a lower “VPN location
unavailable” label. The code can produce this whenever the optional IP probe
returns no observation, including provider/network failures or route changes.
The screenshot alone does not establish which request failed or whether the
tunnel failed; no device logs or real-phone reproduction were available.

Keep the current provider and the mandatory ifconfig.me VPN rule. Replacing that
origin alone could observe physical egress under selective routing. No new
third-party destination, physical-network fallback, location history or selected
server masquerading as an observed IP is introduced.

The lower traffic-card section and divider are hidden when disconnected, in
all-traffic mode, or without an observation. A successful minute/manual refresh
restores the section. If the measured IP is known but its city/country lookup
failed, show that IP without an “unavailable” region. The section clears after a
failed refresh; old results are not retained indefinitely or across route changes.
The existing connection status/errors and upper current-region block are unchanged.

Native AccountScreensTest covers hidden missing metadata, IP-only display,
successful region recovery, disconnect/all-mode suppression, direct-location
labeling and a subsequent failed refresh. Its existing disconnected split-mode
test now expects the optional block to be absent while retaining selection/icon
assertions. There are 21 AccountScreensTest methods. Existing MockWebServer tests
retain provider-error, mismatched-geolocation and tunnel-route guarantees.

Native screenshots use documentation-only synthetic addresses. Final product
SHA, PR merge/build SHA, all Actions runs/attempts and artifacts are recorded in
[PR #64](https://github.com/romankenig/PrettyLisaVPN/pull/64). Source changes do not
constitute a phone test, merge or publication; these remain separately tracked.
