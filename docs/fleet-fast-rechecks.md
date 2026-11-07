# Independent retry observers — backend 0.35.1

Backend 0.35.0 → 0.35.1 is a reliability PATCH; schema remains 0045. Three-minute
retries, checks following failed/unknown outcomes and expired worker claims choose
a randomized configured/enabled source, excluding the target and the previous
observer whenever another source exists. Hourly healthy checks retain their
existing rotation. A locked alternative postpones the queued attempt by 15 seconds;
it does not fall back to the same observer. If the fleet has only one eligible
observer at all, it is the only possible source; a one-node fleet remains UNKNOWN.

The selected observer is saved in server-owned operation result metadata before
network work. It survives worker restarts and control/source failures, while
request parameters remain unchanged for idempotent enqueue. Public observation
source_id still names only actual synthetic probes; passive/control observations
do not pretend a VPN test ran. Every target/method has independent observer history.

UNKNOWN results, including unreachable/unconfigured observers and uncertain
cleanup, have a null historical quality rather than a fabricated zero. Current
availability remains conservatively unconfirmed and is retried; successful or
failed VPN evidence and existing rating history are not rewritten. A failed
handshake does not by itself identify which side of the path failed; changing
the next observer supplies independent follow-up evidence.

Unit and PostgreSQL integration coverage includes restart/lease recovery,
alternating observers, unavailable alternatives, idempotency and honest historical
quality/source fields. Exact product/build SHA, CI and deployment follow the task PR.

# Zero-rating retries — backend 0.22.1

Backend 0.22.0 → 0.22.1 is a scheduler patch; database schema remains 0035.
Android/Windows/dashboard versions do not change for this rule. The scheduler
runs in the durable main-server fleet worker, with PostgreSQL-owned operations
and deadlines. No Codex/ChatGPT automation is involved.

Each configured method uses the same current 24-hour rating calculation as
monitoring, including configured weights, capacity, stale data and verification
state. A zero rating selects a 180-second period; a positive rating selects the
normal 3600-second period. Existing hour-away deadlines are shortened when the
rating reaches zero. A completed observation clears the old deadline so the
next worker cycle applies its new rating, including recovery to hourly checks.

Stable UUID-based slots spread the configured node/method roster within either
period. New enabled/configured nodes enter automatically. Missed slots are not
replayed after an outage, and an existing queued/running operation prevents a
duplicate for that target. Existing target/source locks and cleanup rules stay
in force: a busy operation must finish before another probe can start. A Free
user's active connection alone does not cause a zero score or suppress a probe.

The dashboard receives the actual next_check_at and retains each observed
measurement. No new endpoint, fabricated history or schema migration is needed.
Disabling a node excludes it as before; an unconfigured node cannot be tested
until initial setup is requested.

Validation: 25 unit tests pass, including distinct three-minute slots, exact
180-second recurrence and preserved hourly slots. A fresh isolated PostgreSQL
database passed migrations through 0035, Alembic check and 42 fleet/publication
tests. Integration cases cover stale/unverified zero ratings, shortening an
existing deadline, failed checks, duplicate prevention and hourly recovery with
active connections. Final source/build/deployment evidence belongs in PR #38.

Pending: complete HEAD CI, immutable backend deployment on the main server, and
readback of live next-check deadlines. Existing clients and WireGuard access must
remain available during rollout; managed-transport admission stays separately
controlled by its explicit server setting.
