# Home refresh, catalog and Android VPN notification

Task versions: Android **0.18.1/code 35 → 0.19.0/code 36**, Windows
**0.21.1 → 0.22.0**, backend **0.26.0 → 0.27.0**. MINOR releases add Home
refresh, an expanded database catalog and actionable VPN notifications.
Managed engines **0.5.0 → 0.5.1** fix the domain rule bound for the larger catalog;
dashboard remains **0.4.3**.

## Behavior

- Android Home refreshes account, country availability and both applicable
  location observations on a downward pull. Windows has a Home refresh button.
  Refresh never reconnects or changes routing rules.
- Android immediately invalidates the old IP on a VPN transition and reads the
  new location after connection/disconnection. Both clients show a loading
  indicator. Cancelled/older lookups cannot replace a newer route's result.
  Full traffic still has one location; split modes retain the separate,
  VPN-pinned ifconfig.me observation.
- A network warning requires 15 seconds of continuous failure. Home account and
  country GETs retry during this period; Android's public reachability observer
  checks failures every three seconds. Recovery cancels the warning immediately.
  Authentication errors, VPN verification and cleanup rules are unchanged.
- The selector first shows ten catalog-ranked popular services. Russian exclude
  mode promotes ten allowlist entries under the requested “Топ-10 популярных”
  heading; other languages use the ordinary popular group. The second section
  always contains the entire catalog, sorted by localized name. Duplicated rows
  edit the same selection; include/exclude lists remain separate.
- Android requests notification permission on the first approved VPN attempt on
  API 33+. Declining never blocks the VPN and never repeats on each transport
  fallback. The ongoing notice reflects connecting/connected/disconnecting and
  provides Open app / Disconnect VPN. Disconnect goes through the existing
  cleanup-aware controller, including remote lease removal. Android can hide the
  notification if the user denies notification permission or disables its channel.

## Data and compatibility

Migration **0040_traffic_catalog_refresh** adds nullable `popularity_rank`
(1–1000), preserves all existing IDs/masks/Telegram IPv4 networks, and inserts
40 services. There are 50 popular services plus 10 allowlist services: 60 entries,
below the existing 64-entry API/client limit. Rank is optional for older clients
and older saved selections. No traffic destinations or user browsing observations
are collected. Names are observed catalog facts; ranking is editorial, not usage
statistics. See [catalog evidence](traffic-catalog-sources.md).

Both clients and engine 0.5.1 accept up to 1024 combined domain rules, so the
complete catalog and 256 manual masks fit together. Manual masks remain limited
to 256, service IPv4 rules to 256, and the engine profile to 64 KiB. Older engines
still accept their previous profiles; new clients ship the matching engine.

Upgrade backend before distributing clients to expose the larger catalog.
Downgrade removes only the 40 seeded IDs and the rank column; original services
remain. Previously saved client rules remain on the device until edited.

## Validation and handoff

Tests cover the 15-second deadline and recovery, stale location cancellation,
Home refresh, mode/language grouping, catalog bounds and authentication,
notification actions and cleanup. Android API 26/35/36 instrumentation also
captures the native notification and Home; Windows UI review builds the current
checkout and captures the native window.

At source preparation, new binaries and deployment are **not yet verified**.
The task PR records the final verified source HEAD, actual build/merge SHA,
run/attempt, native screenshots and publication results after all checks finish.
Previous development binaries are not evidence for these changes. Latest download
links remain `/dashboard/downloads/android.apk` and `/dashboard/downloads/windows.exe`.
