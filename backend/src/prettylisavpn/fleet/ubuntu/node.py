"""Ubuntu-only privileged helper. JSON protocol; never prints command output or secrets.

The measurement service is unprivileged. Probe namespaces have no host-side veth,
so loss of WireGuard cannot fall back to the host's default Internet connection.
"""

import contextlib
import hmac
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from uuid import UUID

ROOT = Path("/etc/prettylisavpn-fleet")
RUN = Path("/run/prettylisavpn-fleet")
WG = "pl-wg0"
HELPER = "/usr/local/lib/prettylisavpn-fleet/node.py"
FIREWALL_UNIT = Path("/etc/systemd/system/wg-quick@pl-wg0.service.d/50-prettylisavpn-firewall.conf")
MAX_BYTES = 8 * 1024 * 1024
KEY = re.compile(r"^[A-Za-z0-9+/]{43}=$")
BLOCKED = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "240.0.0.0/4",
)


class Failure(Exception):
    pass


def cmd(args: list[str], *, data: str | None = None, timeout: int = 20, check: bool = True) -> str:
    try:
        result = subprocess.run(
            args,
            input=data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Failure("NODE_COMMAND_FAILED") from None
    if check and result.returncode:
        raise Failure("NODE_COMMAND_FAILED")
    return result.stdout.strip() if result.returncode == 0 else ""


def write(path: Path, value: str, mode: int = 0o600) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, mode)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def uid(value: Any) -> str:
    return str(UUID(str(value)))


def public_ip(value: Any) -> str:
    address = ipaddress.IPv4Address(value)
    if not address.is_global:
        raise Failure("INVALID_PUBLIC_ADDRESS")
    return str(address)


def validated_config(value: dict[str, Any]) -> dict[str, Any]:
    address = ipaddress.IPv4Interface(value["address"])
    private = any(
        address.ip in ipaddress.IPv4Network(block)
        for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )
    port, mtu = int(value.get("listen_port", 51820)), int(value.get("mtu", 1380))
    if (
        not private
        or not 24 <= address.network.prefixlen <= 28
        or address.ip != address.network.network_address + 1
        or not 1024 <= port <= 65535
        or not 1280 <= mtu <= 1420
    ):
        raise Failure("INVALID_CONFIGURATION")
    return {"address": str(address), "listen_port": port, "mtu": mtu}


def wg(field: str) -> str:
    # Never query dump/showconf/private-key: public field allowlist only.
    if field not in ("peers", "public-key", "latest-handshakes", "transfer"):
        raise Failure("INVALID_FIELD")
    return cmd(["wg", "show", WG, field])


def peers() -> list[str]:
    return wg("peers").splitlines()


def counts() -> tuple[int, int, int, int]:
    monitors = {row["public_key"] for path in RUN.glob("lease-*.json") if (row := read(path))}
    users = set(peers()) - monitors
    handshakes = {
        key: int(at) for key, at in (line.split() for line in wg("latest-handshakes").splitlines())
    }
    transfer = {
        key: (int(rx), int(tx))
        for key, rx, tx in (line.split() for line in wg("transfer").splitlines())
    }
    active = sum(time.time() - handshakes.get(key, 0) < 180 for key in users)
    return (
        len(users),
        active,
        sum(transfer.get(key, (0, 0))[0] for key in users),
        sum(transfer.get(key, (0, 0))[1] for key in users),
    )


def inspect() -> dict[str, Any]:
    state = read(ROOT / "state.json")
    installed = state.get("committed", False) and bool(cmd(["ip", "link", "show", WG], check=False))
    users, active, _, _ = counts() if installed else (0, 0, 0, 0)
    relays = [read(path) for path in (ROOT / "relays").glob("*.json")]
    # Relay load is an authorized reservation, not a fabricated WireGuard handshake.
    relay_load = sum(row.get("expires", 0) > time.time() for row in relays)
    return {
        "installed": bool(installed),
        "public_key": wg("public-key") if installed else None,
        "configuration": state.get("configuration", {}),
        "authorized_connections": users + len(relays),
        "active_connections": active + relay_load,
    }


