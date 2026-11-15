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

Selected methods appear first in their saved base attempt order; unselected
methods follow in catalog order. Enabling another method appends it; disabling
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
