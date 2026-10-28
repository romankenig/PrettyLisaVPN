# Free quota, abandoned access and client cleanup

Source baseline: backend 0.21.0, Android 0.14.0/code25, Windows 0.17.0.
UI naming/hint patch: Android 0.14.1/code26 and Windows 0.17.1; included in
the next builds, not separately published. Quota/cleanup patch: backend **0.21.1**,
Android **0.14.2/code27**, Windows **0.17.2**. Dashboard remains **0.3.0** for the
ongoing history task. Additive migration **0034_short_free_reservations**.

## Failure and changes

The previous first Free session reserved the entire remaining hour. A second
device therefore received FREE_QUOTA_EXHAUSTED. On Windows a native stop failure
prevented the subsequent DELETE, leaving a READY grant renewed by the server.
Both clients correctly read that shared running session but continued counting
it down even while their local UI said disconnected. Live inspection on
2026-10-28 found this Windows grant; targeted revocation was confirmed CLOSED,
leaving zero active sessions and 2380 seconds. No extra quota reset was performed.

Each new Free access now reserves at most 180 seconds in PostgreSQL, under the
account lock also used by admission and worker extensions. Before any node grant,
the worker extends that reservation from still unreserved account time. Exit and
relay grants share the same reservation/deadline. Existing grants never lose a
reserved second before their enforced deadline or confirmed removal. Total
reserved plus consumed device time cannot exceed the account's UTC-day hour.
The user-visible expires_at stays the maximum session/UTC entitlement deadline;
sleeping clients do not need to renew short reservations themselves. An exhausted
or expired reservation stops on the node even if the control plane is unavailable.

The balance adds back the unused portion of current READY reservations, not the
entire user-facing deadline. Two devices consume two budget seconds per second.
Unused reservations return after confirmed removal; unknown removal retains the
reservation and retries every 10 seconds. Near exhaustion, time reserved by a
different device produces FREE_QUOTA_RESERVED rather than an invented new hour.
No endpoints or browsing/packet logs are added.

An expected-egress probe records verified_at. A newly issued grant without that
confirmation is revoked after the 90-second setup timeout, even if installation
already reached READY. Existing READY grants are grandfathered during migration
to avoid interrupting verified sleeping phones. Absence of phone HTTP heartbeats
is not used to revoke verified access. Explicit deletion, account/device/auth
revocation and entitlement expiry still use the persistent server worker.

Both clients attempt remote cleanup even when local shutdown fails. Startup
recovery removes this device's previous grant before new work, once per owner;
it does not touch other devices or another VPN application. A cleanup failure
keeps a retryable stop action and blocks fallback until cleanup succeeds. Windows
waits up to ten seconds for SCM deletion after the uninstall process returns.
Client balance extrapolation stops after 60 seconds without fresh /me data.

## Compatibility, checks and rollback

Existing clients still read the same API fields and use expires_at. Historical
leases with NULL quota_reserved_until retain legacy accounting until their first
renewal; conversion retains at least the possible outstanding 180-second grant.
No quota history is deleted or retroactively refunded. PostgreSQL integration
tests cover five competing devices, renewal, exact summed elapsed time, frozen
idle balance, failed deletion/retry, unverified expiry and legacy conversion.
Client tests cover local-failure/remote-success cleanup, recovery and stale time.
CI provides Android tests and native Windows screenshots for the actual head.
These tests are not a claim of successful VPN on the owner's current devices.

Before rollback to a worker unaware of short reservations, disable new issuance
and confirm all new leases removed. Do not run old and new workers concurrently.
Downgrade refuses live short reservations; retaining the additive schema is
preferred. Preserve migration 0033 and stored dashboard observations. Actual
source/build SHA, runs/attempts, artifacts and deploy evidence belong to PR #35.
