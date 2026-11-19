"""Forced SSH command for test grants on real nodes; no shell or fleet administration.

Install beside the unchanged owner helpers. Its separate key must use restrict,
from=<test-controller-address>,command=<this helper>. Node timers keep expiring grants.
"""

import json
import os
import sys
import time
from ipaddress import IPv4Interface
from typing import Any
from uuid import UUID

if __package__:
    from . import managed, node
else:
    import managed  # type: ignore[no-redef,import-not-found]
    import node  # type: ignore[no-redef,import-not-found]

GRANTS = {"grant": "wireguard", "managed-grant": "managed", "grant-relay": "relay"}
REVOKES = {"revoke": "wireguard", "managed-revoke": "managed", "revoke-relay": "relay"}


def existing_paths(identifier: str) -> list[Any]:
    return [
        node.ROOT / "clients" / f"{identifier}.json",
        node.ROOT / "relays" / f"{identifier}.json",
        node.RUN / f"lease-{identifier}.json",
        managed.ROOT / "leases" / f"{identifier}.json",
        managed.ROOT / "closed" / f"{identifier}.json",
    ]


def validate_grant(payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    action, access = payload["action"], payload["access"]
    if access.get("purpose", "client") != "client":
        raise node.Failure("SHARED_ACCESS_DENIED")
    if action == "grant":
        subnet = IPv4Interface(node.read(node.ROOT / "state.json")["configuration"]["address"])
        address = IPv4Interface(access["address"])
        if (
            subnet.network.prefixlen != 24
            or address.network.prefixlen != 32
            or not subnet.network.network_address + 128
            <= address.ip
            < subnet.network.network_address + 192
        ):
            raise node.Failure("SHARED_RESOURCE_DENIED")
    elif action == "managed-grant":
        if not 48000 <= int(access["port"]) < 48500:
            raise node.Failure("SHARED_RESOURCE_DENIED")
    else:
        if (
            not policy.get("relay")
            or not 28000 <= int(access["listen_port"]) < 28500
            or access["target_host"] not in policy["relay_targets"]
            or not (
                int(access["target_port"]) == 51820 or 48000 <= int(access["target_port"]) < 48500
            )
        ):
            raise node.Failure("SHARED_RESOURCE_DENIED")
    # This journal may contain access credentials; it is root-only and never returned.
    return {key: value for key, value in access.items() if key != "expires_at"}


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    if action not in GRANTS and action not in REVOKES:
        raise node.Failure("SHARED_ACTION_DENIED")
    identifier = node.uid(payload["access"]["id"] if action in GRANTS else payload["access_id"])
    if not UUID(identifier).hex.startswith("74657374"):
        raise node.Failure("SHARED_ACCESS_DENIED")
    kind = GRANTS.get(action) or REVOKES[action]
    directory = node.ROOT / "shared-test"
    directory.mkdir(mode=0o700, exist_ok=True)
    journal = directory / f"{identifier}-{kind}.json"
    previous = node.read(journal)
    if not previous and any(path.exists() for path in existing_paths(identifier)):
        # A prefix is not proof of ownership. Never adopt or remove an owner's UUID.
        raise node.Failure("SHARED_FOREIGN_ACCESS")
    if action in GRANTS:
        policy = node.read(node.ROOT / "shared-test-policy.json")
        if not policy.get("enabled"):
            raise node.Failure("SHARED_ACCESS_DISABLED")
        value = validate_grant(payload, policy)
        if previous and (previous.get("closed") or previous.get("access") != value):
            raise node.Failure("SHARED_ACCESS_CONFLICT")
        active_path = (
            managed.ROOT / "leases" / f"{identifier}.json"
            if kind == "managed"
            else node.ROOT / ("relays" if kind == "relay" else "clients") / f"{identifier}.json"
        )
        if node.read(active_path).get("expires", 0) <= time.time():
            count = (
                sum(
                    node.read(path).get("expires", 0) > time.time()
                    for path in (node.ROOT / "relays").glob("*.json")
                )
                if kind == "relay"
                else node.counts()[0] + managed.counts()[0]
            )
            if count >= int(policy["capacity"]):
                raise node.Failure("SHARED_NODE_FULL")
        node.write(journal, json.dumps({"access": value, "closed": False}))
    else:
        if action == "revoke" and payload.get("purpose") != "client":
            raise node.Failure("SHARED_ACCESS_DENIED")
        # Tombstone first so a delayed retry cannot revive a disconnected lease.
        node.write(journal, json.dumps({**previous, "closed": True}))
        if not previous:
            return {"removed": True}
    return managed.dispatch(payload) if action.startswith("managed-") else node.dispatch(payload)


def main() -> None:
    try:
        if os.getuid() != 0:
            raise node.Failure("ROOT_REQUIRED")
        payload = json.loads(sys.stdin.read(16385))
        import fcntl

        # The exact owner's mutex serializes resource checks, journals and mutations.
        with (node.RUN / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = dispatch(payload)
        print(json.dumps(result))
    except Exception as error:
        code = str(error) if isinstance(error, node.Failure) else "SHARED_ACCESS_FAILED"
        print(json.dumps({"error": code}))


if __name__ == "__main__":
    main()
