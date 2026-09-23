"""Connect one standalone profile, verify it and clean up in a disposable container.

Never use --network=host. No fallback or cross-profile retry. Only JSON evidence
is printed; runtime output stays private and is deleted with the container.
"""

import argparse
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from probe import classify, probe, run
from profiles import load


def connect_and_check(manifest, profile, endpoints):
    if not Path("/.dockerenv").is_file():
        raise ValueError("isolated Docker runner required")
    processes = []
    log_path = Path("/run/profile-adapter.log")
    routes = []
    wireguard = profile["protocol"] == "WIREGUARD"
    config_root = Path("/run/secrets") / profile["id"]
    start = datetime.now(UTC).timestamp()
    handshake = False
    with log_path.open("w+") as log:
        try:
            default = json.loads(run("ip", "-j", "-4", "route", "show", "default"))[0]
            endpoint_route = manifest["public_ipv4"] + "/32"
            run(
                "ip",
                "route",
                "replace",
                endpoint_route,
                "via",
                default["gateway"],
                "dev",
                default["dev"],
            )
            routes.append(endpoint_route)

            def launch(*args):
                processes.append(subprocess.Popen(args, stdout=log, stderr=log))

            if wireguard:
                if profile["obfuscation_mode"] == "SIMPLE_PACKET_WRAPPER_V1":
                    launch(
                        "/opt/probe/venv/bin/python",
                        "/opt/probe/wrapper_client.py",
                        manifest["public_ipv4"],
                        str(profile["port"]),
                    )
                    for _ in range(100):
                        if "127.0.0.1:51821" in run(
                            "ss", "-H", "-lun", "sport = :51821"
                        ):
                            break
                        time.sleep(0.05)
                subprocess.run(
                    ["wg-quick", "up", str(config_root / "wg0.conf")],
                    check=True,
                    stdout=log,
                    stderr=log,
                )
            elif profile["protocol"] == "OPENVPN":
                if profile["obfuscation_mode"] == "TLS_TRANSPORT":
                    launch("stunnel4", str(config_root / "stunnel.conf"))
                launch(
                    "openvpn",
                    "--config",
                    str(config_root / "client.ovpn"),
                    "--management",
                    "127.0.0.1",
                    "7505",
                )
            else:
                launch(
                    "/usr/local/bin/prettylisa-masque", str(config_root / "client.json")
                )
            for _ in range(30):
                try:
                    link = json.loads(
                        run("ip", "-j", "address", "show", "dev", profile["interface"])
                    )[0]
                    if any(
                        addr.get("family") == "inet"
                        for addr in link.get("addr_info", [])
                    ):
                        break
                except (subprocess.SubprocessError, ValueError, IndexError):
                    pass
                if any(p.poll() is not None for p in processes):
                    break
                time.sleep(1)
            for prefix in ["0.0.0.0/1", "128.0.0.0/1"]:
                run("ip", "route", "replace", prefix, "dev", profile["interface"])
                routes.append(prefix)
            result = probe(manifest, profile, endpoints)
            if wireguard:
                handshake = any(
                    int(row.split()[1]) >= start - 5
                    for row in run(
                        "wg", "show", profile["interface"], "latest-handshakes"
                    ).splitlines()
                )
            elif profile["protocol"] == "OPENVPN":
                with socket.create_connection(
                    ("127.0.0.1", 7505), timeout=5
                ) as management:
                    # Sending quit in the same write can close the management
                    # socket before OpenVPN flushes its queued state response.
                    management.sendall(b"state\n")
                    chunks = []
                    while chunk := management.recv(4096):
                        chunks.append(chunk)
                        if (
                            b"END\r\n" in b"".join(chunks)
                            or sum(map(len, chunks)) > 16384
                        ):
                            break
                handshake = b",CONNECTED,SUCCESS," in b"".join(chunks)
            else:
                log.flush()
                handshake = any(
                    '"msg":"tunnel_established"' in line
                    for line in log_path.read_text().splitlines()
                )
            return classify(result, handshake)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return classify(probe(manifest, profile, []), False)
        finally:
            for prefix in reversed(routes):
                subprocess.run(
                    ["ip", "route", "del", prefix],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if wireguard:
                subprocess.run(
                    ["wg-quick", "down", str(config_root / "wg0.conf")],
                    stdout=log,
                    stderr=log,
                    check=False,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profile")
    args = parser.parse_args()
    os.umask(0o077)
    manifest = load("/run/secrets/node.json")
    selected = next(
        p for p in manifest["profiles"] if p["id"] == args.profile and p["enabled"]
    )
    endpoints = json.loads(Path("/run/secrets/health-endpoints.json").read_text())
    result = connect_and_check(manifest, selected, endpoints)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "E2E_VERIFIED" else 1)
