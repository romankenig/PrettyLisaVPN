# Premium country visibility

## Scope and versions

Country selectors show Premium-only locations to FREE and DEMO with a blurred,
dimmed label and a readable localized “available only with Premium” explanation.
They cannot be selected. FREE still selects free-node countries; DEMO still uses
AUTO and retains its existing registration prompt for FREE locations. Premium and
Platinum retain full access. No purchase or external navigation is added.

Base: develop `84466c97c6938fcf09fcef296da38dc18d27f479`.
Backend **0.53.0 → 0.54.0** adds an opt-in catalog capability (MINOR). Client
PATCH versions: Windows **0.31.2 → 0.31.3**, Android **0.30.2 → 0.30.3**, code
**61 → 62**, Chrome **0.5.1 → 0.5.2**, iOS **0.6.1 → 0.6.2**, macOS
**0.5.1 → 0.5.2**. Website and managed engines are unchanged. Linux/TV have no
shipping country selectors to update.

## Contract and compatibility

Updated clients request `GET /vpn/countries?include_locked=true`; Chrome also
retains `method=https_proxy` and the existing IP-proxy capability header. Each
country adds `premium_required: boolean`. Locked countries have `available=false`
and `quality=0`; these are account-scoped capabilities, not public health claims.
AUTO and top recommendations use only eligible nodes. Infrastructure details,
addresses, credentials and browsing data are never returned by this catalog.

The default response remains shape compatible: without opt-in, restricted
countries and the new field are omitted. New clients accept legacy responses with
the field absent. A country containing any FREE-eligible node is not Premium-only,
even when that free node is offline and a paid node in the country is healthy.
Its free-user quality and availability still use only free nodes. Intermediate
nodes are excluded; Chrome also excludes nodes without a supported proxy method.

Backend session admission, quotas, identities, paid expiry and traffic routing
are unchanged. Showing metadata never grants access. No migration is required.
Deploy backend before publishing updated clients to expose the new rows. Rollback
to an older backend restores the old catalog without breaking updated clients.

## UI and validation

Windows and Chrome blur only the country content, leaving the explanation clear.
Windows limits the scrollable dropdown to the actual remaining workspace height,
including after resize, so additional locked rows cannot overflow the native window.
Disabled rows are skipped by keyboard selection. Windows and Android reset a
previously selected locked country to AUTO; Apple checks refreshed selection and
connection, and Chrome checks cached selections before allocating a proxy lease.
Apple uses a native scrollable sheet/popover because system menus flatten custom
blur content. Its text follows the sheet appearance, and the Premium explanation
stays outside the disabled button so native dimming cannot obscure it. Native Mac
review captures the picker in both appearances. Android uses platform blur from
API 31 and a composited blur fallback on API 26–30. All six languages contain the
new explanation.

Unit/API tests cover opt-in/legacy behavior, mixed-country ratings, all-locked
AUTO, FREE/DEMO locks and Premium/Platinum selection. PostgreSQL integration checks
cover the actual fleet catalog and Chrome proxy filtering. UI review scenarios
capture FREE/DEMO Windows, Android and Chrome lists and Apple's native picker;
they use synthetic account data and do not claim a real VPN acceptance run.

The task PR records final product HEAD, actual build/temporary merge SHA, original
run/attempt, all workflow/job results and native screenshots after the last push.
Local checks do not replace Android/Apple compilation or Windows native review.
Merge, backend deployment and publication are separate owner-authorized actions.
After an authorized develop merge, verify shared client publishers and stable
dashboard downloads against the exact successful develop builds. This source
handoff does not claim deployment or updated public download binaries.
