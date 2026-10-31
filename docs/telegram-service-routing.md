# Native Telegram routing and split-mode locations

Task versions: backend 0.25.0 → 0.26.0 (migration 0039), Android
0.17.0/code33 → 0.18.0/code34, Windows 0.20.0 → 0.21.0, managed engine
0.4.0 → 0.5.0. These are compatible capabilities; dashboard stays 0.4.3.

The reported case is Android, WireGuard+, include mode: YouTube works, the
native Telegram app does not. Domain rules cannot classify a direct MTProto
connection to a numeric DC address. The Telegram preset now carries nine
explicit IPv4 CIDRs from [Telegram's published networks](https://core.telegram.org/resources/cidr.txt),
checked 2026-10-31. [Telegram describes its DC IP connections](https://core.telegram.org/api/datacenter).
These data are seeded in PostgreSQL, not inferred from browsing observations.
The catalog's optional `ipv4_cidrs` field defaults to empty; old selections and
clients remain readable. Only selecting/saving an updated preset adopts these
networks. Manual domain masks still mean domain rules, not application identity.

Both clients validate, persist and compile domains and networks separately for
the selected mode. The engine validates canonical public IPv4 networks and
bounded counts again. Selected networks use VPN in include mode and direct
egress in exclude mode, without needing DNS or HTTP/TLS metadata. Private,
reserved, FakeDNS and catch-all ranges are rejected. No IP-rule text box is
added. Telegram-owned DC traffic is covered; third-party proxies and arbitrary
P2P call peers are not matched by Telegram's published networks. IPv6 remains
blocked as before; this task does not add IPv6 connectivity or per-app routing.

`ifconfig.me` and its subdomains always use the VPN before user domain/network
rules, alongside the existing verification origin. They cannot be excluded.
All-traffic mode already tunnels all traffic. The include/exclude acceptance
expectations explicitly check that even excluded ifconfig.me uses the exit IP.

In split modes only, the left Home block retains its existing public-location
provider and routing. The right traffic block shows a second, measured VPN
location. [ifconfig.me/all.json](https://ifconfig.me/) supplies the IP;
[ipwho.is](https://ipwhois.io/documentation) looks up that exact IP for city and
country. If metadata fails/mismatches, keep the measured IP and show unknown
location rather than substituting the chosen country or physical IP. The right
lookup runs only when connected, binds to the tunnel, and clears on teardown.
Windows uses the managed TUN source address; Android pins the VPN Network
socket factory/DNS snapshot. No direct fallback is allowed for this probe.

**Full-traffic mode has only one location**, in the left block. Saving traffic
rules still disconnects and waits for cleanup; it never reconnects automatically.
No auth tokens, device identifiers or location/browsing history enter public
geolocation requests or logs. Existing left-side location behavior is retained.

Validation and rollout are pending until the PR records actual source/build
SHAs, all CI runs/jobs, native screens, real tunnel acceptance and downloads.
This handoff is not evidence that an unbuilt APK or a physical Telegram account
has been tested. User acceptance must update the APK, open service selection,
save the Telegram preset, and reconnect; an old APK only understands domains.
