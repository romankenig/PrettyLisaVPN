"""External Linux E2E probe, run inside an isolated VPN client network namespace.

Connect the standalone client first. This probe never changes routes and never
uses ICMP. Endpoint definitions and command output are not copied to reports.
"""

import argparse
import ipaddress
import json
import secrets
import socket
import struct
import subprocess
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

from profiles import load, revision


def run(*args: str) -> str:
    return subprocess.check_output(args, timeout=20, stderr=subprocess.DEVNULL).decode()


def resolve(host: str, dns: str, interface: str) -> str:
    query_id = secrets.randbelow(65536)
    labels = host.encode("idna").split(b".")
    if any(not label or len(label) > 63 for label in labels):
        raise ValueError("DNS_FAILED")
    question = b"".join(bytes([len(label)]) + label for label in labels) + b"\0\0\1\0\1"
    request = struct.pack("!6H", query_id, 0x100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\0"
        )
        sock.settimeout(8)
        sock.connect((dns, 53))
        sock.send(request)
        response = sock.recv(4096)
    ident, flags, questions, answers, _, _ = struct.unpack("!6H", response[:12])
    if ident != query_id or flags & 0x820F != 0x8000 or questions != 1:
        raise ValueError("DNS_FAILED")

    def skip_name(offset: int) -> int:
        for _ in range(128):
            size = response[offset]
            if size & 0xC0 == 0xC0:
                return offset + 2
            if size > 63:
                raise ValueError("DNS_FAILED")
            offset += size + 1
            if size == 0:
                return offset
        raise ValueError("DNS_FAILED")

    offset = skip_name(12) + 4
    for _ in range(answers):
        offset = skip_name(offset)
        kind, cls, _, size = struct.unpack("!HHIH", response[offset : offset + 10])
        offset += 10
        if kind == 1 and cls == 1 and size == 4:
            return str(ipaddress.IPv4Address(response[offset : offset + size]))
        offset += size
    raise ValueError("DNS_FAILED")


def route(address: str, interface: str) -> bool:
    paths = json.loads(run("ip", "-j", "-4", "route", "get", address))
    return len(paths) == 1 and paths[0].get("dev") == interface


def probe(m: dict, p: dict, endpoints: list[dict]) -> dict:
    result = {
        "node_id": m["node_id"],
        "profile": p["id"],
        "transport": p["transport"],
        "configuration_sha256": revision(m),
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "E2E_FAILED",
        "transport_established": False,
        "tunnel": False,
        "dns": False,
        "https": False,
        "internet": False,
        "route_verified": False,
        "egress_ip": None,
        "latency_ms": None,
        "failure_code": "TUNNEL_ESTABLISHED_NO_TRAFFIC",
    }
    start = time.monotonic()
    interface = p["interface"]
    try:
        links = json.loads(run("ip", "-j", "link", "show", "dev", interface))
        result["tunnel"] = bool(links and "UP" in links[0].get("flags", []))
        # Caller must supply the standalone adapter's authenticated handshake evidence.
        # Existence of a TUN device alone is never sufficient for success.
        if not result["tunnel"]:
            return result
        for endpoint in endpoints:
            try:
                url = urlsplit(endpoint["url"])
                if (
                    url.scheme != "https"
                    or not url.hostname
                    or url.username
                    or url.password
                ):
                    continue
                dns = p["dns"][0]
                if not route(dns, interface):
                    result["failure_code"] = "ROUTE_LEAK_DETECTED"
                    return result
                result["failure_code"] = "DNS_FAILED"
                address = resolve(url.hostname, dns, interface)
                result["dns"] = True
                if not route(address, interface):
                    result["failure_code"] = "ROUTE_LEAK_DETECTED"
                    return result
                result["failure_code"] = "HTTPS_CHECK_FAILED"
                response = run(
                    "curl",
                    "--silent",
                    "--fail",
                    "--noproxy",
                    "*",
                    "--max-time",
                    "12",
                    "--max-filesize",
                    "4096",
                    "--proto",
                    "=https",
                    "--tlsv1.3",
                    "--interface",
                    interface,
                    "--resolve",
                    f"{url.hostname}:{url.port or 443}:{address}",
                    "--write-out",
                    "\n%{http_code}",
                    endpoint["url"],
                )
                body, code = response.rsplit("\n", 1)
                if int(code) != endpoint.get("expected_status", 200):
                    continue
                if (
                    "expected_body" in endpoint
                    and body.strip() != endpoint["expected_body"]
                ):
                    continue
                if endpoint.get("egress_response") != "plain_ip":
                    continue  # This runner requires an independently checked egress identity.
                egress = str(ipaddress.IPv4Address(body.strip()))
                result["https"] = True
                result["egress_ip"] = egress
                if egress != m["public_ipv4"]:
                    result["failure_code"] = "EGRESS_MISMATCH"
                    return result
                if not route(address, interface) or not route(dns, interface):
                    result["failure_code"] = "ROUTE_LEAK_DETECTED"
                    return result
                result.update(internet=True, route_verified=True, failure_code=None)
                break
            except (
                OSError,
                ValueError,
                IndexError,
                struct.error,
                subprocess.SubprocessError,
            ):
                continue
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    finally:
        result["latency_ms"] = round((time.monotonic() - start) * 1000, 2)
    return result


def classify(result: dict, handshake: bool) -> dict:
    result["transport_established"] = handshake
    if handshake and all(
        result[key] is True
        for key in ("tunnel", "dns", "https", "internet", "route_verified")
    ):
        result["status"] = "E2E_VERIFIED"
    else:
        result["status"] = "E2E_FAILED"
        if not handshake:
            result["failure_code"] = "HANDSHAKE_FAILED"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("profile")
    parser.add_argument("endpoints")
    parser.add_argument(
        "--handshake-confirmed",
        action="store_true",
        help="Set only after independently checking the standalone client handshake",
    )
    args = parser.parse_args()
    manifest = load(args.manifest)
    profile = next(p for p in manifest["profiles"] if p["id"] == args.profile)
    with open(args.endpoints) as stream:
        endpoints = json.load(stream)
    print(
        json.dumps(
            classify(probe(manifest, profile, endpoints), args.handshake_confirmed)
        )
    )