def firewall(up: bool) -> None:
    state = read(ROOT / "state.json")
    if not state:
        return
    config, uplink = state["configuration"], state["uplink"]
    subnet = str(ipaddress.IPv4Interface(config["address"]).network)
    chains: list[tuple[str, str, str, list[list[str]]]] = [
        (
            "filter",
            "PLF_INPUT",
            "INPUT",
            [
                ["-i", WG, "-j", "DROP"],
                ["-p", "udp", "--dport", str(config["listen_port"]), "-j", "ACCEPT"],
                ["-p", "tcp", "--dport", "8443", "-j", "ACCEPT"],
            ],
        ),
        (
            "filter",
            "PLF_FORWARD",
            "FORWARD",
            [
                *[["-i", WG, "-d", block, "-j", "DROP"] for block in BLOCKED],
                ["-i", WG, "-s", subnet, "-o", uplink, "-j", "ACCEPT"],
                [
                    "-o",
                    WG,
                    "-d",
                    subnet,
                    "-m",
                    "conntrack",
                    "--ctstate",
                    "ESTABLISHED,RELATED",
                    "-j",
                    "ACCEPT",
                ],
                ["-i", WG, "-j", "DROP"],
                ["-o", WG, "-j", "DROP"],
            ],
        ),
        ("nat", "PLF_NAT", "POSTROUTING", [["-s", subnet, "-o", uplink, "-j", "MASQUERADE"]]),
    ]
    for table, chain, parent, rules in chains:
        base = ["iptables", "-w", "5", "-t", table]
        hook = ["-m", "comment", "--comment", "PrettyLisaVPN-fleet", "-j", chain]
        if up:
            if not cmd(base + ["-S", chain], check=False):
                cmd(base + ["-N", chain])
            for rule in rules:
                exists = (
                    subprocess.run(
                        base + ["-C", chain] + rule,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                    == 0
                )
                if not exists:
                    cmd(base + ["-A", chain] + rule)
            exists = (
                subprocess.run(
                    base + ["-C", parent] + hook,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            )
            if not exists:
                cmd(base + ["-I", parent, "1"] + hook)
        else:
            cmd(base + ["-D", parent] + hook, check=False)
            cmd(base + ["-F", chain], check=False)
            cmd(base + ["-X", chain], check=False)


def configure(payload: dict[str, Any]) -> dict[str, Any]:
    import grp

    config, operation = validated_config(payload["configuration"]), uid(payload["operation_id"])
    host = public_ip(payload["host"])
    old = read(ROOT / "state.json")
    if old:
        if old["configuration"] != config or old["host"] != host:
            raise Failure("CONFIGURATION_IMMUTABLE")
        if old.get("committed"):
            if not inspect()["installed"]:
                cmd(["systemctl", "start", "wg-quick@" + WG], timeout=40)
            return inspect()
        if old["operation_id"] != operation:
            raise Failure("INCOMPLETE_CONFIGURATION_REQUIRES_ROLLBACK")
    elif Path("/etc/wireguard/" + WG + ".conf").exists() or cmd(
        ["ip", "link", "show", WG], check=False
    ):
        raise Failure("UNOWNED_INTERFACE_EXISTS")
    else:
        for table, chain in (
            ("filter", "PLF_INPUT"),
            ("filter", "PLF_FORWARD"),
            ("nat", "PLF_NAT"),
        ):
            if cmd(["iptables", "-t", table, "-S", chain], check=False):
                raise Failure("UNOWNED_FIREWALL_CHAIN_EXISTS")
        if cmd(["ss", "-H", "-ltn", "sport = :8443"]):
            raise Failure("MEASUREMENT_PORT_IN_USE")
        subnet = ipaddress.IPv4Interface(config["address"]).network
        for route in json.loads(cmd(["ip", "-j", "route", "show"])):
            destination = route.get("dst", "default")
            if destination != "default" and subnet.overlaps(
                ipaddress.IPv4Network(destination, strict=False)
            ):
                raise Failure("SUBNET_ROUTE_CONFLICT")
        links = json.loads(cmd(["ip", "-j", "route", "get", "1.1.1.1"]))
        uplink = links[0]["dev"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", uplink):
            raise Failure("UPLINK_INVALID")
        old = {
            "configuration": config,
            "host": host,
            "operation_id": operation,
            "committed": False,
            "uplink": uplink,
            "previous_forward": cmd(["sysctl", "-n", "net.ipv4.ip_forward"]),
        }
        ROOT.mkdir(mode=0o750, exist_ok=True)
        os.chown(ROOT, 0, grp.getgrnam("prettylisa-fleet").gr_gid)
        write(ROOT / "state.json", json.dumps(old))
    private = ROOT / "wireguard.key"
    if not private.exists():
        write(private, cmd(["wg", "genkey"]) + "\n")
    key = private.read_text(encoding="utf-8").strip()
    Path("/etc/wireguard").mkdir(mode=0o700, exist_ok=True)
    write(
        Path("/etc/wireguard/" + WG + ".conf"),
        (
            f"[Interface]\nAddress = {config['address']}\n"
            f"ListenPort = {config['listen_port']}\nPrivateKey = {key}\n"
            f"MTU = {config['mtu']}\n"
        ),
    )
    # Ubuntu 26.04 confines wg-quick with AppArmor: Python hooks cannot inherit
    # that profile. systemd starts our fixed helper separately, with no profile
    # relaxation. StopPost also removes owned rules when startup fails.
    FIREWALL_UNIT.parent.mkdir(parents=True, exist_ok=True)
    write(
        FIREWALL_UNIT,
        f"[Service]\nExecStartPost=/usr/bin/python3 {HELPER} firewall-up\n"
        f"ExecStopPost=/usr/bin/python3 {HELPER} firewall-down\n",
        0o644,
    )
    cmd(["systemctl", "daemon-reload"])
    write(Path("/etc/sysctl.d/90-prettylisavpn-fleet.conf"), "net.ipv4.ip_forward=1\n", 0o644)
    cmd(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    if not (ROOT / "measure.key").exists():
        cmd(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "365",
                "-keyout",
                str(ROOT / "measure.key"),
                "-out",
                str(ROOT / "measure.crt"),
                "-subj",
                "/CN=" + host,
                "-addext",
                "subjectAltName=IP:" + host,
            ],
            timeout=30,
        )
        write(
            ROOT / "measure.json",
            json.dumps({"token": secrets.token_urlsafe(32), "host": host}),
            0o640,
        )
        for name in ("measure.key", "measure.crt", "measure.json"):
            os.chmod(ROOT / name, 0o640)
            os.chown(ROOT / name, 0, grp.getgrnam("prettylisa-fleet").gr_gid)
    cmd(["systemctl", "enable", "--now", "wg-quick@" + WG], timeout=45)
    cmd(["systemctl", "enable", "--now", "prettylisa-fleet-measure"], timeout=30)
    for attempt in range(10):
        try:
            measure_request("/ip")
            break
        except (OSError, Failure):
            if attempt == 9:
                raise Failure("MEASUREMENT_SERVICE_NOT_READY") from None
            time.sleep(0.5)
    old["committed"] = True
    write(ROOT / "state.json", json.dumps(old))
    return inspect()


def rollback(operation: str) -> dict[str, Any]:
    state = read(ROOT / "state.json")
    if not state or state["operation_id"] != uid(operation) or state.get("committed"):
        return {"rolled_back": False}
    cmd(["systemctl", "disable", "--now", "wg-quick@" + WG], check=False, timeout=40)
    cmd(["systemctl", "disable", "--now", "prettylisa-fleet-measure"], check=False, timeout=30)
    firewall(False)
    Path("/etc/wireguard/" + WG + ".conf").unlink(missing_ok=True)
    FIREWALL_UNIT.unlink(missing_ok=True)
    cmd(["systemctl", "daemon-reload"])
    Path("/etc/sysctl.d/90-prettylisavpn-fleet.conf").unlink(missing_ok=True)
    cmd(["sysctl", "-w", "net.ipv4.ip_forward=" + state["previous_forward"]])
    (ROOT / "state.json").unlink()
    return {"rolled_back": True}


def grant(access: dict[str, Any]) -> dict[str, Any]:
    if access.get("purpose") == "client":
        return grant_client(access)
    identifier, key = uid(access["id"]), str(access["public_key"])
    config = read(ROOT / "state.json")["configuration"]
    reserved = str(ipaddress.IPv4Interface(config["address"]).network.broadcast_address - 1) + "/32"
    expiry = datetime.fromisoformat(access["expires_at"]).timestamp()
    if (
        not KEY.fullmatch(key)
        or access["address"] != reserved
        or not time.time() < expiry <= time.time() + 300
    ):
        raise Failure("ACCESS_INVALID")
    path = RUN / ("lease-" + identifier + ".json")
    existing = read(path)
    known = {read(item)["public_key"] for item in (ROOT / "clients").glob("*.json")}
    known.update(read(item)["public_key"] for item in RUN.glob("lease-*.json"))
    present = set(peers())
    if present - known:
        # Unmanaged peers can own the reserved address; never take their route.
        raise Failure("NODE_BUSY")
    if existing and existing["public_key"] != key:
        raise Failure("ACCESS_CONFLICT")
    if not existing and key in present:
        raise Failure("ACCESS_CONFLICT")
    for other in RUN.glob("lease-*.json"):
        if other != path:
            raise Failure("NODE_BUSY")
    # Journal before mutation, so interruption can always be cleaned up by the timer.
    write(path, json.dumps({"public_key": key, "expires": expiry}))
    cmd(["wg", "set", WG, "peer", key, "allowed-ips", reserved])
    return {"granted": True}


def revoke(identifier: str, purpose: str = "monitor") -> dict[str, Any]:
    if purpose not in ("monitor", "client"):
        raise Failure("ACCESS_INVALID")
    path = (
        (ROOT / "clients" / (uid(identifier) + ".json"))
        if purpose == "client"
        else RUN / ("lease-" + uid(identifier) + ".json")
    )
    row = read(path)
    if row:
        if cmd(["ip", "link", "show", WG], check=False):
            cmd(["wg", "set", WG, "peer", row["public_key"], "remove"])
            if row["public_key"] in peers():
                return {"removed": False}
        if purpose == "client":
            client_firewall(identifier, row["address"], None)
        path.unlink()
    return {"removed": True}


def client_firewall(identifier: str, address: str, expiry: float | None) -> None:
    # Kernel UTC deadline: traffic stops even if both worker and cleanup timer fail.
    chain = "PLU_" + UUID(identifier).hex[:20]
    base = ["iptables", "-w", "5"]
    hooks = [["-i", WG, "-s", address, "-j", chain], ["-o", WG, "-d", address, "-j", chain]]
    if expiry is None:
        for hook in hooks:
            cmd(base + ["-D", "PLF_FORWARD"] + hook, check=False)
        cmd(base + ["-F", chain], check=False)
        cmd(base + ["-X", chain], check=False)
        if cmd(base + ["-S", chain], check=False):
            raise Failure("CLIENT_FIREWALL_CLEANUP_FAILED")
        return
    # xt_time uses UTC unless --kerneltz is requested. Never allow beyond the deadline.
    until = datetime.fromtimestamp(expiry - 1, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    cmd(
        ["iptables-restore", "-w", "5", "--noflush"],
        data=(
            f"*filter\n:{chain} - [0:0]\n-F {chain}\n"
            f"-A {chain} -m time --datestop {until} -j RETURN\n-A {chain} -j DROP\nCOMMIT\n"
        ),
    )
    rules = cmd(base + ["-S", "PLF_FORWARD"]).splitlines()
    for hook in hooks:
        if not any(line.endswith("-j " + chain) and f"{hook[0]} {WG} " in line for line in rules):
            cmd(base + ["-I", "PLF_FORWARD", "1"] + hook)


def grant_client(access: dict[str, Any]) -> dict[str, Any]:
    identifier, key = uid(access["id"]), str(access["public_key"])
    config = read(ROOT / "state.json")["configuration"]
    subnet = ipaddress.IPv4Interface(config["address"]).network
    address = ipaddress.IPv4Interface(access["address"])
    expiry = datetime.fromisoformat(access["expires_at"]).timestamp()
    if (
        not KEY.fullmatch(key)
        or address.network.prefixlen != 32
        or not subnet.network_address + 2 <= address.ip <= subnet.broadcast_address - 2
        or not time.time() < expiry <= time.time() + 185
    ):
        raise Failure("ACCESS_INVALID")
    directory = ROOT / "clients"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (identifier + ".json")
    existing = read(path)
    if existing and (existing["public_key"] != key or existing["address"] != str(address)):
        raise Failure("ACCESS_CONFLICT")
    for other in directory.glob("*.json"):
        row = read(other)
        if other != path and (row["public_key"] == key or row["address"] == str(address)):
            raise Failure("ACCESS_CONFLICT")
    # Monitor and customer namespaces cannot take ownership of each other's peer.
    for other in RUN.glob("lease-*.json"):
        if read(other)["public_key"] == key:
            raise Failure("ACCESS_CONFLICT")
    if not existing and key in peers():
        raise Failure("ACCESS_CONFLICT")
    write(path, json.dumps({"public_key": key, "address": str(address), "expires": expiry}))
    client_firewall(identifier, str(address), expiry)
    cmd(["wg", "set", WG, "peer", key, "allowed-ips", str(address)])
    return {"granted": True}


def relay_rules(identifier: str, row: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    host, port, target, target_port = (
        row["host"],
        str(row["listen_port"]),
        row["target_host"],
        str(row["target_port"]),
    )
    chain = "PLR_" + UUID(identifier).hex[:20]
    comment = ["-m", "comment", "--comment", "PrettyLisaVPN-relay-" + identifier]
    original = ["-m", "conntrack", "--ctproto", "udp", "--ctorigdst", host, "--ctorigdstport", port]
    return [
        ("filter", "FORWARD", ["-p", "udp"] + original + comment + ["-j", chain]),
        (
            "nat",
            "POSTROUTING",
            ["-p", "udp", "-d", target, "--dport", target_port]
            + original
            + comment
            + ["-j", "MASQUERADE"],
        ),
        (
            "nat",
            "PREROUTING",
            ["-p", "udp", "-d", host, "--dport", port]
            + comment
            + ["-j", "DNAT", "--to-destination", target + ":" + target_port],
        ),
    ]


def has_rule(table: str, parent: str, rule: list[str]) -> bool:
    result = subprocess.run(
        ["iptables", "-w", "5", "-t", table, "-C", parent] + rule,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise Failure("RELAY_FIREWALL_UNAVAILABLE")
    return result.returncode == 0


def relay_deadline(identifier: str, expiry: float | None) -> None:
    chain = "PLR_" + UUID(identifier).hex[:20]
    allow = ""
    if expiry is not None:
        until = datetime.fromtimestamp(expiry - 1, UTC).strftime("%Y-%m-%dT%H:%M:%S")
        allow = f"-A {chain} -m time --datestop {until} -j ACCEPT\n"
    cmd(
        ["iptables-restore", "-w", "5", "--noflush"],
        data=(f"*filter\n:{chain} - [0:0]\n-F {chain}\n{allow}-A {chain} -j DROP\nCOMMIT\n"),
    )


def grant_relay(access: dict[str, Any]) -> dict[str, Any]:
    identifier = uid(access["id"])
    state = read(ROOT / "state.json")
    host, target = public_ip(state["host"]), public_ip(access["target_host"])
    port, target_port = int(access["listen_port"]), int(access["target_port"])
    expiry = datetime.fromisoformat(access["expires_at"]).timestamp()
    if (
        not state.get("committed")
        or host == target
        or not 20000 <= port <= 29999
        or not 1024 <= target_port <= 65535
        or not time.time() < expiry <= time.time() + 185
    ):
        raise Failure("RELAY_ACCESS_INVALID")
    directory = ROOT / "relays"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (identifier + ".json")
    row = {"host": host, "target_host": target, "listen_port": port, "target_port": target_port}
    existing = read(path)
    if existing and any(existing.get(key) != value for key, value in row.items()):
        raise Failure("RELAY_ACCESS_CONFLICT")
    for other in directory.glob("*.json"):
        if other != path and read(other).get("listen_port") == port:
            raise Failure("RELAY_PORT_IN_USE")
    if not existing:
        if cmd(["ss", "-H", "-lun", "sport = :" + str(port)]):
            raise Failure("RELAY_PORT_IN_USE")
        chain = "PLR_" + UUID(identifier).hex[:20]
        if cmd(["iptables", "-w", "5", "-S", chain], check=False):
            raise Failure("UNOWNED_RELAY_RULES")
    # Journal before mutation. A failed grant is recoverable by the node timer.
    row["expires"] = expiry
    write(path, json.dumps(row))
    # Install the bounded filter before exposing the UDP forwarding port.
    relay_deadline(identifier, expiry)
    for table, parent, rule in relay_rules(identifier, row):
        if not has_rule(table, parent, rule):
            cmd(["iptables", "-w", "5", "-t", table, "-I", parent, "1"] + rule)
    return {"granted": True}


def revoke_relay(identifier: str) -> dict[str, Any]:
    identifier = uid(identifier)
    path = ROOT / "relays" / (identifier + ".json")
    row = read(path)
    if not row:
        return {"removed": True}
    # First block existing flows, then remove DNAT so new flows cannot be created.
    relay_deadline(identifier, None)
    rules = relay_rules(identifier, row)
    for table, parent, rule in reversed(rules[1:]):
        if has_rule(table, parent, rule):
            cmd(["iptables", "-w", "5", "-t", table, "-D", parent] + rule)
        if has_rule(table, parent, rule):
            raise Failure("RELAY_CLEANUP_FAILED")
    selector = [
        "-p",
        "udp",
        "--orig-dst",
        row["host"],
        "--dport",
        str(row["listen_port"]),
        "--dst-nat",
    ]
    cmd(["conntrack", "-D"] + selector, check=False)
    if cmd(["conntrack", "-L"] + selector):
        raise Failure("RELAY_CLEANUP_FAILED")
    table, parent, rule = rules[0]
    if has_rule(table, parent, rule):
        cmd(["iptables", "-w", "5", "-t", table, "-D", parent] + rule)
    if has_rule(table, parent, rule):
        raise Failure("RELAY_CLEANUP_FAILED")
    chain = "PLR_" + UUID(identifier).hex[:20]
    cmd(["iptables", "-w", "5", "-F", chain])
    cmd(["iptables", "-w", "5", "-X", chain])
    path.unlink()
    return {"removed": True}


def observation(status: str, mode: str, code: str, **values: Any) -> dict[str, Any]:
    return {
        "status": status,
        "mode": mode,
        "code": code,
        "observed_at": datetime.now(UTC).isoformat(),
        **values,
    }


def observe() -> dict[str, Any]:
    users, active, rx, tx = counts()
    previous = read(RUN / "passive.json")
    flowing = (
        previous
        and time.time() - previous["at"] < 7200
        and rx > previous["rx"]
        and tx > previous["tx"]
    )
    write(RUN / "passive.json", json.dumps({"at": time.time(), "rx": rx, "tx": tx}))
    return observation(
        "HEALTHY" if active and flowing else "UNKNOWN",
        "PASSIVE",
        "ACTIVE_TRAFFIC" if active and flowing else "PASSIVE_EVIDENCE_INSUFFICIENT",
        active_connections=active,
        authorized_connections=users,
        handshake_ok=bool(active),
        rx_bytes=rx,
        tx_bytes=tx,
    )


def measure_request(path: str, *, upload: bool = False) -> tuple[bytes, float]:
    config = read(ROOT / "measure.json")
    context = ssl.create_default_context(cafile=str(ROOT / "measure.crt"))
    connection = http.client.HTTPSConnection(config["host"], 8443, timeout=8, context=context)
    started = time.monotonic()
    try:
        connection.request(
            "POST" if upload else "GET",
            path,
            body=b"x" * MAX_BYTES if upload else None,
            headers={"Authorization": "Bearer " + config["token"], "Connection": "close"},
        )
        response = connection.getresponse()
        data = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(data) > MAX_BYTES:
            raise Failure("MEASUREMENT_UNAVAILABLE")
        return data, time.monotonic() - started
    finally:
        connection.close()


def health() -> None:
    # Fixed owned test destination. No user browsing traffic or arbitrary URLs accepted.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("https://api.prettylisavpn.com/health", timeout=8) as response:
        if response.status != 200 or json.loads(response.read(1024)).get("status") != "ok":
            raise Failure("HTTPS_FAILED")


def prepare(identifier: str) -> dict[str, Any]:
    identifier = uid(identifier)
    try:
        health()
        data, _ = measure_request("/ip")
        if json.loads(data)["ip"] != read(ROOT / "state.json")["host"]:
            raise Failure("SOURCE_EGRESS_UNEXPECTED")
    except Exception:
        raise Failure("PROBE_BASELINE_UNAVAILABLE") from None
    path = RUN / ("probe-" + identifier + ".json")
    key = RUN / ("probe-" + identifier + ".key")
    if not path.exists():
        write(path, json.dumps({"expires": time.time() + 240}))
    if not key.exists():
        write(key, cmd(["wg", "genkey"]) + "\n")
    public = cmd(["wg", "pubkey"], data=key.read_text(encoding="utf-8"))
    return {"public_key": public}


def dispose(identifier: str) -> dict[str, Any]:
    identifier = uid(identifier)
    namespace = "plp-" + UUID(identifier).hex[:16]
    interface = "p" + UUID(identifier).hex[:14]
    if any(line.split()[0] == namespace for line in cmd(["ip", "netns", "list"]).splitlines()):
        for pid in cmd(["ip", "netns", "pids", namespace]).splitlines():
            if pid.isdecimal():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(int(pid), 9)
        cmd(["ip", "netns", "delete", namespace])
    cmd(["ip", "link", "delete", interface], check=False)
    resolver = Path("/etc/netns") / namespace
    (resolver / "resolv.conf").unlink(missing_ok=True)
    if resolver.exists():
        resolver.rmdir()
    for extension in ("json", "key"):
        (RUN / ("probe-" + identifier + "." + extension)).unlink(missing_ok=True)
    return {"removed": True}


def probe_child(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    interface = str(payload["interface"])
    flags: dict[str, Any] = {
        "handshake_ok": False,
        "dns_ok": False,
        "https_ok": False,
        "egress_ok": False,
    }
    # Generate encrypted traffic before waiting for a handshake.
    cmd(["ping", "-c", "1", "-W", "1", "1.1.1.1"], check=False)
    for _ in range(10):
        stamps = cmd(["wg", "show", interface, "latest-handshakes"])
        if stamps and any(int(line.split()[1]) > 0 for line in stamps.splitlines()):
            flags["handshake_ok"] = True
            break
        time.sleep(1)
    if not flags["handshake_ok"]:
        return observation("FAILED", "SYNTHETIC", "HANDSHAKE_FAILED", **flags)
    flags["connection_ms"] = (time.monotonic() - started) * 1000
    try:
        # A fresh namespace has no host resolver cache or alternative route.
        answer = cmd(
            ["dig", "+short", "+time=2", "+tries=1", "A", "api.prettylisavpn.com"], timeout=8
        )
        if not answer or not any(re.fullmatch(r"[0-9.]+", line) for line in answer.splitlines()):
            return observation("FAILED", "SYNTHETIC", "DNS_FAILED", **flags)
        flags["dns_ok"] = True
        health()
        flags["https_ok"] = True
        data, _ = measure_request("/ip")
        flags["egress_ok"] = json.loads(data)["ip"] in payload["expected_egress_ips"]
        if not flags["egress_ok"]:
            return observation("FAILED", "SYNTHETIC", "EGRESS_IP_MISMATCH", **flags)
    except Exception:
        return observation("FAILED", "SYNTHETIC", "HTTPS_FAILED", **flags)
    try:
        data, seconds = measure_request("/download")
        if len(data) == MAX_BYTES:
            flags["download_mbps"] = MAX_BYTES * 8 / max(seconds, 0.001) / 1000000
        data, seconds = measure_request("/upload", upload=True)
        if json.loads(data)["received"] == MAX_BYTES:
            flags["upload_mbps"] = MAX_BYTES * 8 / max(seconds, 0.001) / 1000000
    except Exception:
        # Internet proof remains valid; missing throughput is explicitly absent.
        pass
    return observation("HEALTHY", "SYNTHETIC", "FULL_CHECK_PASSED", **flags)


def probe(payload: dict[str, Any]) -> dict[str, Any]:
    identifier = uid(payload["check_id"])
    journal = read(RUN / ("probe-" + identifier + ".json"))
    if not journal or journal["expires"] < time.time() + 120:
        raise Failure("PROBE_LEASE_EXPIRED")
    endpoint, key = public_ip(payload["endpoint"]), str(payload["public_key"])
    address = str(ipaddress.IPv4Interface(payload["address"]))
    port, mtu = int(payload["listen_port"]), int(payload["mtu"])
    if not KEY.fullmatch(key) or not 1024 <= port <= 65535 or not 1280 <= mtu <= 1420:
        raise Failure("PROBE_ARGUMENT_INVALID")
    payload["expected_egress_ips"] = [public_ip(item) for item in payload["expected_egress_ips"]]
    namespace = "plp-" + UUID(identifier).hex[:16]
    interface = "p" + UUID(identifier).hex[:14]
    resolver = Path("/etc/netns") / namespace
    resolver.mkdir(mode=0o700, parents=True, exist_ok=True)
    write(
        resolver / "resolv.conf",
        "nameserver 1.1.1.1\nnameserver 9.9.9.9\noptions timeout:2 attempts:1\n",
    )
    try:
        cmd(["ip", "netns", "add", namespace])
        cmd(["ip", "link", "add", interface, "type", "wireguard"])
        cmd(["ip", "link", "set", interface, "netns", namespace])
        execute = ["ip", "netns", "exec", namespace]
        cmd(execute + ["sysctl", "-w", "net.ipv6.conf.all.disable_ipv6=1"])
        cmd(
            execute
            + [
                "wg",
                "set",
                interface,
                "private-key",
                "/dev/stdin",
                "peer",
                key,
                "endpoint",
                f"{endpoint}:{port}",
                "allowed-ips",
                "0.0.0.0/0",
                "persistent-keepalive",
                "15",
            ],
            # Keep the key in a pipe: Ubuntu's wg AppArmor profile deliberately
            # cannot open our private journal directory. Never put it in argv.
            data=(RUN / ("probe-" + identifier + ".key")).read_text(encoding="utf-8"),
        )
        cmd(["ip", "-n", namespace, "addr", "add", address, "dev", interface])
        cmd(["ip", "-n", namespace, "link", "set", "lo", "up"])
        cmd(["ip", "-n", namespace, "link", "set", interface, "mtu", str(mtu), "up"])
        cmd(["ip", "-n", namespace, "route", "add", "default", "dev", interface])
        output = cmd(
            execute + ["python3", HELPER, "probe-child"],
            data=json.dumps(
                {"interface": interface, "expected_egress_ips": payload["expected_egress_ips"]}
            ),
            timeout=100,
        )
        return cast(dict[str, Any], json.loads(output))
    finally:
        dispose(identifier)


def cleanup() -> dict[str, Any]:
    for path in (ROOT / "relays").glob("*.json"):
        if read(path).get("expires", 0) <= time.time():
            revoke_relay(path.stem)
    for path in (ROOT / "clients").glob("*.json"):
        if read(path).get("expires", 0) <= time.time():
            revoke(path.stem, "client")
    for path in RUN.glob("lease-*.json"):
        if read(path).get("expires", 0) <= time.time():
            revoke(path.stem.removeprefix("lease-"))
    for path in RUN.glob("probe-*.json"):
        if read(path).get("expires", 0) <= time.time():
            dispose(path.stem.removeprefix("probe-"))
    return {"cleaned": True}


class MeasurementHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token = ""
    slots = threading.BoundedSemaphore(2)

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def handle_one_request(self) -> None:
        self.connection.settimeout(10)
        super().handle_one_request()

    def do_GET(self) -> None:
        self.respond(False)

    def do_POST(self) -> None:
        self.respond(True)

    def respond(self, upload: bool) -> None:
        self.close_connection = True
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.token):
            self.send_error(403)
            return
        if not self.slots.acquire(blocking=False):
            self.send_error(429)
            return
        try:
            if self.path == "/ip" and not upload:
                body = json.dumps({"ip": self.client_address[0]}).encode()
            elif self.path == "/download" and not upload:
                body = b"x" * MAX_BYTES
            elif (
                self.path == "/upload"
                and upload
                and self.headers.get("Content-Length") == str(MAX_BYTES)
            ):
                received = 0
                deadline = time.monotonic() + 10
                while received < MAX_BYTES and time.monotonic() < deadline:
                    chunk = self.rfile.read(min(65536, MAX_BYTES - received))
                    if not chunk:
                        break
                    received += len(chunk)
                body = json.dumps({"received": received}).encode()
            else:
                self.send_error(400)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        finally:
            self.slots.release()


class MeasurementServer(ThreadingHTTPServer):
    daemon_threads = True
    context: ssl.SSLContext

    def get_request(self) -> tuple[socket.socket, Any]:
        connection, address = self.socket.accept()
        connection.settimeout(3)
        try:
            return self.context.wrap_socket(connection, server_side=True), address
        except Exception:
            connection.close()
            raise


def measure() -> None:
    MeasurementHandler.token = read(ROOT / "measure.json")["token"]
    server = MeasurementServer(("0.0.0.0", 8443), MeasurementHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(ROOT / "measure.crt"), str(ROOT / "measure.key"))
    server.context = context
    server.serve_forever()


def dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload["action"]
    if action == "inspect":
        return inspect()
    if action == "configure":
        return configure(payload)
    if action == "rollback":
        return rollback(payload["operation_id"])
    if action == "grant":
        return grant(payload["access"])
    if action == "revoke":
        return revoke(payload["access_id"], payload.get("purpose", "monitor"))
    if action == "grant-relay":
        return grant_relay(payload["access"])
    if action == "revoke-relay":
        return revoke_relay(payload["access_id"])
    if action == "observe":
        return observe()
    if action == "prepare":
        return prepare(payload["check_id"])
    if action == "probe":
        return probe(payload)
    if action == "dispose":
        return dispose(payload["check_id"])
    if action == "cleanup":
        return cleanup()
    raise Failure("ACTION_UNSUPPORTED")


def main() -> None:
    try:
        argument = sys.argv[1] if len(sys.argv) > 1 else ""
        if argument == "measure":
            measure()
            return
        if argument == "probe-child":
            print(json.dumps(probe_child(json.loads(sys.stdin.read(8192)))))
            return
        if os.getuid() != 0:
            raise Failure("ROOT_REQUIRED")
        RUN.mkdir(mode=0o700, exist_ok=True)
        if argument in ("firewall-up", "firewall-down"):
            # Called by wg-quick inside the configuration lock.
            firewall(argument == "firewall-up")
            return
        payload = (
            {"action": "cleanup"} if argument == "cleanup" else json.loads(sys.stdin.read(16384))
        )
        import fcntl

        if payload["action"] == "probe":
            # Only this check's namespace is touched. Holding the global mutex
            # during network waits would delay customer renewals and revocations.
            # The DB fences CHECK/CONFIGURE; the expiring probe journal and its
            # timer independently bound orphaned namespaces.
            result = dispatch(payload)
        else:
            with (RUN / "lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = dispatch(payload)
        print(json.dumps(result))
    except Exception as exc:
        code = str(exc) if isinstance(exc, Failure) else "NODE_OPERATION_FAILED"
        print(json.dumps({"error": code}))
        if len(sys.argv) > 1:
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
