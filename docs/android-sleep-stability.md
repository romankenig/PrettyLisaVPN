# Android sleep stability and occupied-node monitoring

## Scope and versions

Backend 0.18.1 → 0.19.0; Android 0.12.1/code 22 → 0.12.2/code 23.
Windows remains 0.15.0, dashboard 0.1.0, schema 0030. No new endpoint or migration.
The backend adds the optional `heartbeat_required=false` response capability.
Older clients ignore it; the new Android client uses its original bounded policy
when the field is absent or true. This preserves rollback compatibility.

## Evidence that motivated the change

On 2026-10-27, the owner's DE session started at 13:01:42 UTC. The final API
heartbeat arrived at 13:07:05; the worker removed the peer at 13:08:46 with
VPN_CLIENT_LOST. The owner reported that the screen was off for part of that test.
On 2026-10-28, the owner switched eSIM → Wi-Fi at approximately 08:49 UTC with
mobile data disabled and kept the screen on. Server observation confirmed over
35 minutes of traffic and repeated WireGuard rekeys. This supports addressing
sleep-sensitive control traffic; it does not prove ISP behavior in every network.

## Access lifetime

HTTP polling is telemetry/reconciliation, not proof that a sleeping phone remains
authorized. Once provisioned, the worker maintains the existing peer while the
account, device, auth session, node and entitlement remain valid. Free ends at its
reserved quota deadline or UTC midnight; paid access ends at the paid/auth deadline.
Explicit disconnect/logout/device revocation still cleans up the peer and releases
unused quota only after confirmed removal. Failed provisioning expires after 90 s.
Node grants remain at most 180 s, refreshed by the main-server worker every 30 s;
kernel rules and node timers still enforce expiry independently of the API.

Sleeping or crashed clients keep their reservation until confirmed cleanup or an
access deadline. This deliberately avoids treating CPU suspension as Disconnect.
For Free, time continues to count while connected/asleep, as for an active tunnel.
After process restart, Connect first removes the old reservation. This task does
not add automatic recovery from force-stop, reboot or OS process termination.

Android retains its foreground VPN service and uses no permanent wake lock or
repeating exact alarm to defeat battery saving. It does not put a disconnect timer
around sleep-sensitive heartbeat delays. HTTP requests remain individually bounded;
temporary offline/network/service errors retry while the same tunnel stays up.
An ambiguous refresh is not replayed and does not itself revoke the existing VPN
grant; account recovery still requires the existing OTP flow. Confirmed denial,
closed lease, deadline or Android VPN revocation stops the tunnel. Android may
defer background network activity during Doze; the goal is preserving the tunnel
and resuming traffic after wake, not forcing all applications to run while asleep.

## Full checks with customers

Every hourly check retains handshake, DNS, HTTPS, exit-IP and bounded throughput
measurements even with customer peers present. A reserved address and isolated
namespace keep the test independent. Unknown foreign peers remain protected.
The result also carries customer active/authorized counts, excluding the probe.
Default weights remain 50% availability, 20% spare active capacity, 15% connection
speed and 15% measured throughput. Missing passive evidence is no longer produced
merely because a customer is connected. Existing historical failures remain intact.

CHECK locks permit customer grant renewal/revocation without losing ownership.
Fleet claims exclude in-flight customer claims; configuration stays exclusive.
Long namespace probes release the helper's global mutation lock. Roll out helpers
to DE/US/RU before relying on occupied-node probes; preserve keys and inventory.

## Validation and release evidence

Required regressions: absent capability on a legacy backend; long client sleep;
Free/Premium/Platinum access; terminal revocation/expiry; cancellation; ambiguous
refresh without replay; shared CHECK vs exclusive CONFIGURE; monitor/customer key
isolation; load score and complete synthetic evidence. Real opt-in Android
acceptance holds one tunnel for two minutes, forces five minutes of deep Doze,
wakes it, checks the same VPN Network and working tunnel HTTPS, then confirms
disconnect. No phone USB is needed for the isolated emulator test.

Exact source HEAD, complete CI audit, build SHA/run/attempt, APK checksum and
development deployment evidence belong in the task PR after verification. No
success is claimed from older APKs. Physical-phone sleep acceptance remains a
separate owner test using the delivered APK.

## Rollback

Retain the previous immutable backend image and node helper files. No schema
downgrade is needed. Backend rollback restores the old liveness timeout; new
Android sessions detect the absent capability, while already running new-mode
sessions can be removed by the older worker and must reconnect. Android rollback
restores its old timeout behavior even on the newer backend. Keep canonical fleet
inventory, credentials and all three nodes; do not regenerate a DE/US-only roster.
