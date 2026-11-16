# Random connection-method selection and order

## Scope and versions

Windows **0.28.2 → 0.29.0**, Android **0.27.4/code 54 → 0.28.0/code 55**,
iOS **0.3.0 → 0.4.0**, macOS **0.2.2 → 0.3.0**. MINOR for a new client feature.
Integrated develop: `6177e2e53da41413f60385686d9f1f8e425b0492`.
Android code 55 follows the independently released analytics client (code 54);
the feature's target SemVer versions remain unchanged after synchronization.
Backend/API/schema, managed engines, website and Chrome Extension unchanged.
Linux/Android TV have no implemented method-selection screen in this repository;
Chrome remains a browser proxy client without this VPN-protocol selector.

## Behavior

The refresh icon in connection-method settings draws a nonempty subset from the
platform's existing catalog and shuffles its order. Each catalog entry, including
each relay variant, is independent. The size is uniformly chosen from 1 through
the catalog size. Fisher–Yates/platform shuffle chooses the ordering; an identical
result is rotated (or replaced for a singleton), so every click visibly changes it.
There are no new protocols, backend calls or network checks in this action.

Windows and Apple show selected methods first in their saved base attempt order;
unselected methods follow in catalog order. Android 0.28.2 always displays methods
alphabetically by their labels, independently of selection or saved attempt order.
Enabling another method appends it to the attempt order; disabling
one retains the others' order and cannot remove the last method. “All methods”
on Windows/Android restores the default catalog order and includes future entries.
An explicitly randomized full catalog remains a fixed ordered selection.

The executor uses this order within existing priority rules. The last successful
enabled method still takes priority; Android retains its 10% exploration and
30-minute delayed-failure cooldown. Randomizing does not clear that preference or
failure history. Home's reset/confirmation/reconnect action is unchanged.
Windows/Android changes affect the next attempt cycle, including a future automatic
recovery, and never interrupt a live tunnel. Apple retains its existing disabled
method editor until disconnected and tries the saved order directly.

## Persistence and compatibility

Windows retains the existing JSON-array preference, now preserving entry order
and dropping duplicate/unknown IDs. Android writes an ordered JSON array under
`ordered-methods-v2` and mirrors the enabled set under `enabled-methods-v1` for
older clients. Legacy sets migrate in catalog order; damaged order or a changed
legacy set falls back to that set. The UI state is a list so order-only updates
are observable. Apple retains the existing ordered UserDefaults array.
Rollback keeps enabled methods; older Windows/Android ignore the custom ordering.
No migration, credentials or account state are involved.

## Validation and handoff

Unit tests cover nonempty/unique selections, repeated draws, persistence, manual
editing and preserved success/cooldown priorities. Existing snapshot/cleanup tests
remain. Native Windows capture exercises two draws, navigation persistence and
default restoration. Android native tests cover the icon, SharedPreferences
round-trip and legacy/corrupt values. iOS/macOS native UI runs capture the control;
Swift core tests cover the random selection contract.

Exact verified product HEAD, build SHA/run/attempt, all CI results and screenshot
artifacts are recorded in the task PR after the last push. Native fixture UI is
not real VPN acceptance. No transport change requires a new real-tunnel claim.
Backend follow-up: none. Merge and client publication are separate owner actions;
the existing develop publisher will run after an approved merge.

## Android display correction — 2026-11-15

Android **0.28.1/code 56 → 0.28.2/code 57**, PATCH for selection-screen feedback.
Integrated develop: `159d98890602179838fe196d1d3c75aaaf8502c4`. Other component versions
are unchanged. The two-column list reads alphabetically left to right, then top
to bottom, using case-insensitive protocol labels. Selected and unselected rows
stay in the same positions. Both explanatory captions are removed in six locales.

Each refresh press rotates the icon over 400 ms and fades a violet highlight on
changed checkbox rows over 650 ms. If only saved attempt order changes, the selected
rows receive the feedback. Rapid presses apply immediately and restart the feedback;
manual editing clears it. Compose animations honor the system motion duration scale.
No selection, persistence, attempt-order or last-success rule is changed.

Native Android acceptance checks alphabetical coordinates and checkbox state after
manual selection, repeated randomization and restoring all methods; it also checks
the highlight fades with a controlled animation clock and saves native screenshots.
Existing unit tests continue to cover preserved attempt order and recovery priority.
Actual final source/build SHA, run/attempt and artifacts belong in the task PR after
CI completes. No backend follow-up or data migration is needed. Publication follows
a separately approved develop merge.
