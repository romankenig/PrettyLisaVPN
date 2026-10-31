# Home traffic mode dropdown

Android 0.18.0 (34) → 0.18.1 (35); Windows 0.21.0 → 0.21.1.
PATCH: presentation refinement, no storage/API changes. Backend 0.26.0,
engine 0.5.0 and dashboard 0.4.3 remain unchanged.

The Home traffic card keeps the title and compact mode dropdown on one row.
Options: all / selected / except selected. A small translucent explanation
follows the header. Only the two split modes show the service picker button,
selected service icons and VPN location. All mode has one left-side location.
Existing 20px/dp service logos, 4px/dp gaps and a single ellipsis for missing
logos or overflow remain in place. The selector uses native HTML select on
Windows and Material DropdownMenu on Android.

Mode changes use the existing save path: disconnect any active/starting tunnel,
wait for confirmed cleanup, persist rules, then wait for the next manual
connection. A cleanup failure retains the old mode and both independent lists.
Existing saved choices are read without migration; service catalog and all
transport engines are unchanged. The picker keeps its existing tabs and switches.

Home tests cover dropdown options, conditional controls, mode persistence,
independent lists and failed/pending cleanup. Native Windows capture and Android
AccountScreensTest exercise the real dropdown, service picker and split-only
location/icon rows. Locale checks cover all six languages.

Base product commit: 7b911dc4e09fbe9d4814f04ac02a05e746718182 (PR #42).
Implementation HEAD, actual build SHA/run/attempt, native screenshots, full CI
audit and downloadable binaries will be recorded in the task PR after checking.
No backend follow-up or new real-tunnel acceptance is required for this UI-only
change; previous transport acceptance does not count as testing this new UI.
