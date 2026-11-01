# Traffic catalog sources — 2026-11-01

The catalog names were inspected inside the owner's installed **NotVPN Android
25.3 (versionCode 253, package com.notvpn)** over authorized USB debugging:
**Apps / Websites → Show the full list**. The list was scrolled and the selected
entries checked in the actual UI, including a search for Google. NotVPN VPN was
never connected, and no service toggles or account settings were changed.
The phone was no longer needed after collection.

Public landing pages did not expose this catalog; the official channel's old APK
links returned 403. They were not used as catalog evidence. No app source code,
credentials, private databases or browsing traffic was extracted. Only the names
of catalog entries were recorded. The exact 50 selected entries and displayed
labels are in [selection.json](../assets/domain-catalog/selection.json).

This is an editorial selection of recognizable services across messaging, social
networks, video/music, AI, productivity, games and shopping. NotVPN exposes no
usage counts; neither the selection nor its ranking claims statistical popularity.
The existing ten popular entries are included; forty additional entries are added.
The separate ten allowlist presets are retained.

Domain masks are maintained independently of NotVPN, using the
[v2fly/domain-list-community](https://github.com/v2fly/domain-list-community)
maintainers' MIT-licensed lists. `selection.json` records each source path and
the exact retrieved Git blob SHA. Disney also includes the `bamtech` list,
blob `6abe15b918d583a6150b0b766fed9e9252286fd5`, for `bamgrid.com`.
The [upstream license](../assets/domain-catalog/LICENSE) is included.

Presets contain bounded primary/API/content domain masks, not entire corporate
holdings, advertising lists or catch-all shared cloud/CDN domains. The Google and
Microsoft presets intentionally cover several services from those vendors; this
overlap is inherent in their shared authentication/content infrastructure.
YouTube Music similarly overlaps YouTube. A domain preset cannot guarantee
classification of every native application's hard-coded IP or an unforeseen CDN
alias. Telegram retains its explicitly maintained public IPv4 ranges from 0039.
No packet capture or per-user destination logging is introduced.

Thirty additional available logos use the existing pinned Simple Icons CC0
source; see [icon attribution](../assets/service-icons/README.md). Entries without
a packaged logo keep the existing generic selector icon and are represented by
the Home ellipsis, according to the owner's design rule.
