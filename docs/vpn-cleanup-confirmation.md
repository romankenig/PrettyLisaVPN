# Confirmed VPN cleanup

Backend 0.12.0 → 0.13.0; Windows 0.12.0 → 0.12.1;
Android 0.8.0/code15 → 0.8.1/code16. Schema remains 0027.

`DELETE /vpn/sessions/{id}` accepts the optional `X-VPN-Cleanup: 1` header.
Only opted-in responses include `cleanup_confirmed: boolean`. Legacy responses
retain exactly `session_id` and `status`. A terminal status records durable
termination intent; it does not itself prove the peer was removed.

Confirmation is true only after successful node removal and database commit,
or when the stored removal acknowledgement already exists. Node outages and
failed commits return false; reconciliation and repeated DELETE remain safe.
Ownership/authentication checks are unchanged.

Both clients request this contract and require literal boolean true for the
requested session ID. Missing, malformed, false or mismatched responses keep
their existing cleanup retry state. Android retains its existing authoritative
owned-session-not-found handling. No extra private material or network traffic
is logged.

Deploy backend first, then update clients. New clients against an older backend
deliberately retain cleanup-pending rather than assuming success. Existing
clients continue using the legacy response. This change does not advertise
OpenVPN capabilities or implement automatic transport fallback.

## External-client acceptance

The owner selected separately installed official OpenVPN clients first.
Windows OpenVPN Community 2.7.7 was installed; OpenVPN for Android was already
installed. Separate diagnostic certificates expire after two hours and are
never committed. DE TLS handshake and tunnel-address allocation were observed
on both devices, but a successful data path must be established separately.
Windows has an active Kaspersky VPN required for this development connection;
only isolated destination checks are suitable while it remains active.
Android previously passed DE HTTPS in an earlier test; that is not evidence
for the current certificates/network or an integrated PrettyLisaVPN engine.

Product source SHA, actual CI build SHA/run/attempt, test totals and final
device results are recorded in the task PR after the last push. No new client
build or backend deployment is claimed before those checks finish.
