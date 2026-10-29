"""Ubuntu managed-engine grants. One unprivileged process and hard deadline per lease.

Only the SSH node helper and its systemd supervisor call this module. No network
control listener, credentials in argv, destination logs or arbitrary core config.
"""

import contextlib
import json
import os
import re
import select
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

if __package__:
    from .node import Failure as Failure
    from .node import cmd, public_ip, read, uid, write
else:
    from node import (  # type: ignore[no-redef,import-not-found]
        Failure,
        cmd,
        public_ip,
        read,
        uid,
        write,
    )

ROOT = Path("/etc/prettylisavpn-fleet/managed")
ENGINE = Path("/usr/local/lib/prettylisavpn-fleet/pl-node-engine")
HELPER = Path("/usr/local/lib/prettylisavpn-fleet/managed.py")
METHODS = {
    "AMNEZIA": ("udp",),
    "VLESS_REALITY": ("tcp",),
    "VLESS_TLS": ("tcp",),
    "VMESS_TLS": ("tcp",),
    "SHADOWSOCKS_2022": ("tcp", "udp"),
    "HYSTERIA2_TLS": ("udp",),
    "HYSTERIA1_TLS": ("udp",),
    "HYSTERIA2_SALAMANDER": ("udp",),
}


def unit(identifier: str) -> str:
    return "pl-managed-" + uid(identifier) + ".service"


def lease_path(identifier: str) -> Path:
    return ROOT / "leases" / (uid(identifier) + ".json")


def tombstone(identifier: str) -> Path:
    return ROOT / "closed" / (uid(identifier) + ".json")


def active(identifier: str) -> bool:
    return cmd(
        ["systemctl", "show", "--property=ActiveState", "--value", unit(identifier)], check=False
    ) in ("active", "activating", "deactivating", "reloading")


