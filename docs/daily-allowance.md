# One-off account/day allowance

Backend 0.22.1 → 0.23.0, migration `0036_daily_allowance`; Android
0.15.2/code30 → 0.15.3/code31; Windows 0.18.0 → 0.18.1.

The server-only `python -m prettylisavpn.client_vpn.reset_quota --email EMAIL
--request-id UUID --seconds 10800` resets one account to three hours remaining
for the current UTC day. Omitted seconds still mean 3600. Valid amounts are
1–86400; the session deadline never exceeds UTC midnight. Next day automatically
returns to ordinary Free. This does not change plan, country rights or device
limits, and is not a client-callable API.

Account locking, one reset per UTC day, request UUID idempotency and confirmed
cleanup are preserved. Reusing a request UUID with a different allowance fails.
No historical sessions or usage are rewritten. Existing reset records receive
3600 through the database default. The downgrade refuses while a custom
allowance still applies today or in the future; preserve the database audit
before any later downgrade.

`GET /me` uses its existing `daily_vpn_limit_seconds` field for the account/day
allowance. The existing usable/available counters retain their meanings, with
short reservations shared by all devices. The new clients validate against
that explicit allowance (at most one day); responses without it retain the
one-hour fallback. Older clients continue to connect, but show an unknown
balance while it exceeds their former one-hour display cap; update the client
to see the full amount. API field names and ordinary Free responses are unchanged.

Validation covers scoped allowance, reset idempotency/conflict, invalid values,
UTC expiry, active reservations, unchanged account rights and both client
counters. Release SHA/run/attempt, native screenshots and the requested operator
reset are recorded in the task PR after CI/deployment. This source document is
not a claim that a reset or deployment has already occurred.
