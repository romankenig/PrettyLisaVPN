# Service selection and dashboard corrections

Task versions: backend 0.24.0 → 0.25.0 (catalog categories and migration 0038),
Android 0.16.0/code32 → 0.17.0/code33, Windows 0.19.1 → 0.20.0 (compact routing
controls and service switches), dashboard 0.4.2 → 0.4.3. Managed engines stay
0.4.0 unless the WireGuard+ investigation establishes a runtime change.

The operator reset on 2026-10-31 at 06:11:26 UTC granted the requested account
10,800 seconds for that UTC day using the existing closed CLI, after confirmed
cleanup. No ordinary Free entitlement changed.

Home retains three modes, shows the active mode explanation and only icons for
selected sites. Names are accessible labels/tooltips; custom masks use a generic
website icon. The editor uses switches, search and two independent lists. Preset
masks are hidden; custom masks remain editable. Saving disconnects first and
never reconnects. Existing selections and UUIDs stay compatible. Missing category
in an older response or offline selection means `popular`.

The server-owned catalog has ten popular services (YouTube, Instagram, Facebook,
WhatsApp, Telegram, Discord, Signal, X, LinkedIn, TikTok) and ten allowlist services
(VK, OK, Mail, MAX, Yandex, Ozon, Wildberries, Gosuslugi, Rutube, Dzen). These are
curated shortcuts, not a claimed statistical ranking or a guarantee of availability
on every operator. TikTok includes regional restrictions, YouTube throttling.
Rules cover websites, not native apps using fixed IPs. Shared provider CDNs can
serve related products. No browsing data or selections are uploaded.

Sources checked 2026-10-31:
- [Ministry allowlist announcement, 2025-09-05](https://storage.consultant.ru/ondb/attachments/202509/05/iddoc_297576_idnews_64854_Informatsija_Mintsifry_Rossii_ot_05_09_2025_spisok_resursov_oEZ.pdf).
- [Mediascope audience data](https://mediascope.net/data/); no complete comparable
  top-ten ranking for restricted services was available in the public table.
- [OONI Discord measurements](https://explorer.ooni.org/findings/2025-russia-blocked-discord).
- [Signal network domains](https://support.signal.org/hc/en-us/articles/360007320291-Firewall-and-Internet-settings).
- [Community domain registry](https://github.com/v2fly/domain-list-community/tree/master/data).
- [Icon provenance and CC0 license](../assets/service-icons/README.md).

Autopilot has no displayed rating. Country rows keep the number and show three
ascending bars: 0 fills none, 1–33 one, 34–66 two, 67–100 three. This is the server
rating, not mobile/Wi-Fi signal strength.

Dashboard active totals, including hourly history, include only FREE/PREMIUM
exits from selected servers. Intermediate-only selection has no client aggregate;
its own chart still shows transit counts. Speed means and rating medians retain
the chosen population. Tooltips appear on hover/focus, with GMT+3 time and units.

Actual source/build SHA, CI runs/attempts, native screenshots, WireGuard+ fixed
`ifconfig.me` acceptance and rollout evidence belong in the task PR. This document
does not claim pending checks passed. Client acceptance checks the exact mask and
HTML page in both modes, alongside independent IP probes, without browsing logs.