def configuration(payload: dict[str, Any]) -> dict[str, Any]:
    host = public_ip(payload["host"])
    value = payload["configuration"]
    name, target = str(value["server_name"]), public_ip(value["reality_target"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{1,251}[A-Za-z0-9]", name) or ".." in name:
        raise Failure("MANAGED_CONFIGURATION_INVALID")
    if not ENGINE.is_file():
        raise Failure("MANAGED_ENGINE_MISSING")
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    for folder in ("leases", "closed"):
        (ROOT / folder).mkdir(mode=0o700, exist_ok=True)
    desired = {"host": host, "server_name": name, "reality_target": target}
    state = read(ROOT / "state.json")
    identity = read(ROOT / "identity.json")
    if state and state != desired:
        if any((ROOT / "leases").glob("*.json")):
            raise Failure("NODE_BUSY")
        identity = {}
    if identity and identity["expires"] <= time.time() + 86400:
        if any((ROOT / "leases").glob("*.json")):
            raise Failure("MANAGED_IDENTITY_RENEWAL_REQUIRED")
        identity = {}
    if not identity:
        # Capture privately; the native helper generates keys on the VPN node.
        identity = json.loads(cmd([str(ENGINE), "--identity", name]))
        write(ROOT / "identity.json", json.dumps(identity))
    write(ROOT / "state.json", json.dumps(desired))
    return inspect()


def inspect() -> dict[str, Any]:
    state, identity = read(ROOT / "state.json"), read(ROOT / "identity.json")
    ready = bool(ENGINE.is_file() and state and identity and identity["expires"] > time.time())
    if not ready:
        return {"installed": False}
    authorized, active_count, _, _ = counts()
    return {
        "installed": True,
        "public_key": identity["public_key"],
        "configuration": {
            **state,
            "short_id": identity["short_id"],
            "certificate_pin": identity["certificate_pin"],
            "identity_expires_at": datetime.fromtimestamp(identity["expires"], UTC).isoformat(),
            "methods": list(METHODS),
        },
        "authorized_connections": authorized,
        "active_connections": active_count,
    }


def counts() -> tuple[int, int, int, int]:
    authorized = active_count = rx = tx = 0
    now = time.time()
    for path in (ROOT / "leases").glob("*.json"):
        row = read(path)
        if row.get("purpose", "client") != "client" or row.get("expires", 0) <= now:
            continue
        authorized += 1
        sample = read(path.with_suffix(".stats"))
        if now - sample.get("observed_at", 0) > 30:
            continue
        active_count += now - sample.get("flowed_at", 0) < 180
        rx += sample.get("rx_bytes", 0)
        tx += sample.get("tx_bytes", 0)
    return authorized, active_count, rx, tx


def validate(access: dict[str, Any], now: float) -> dict[str, Any]:
    identifier, secret = uid(access["id"]), uid(access["secret"])
    method, port = str(access["method"]), int(access["port"])
    deadline = datetime.fromisoformat(access["expires_at"])
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise Failure("MANAGED_ACCESS_INVALID")
    expiry = deadline.timestamp()
    purpose = access.get("purpose", "client")
    if purpose not in ("client", "monitor"):
        raise Failure("MANAGED_ACCESS_INVALID")
    if method not in METHODS or not 40000 <= port <= 49999 or not now < expiry <= now + 180:
        raise Failure("MANAGED_ACCESS_INVALID")
    return {
        "id": identifier,
        "secret": secret,
        "method": method,
        "purpose": purpose,
        "port": port,
        "expires": int(expiry),
    }


def firewall(row: dict[str, Any], expiry: float | None) -> None:
    chain = "PLM_" + UUID(row["id"]).hex[:20]
    base = ["iptables", "-w", "5"]
    # A drop-only chain fences traffic before process termination. It is not
    # removed until the systemd control group is confirmed stopped.
    until = datetime.fromtimestamp((expiry or 1) - 1, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    cmd(
        ["iptables-restore", "-w", "5", "--noflush"],
        data=(
            f"*filter\n:{chain} - [0:0]\n-F {chain}\n"
            f"-A {chain} -m time --datestop {until} -j ACCEPT\n-A {chain} -j DROP\nCOMMIT\n"
        ),
    )
    current = cmd(base + ["-S", "INPUT"])
    for network in METHODS[row["method"]]:
        rule = ["-p", network, "--dport", str(row["port"]), "-j", chain]
        if not any(
            f"-p {network} " in line and line.endswith("-j " + chain)
            for line in current.splitlines()
        ):
            cmd(base + ["-I", "INPUT", "1"] + rule)


def remove_firewall(row: dict[str, Any]) -> None:
    chain = "PLM_" + UUID(row["id"]).hex[:20]
    base = ["iptables", "-w", "5"]
    for network in METHODS[row["method"]]:
        cmd(
            base + ["-D", "INPUT", "-p", network, "--dport", str(row["port"]), "-j", chain],
            check=False,
        )
    cmd(base + ["-F", chain], check=False)
    cmd(base + ["-X", chain], check=False)
    if cmd(base + ["-S", chain], check=False):
        raise Failure("MANAGED_FIREWALL_CLEANUP_FAILED")


def grant(access: dict[str, Any]) -> dict[str, Any]:
    row = validate(access, time.time())
    identifier = row["id"]
    if not inspect()["installed"]:
        raise Failure("MANAGED_NOT_CONFIGURED")
    if tombstone(identifier).exists():
        raise Failure("MANAGED_ACCESS_CLOSED")
    path = lease_path(identifier)
    previous = read(path)
    if previous:
        if any(previous[key] != row[key] for key in ("id", "secret", "method", "port", "purpose")):
            raise Failure("MANAGED_ACCESS_CONFLICT")
        if previous["expires"] <= time.time():
            raise Failure("MANAGED_ACCESS_EXPIRED")
    else:
        if any(
            item != path and read(item)["port"] == row["port"]
            for item in path.parent.glob("*.json")
        ):
            raise Failure("MANAGED_PORT_RESERVED")
        for network in METHODS[row["method"]]:
            if cmd(
                [
                    "ss",
                    "-H",
                    "-ltn" if network == "tcp" else "-lun",
                    "sport",
                    "=",
                    str(row["port"]),
                ],
                check=False,
            ):
                raise Failure("MANAGED_PORT_IN_USE")
    # Journal first: interrupted starts/renewals remain visible to autonomous cleanup.
    write(path, json.dumps(row))
    firewall(row, row["expires"])
    if not active(identifier):
        path.with_suffix(".ready").unlink(missing_ok=True)
        cmd(
            [
                "systemd-run",
                "--quiet",
                "--collect",
                "--unit=" + unit(identifier),
                "--property=KillMode=control-group",
                "--property=TimeoutStopSec=3s",
                "--property=NoNewPrivileges=yes",
                "--property=UMask=0077",
                "--property=StandardOutput=null",
                "--property=StandardError=null",
                "/usr/bin/python3",
                str(HELPER),
                "lease",
                identifier,
            ]
        )
    for _ in range(30):
        if path.with_suffix(".ready").exists() and active(identifier):
            return {"granted": True}
        time.sleep(0.1)
    raise Failure("MANAGED_START_UNCONFIRMED")


def revoke(identifier: str) -> dict[str, Any]:
    identifier = uid(identifier)
    (ROOT / "closed").mkdir(mode=0o700, parents=True, exist_ok=True)
    # Late retries of an older grant cannot recreate a revoked authorization.
    write(tombstone(identifier), json.dumps({"id": identifier, "closed_at": time.time()}))
    path = lease_path(identifier)
    row = read(path)
    if row:
        firewall(row, None)
    if active(identifier):
        cmd(["systemctl", "stop", unit(identifier)], timeout=10)
    if active(identifier):
        return {"removed": False}
    if row:
        for network in METHODS[row["method"]]:
            if cmd(
                [
                    "ss",
                    "-H",
                    "-ltn" if network == "tcp" else "-lun",
                    "sport",
                    "=",
                    str(row["port"]),
                ],
                check=False,
            ):
                return {"removed": False}
        remove_firewall(row)
    path.unlink(missing_ok=True)
    path.with_suffix(".ready").unlink(missing_ok=True)
    path.with_suffix(".stats").unlink(missing_ok=True)
    return {"removed": True}


def cleanup() -> None:
    for path in (ROOT / "leases").glob("*.json"):
        if read(path).get("expires", 0) <= time.time() or tombstone(path.stem).exists():
            revoke(path.stem)


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload["action"]
    if action == "managed-inspect":
        return inspect()
    if action == "managed-configure":
        return configuration(payload)
    if action == "managed-grant":
        return grant(payload["access"])
    if action == "managed-revoke":
        return revoke(payload["access_id"])
    if action == "managed-cleanup":
        cleanup()
        return {"removed": True}
    if action == "managed-probe":
        measure = read(ROOT.parent / "measure.json")
        result = cmd(
            [str(ENGINE), "--probe"],
            data=json.dumps(
                {
                    "profile": payload["profile"],
                    "measure_host": measure["host"],
                    "measure_ca": (ROOT.parent / "measure.crt").read_text(),
                    "measure_token": measure["token"],
                    "expected_egress_ips": payload["expected_egress_ips"],
                }
            ),
            timeout=85,
        )
        return dict(json.loads(result))
    raise Failure("ACTION_UNSUPPORTED")


def supervise(identifier: str) -> None:
    path = lease_path(identifier)
    row, identity, state = read(path), read(ROOT / "identity.json"), read(ROOT / "state.json")
    if not row or tombstone(identifier).exists() or row["expires"] <= time.time():
        return
    payload = {
        **{key: row[key] for key in ("id", "secret", "method", "port", "expires")},
        "listen": state["host"],
        "target": state["reality_target"],
        **{key: identity[key] for key in ("private_key", "server_name", "short_id")},
    }
    if row["method"] not in ("VLESS_REALITY", "AMNEZIA", "SHADOWSOCKS_2022"):
        payload.update({key: identity[key] for key in ("tls_certificate", "tls_key")})
    child = subprocess.Popen(
        [str(ENGINE), "--lease", identifier],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        user="prettylisa-fleet",
        group="prettylisa-fleet",
    )
    try:
        assert child.stdin and child.stdout
        child.stdin.write(json.dumps(payload).encode() + b"\n")
        child.stdin.flush()
        if (
            not select.select([child.stdout], [], [], 5)[0]
            or child.stdout.readline(32) != b"READY\n"
        ):
            return
        write(path.with_suffix(".ready"), "ready\n")
        expires = row["expires"]
        sample = {"rx_bytes": 0, "tx_bytes": 0, "flowed_at": 0.0}
        while child.poll() is None:
            time.sleep(0.5)
            renewed = read(path)
            if not renewed or tombstone(identifier).exists() or renewed["expires"] <= time.time():
                return
            if any(
                renewed[key] != row[key] for key in ("id", "secret", "method", "port", "purpose")
            ):
                return
            if select.select([child.stdout], [], [], 0)[0]:
                raw = child.stdout.readline(256)
                counters = json.loads(raw)
                if set(counters) != {"rx_bytes", "tx_bytes"} or any(
                    type(value) is not int or value < 0 for value in counters.values()
                ):
                    return
                if any(counters[key] > sample[key] for key in counters):
                    sample["flowed_at"] = time.time()
                sample.update(counters)
                write(
                    path.with_suffix(".stats"), json.dumps({**sample, "observed_at": time.time()})
                )
            if renewed["expires"] != expires:
                expires = renewed["expires"]
                child.stdin.write(json.dumps({"expires": expires}).encode() + b"\n")
                child.stdin.flush()
    finally:
        path.with_suffix(".ready").unlink(missing_ok=True)
        path.with_suffix(".stats").unlink(missing_ok=True)
        with contextlib.suppress(ProcessLookupError):
            child.kill()
        child.wait(timeout=5)
        if child.stdin:
            child.stdin.close()
        if child.stdout:
            child.stdout.close()


if __name__ == "__main__":
    try:
        if os.getuid() != 0 or len(sys.argv) != 3 or sys.argv[1] != "lease":
            raise SystemExit(1)
        supervise(uid(sys.argv[2]))
    except Exception:
        # The service journal contains no private profile or exception text.
        raise SystemExit(1) from None
