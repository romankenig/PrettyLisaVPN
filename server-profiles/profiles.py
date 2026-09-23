"""Secret-free deployment manifest and evidence contract. No inferred capabilities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

MATRIX = {
    ("WIREGUARD", "UDP", "NONE"): "WIREGUARD",
    ("WIREGUARD", "UDP", "SIMPLE_PACKET_WRAPPER_V1"): "WIREGUARD",
    ("OPENVPN", "TCP", "NONE"): "TLS_1_3_AES_256_GCM",
    ("OPENVPN", "TCP", "TLS_TRANSPORT"): "TLS_1_3_AES_256_GCM",
    ("MASQUE", "UDP", "NONE"): "TLS_1_3_QUIC",
}
STATES = {"UNTESTED", "UNIT_TESTED", "SERVER_READY", "E2E_VERIFIED", "E2E_FAILED"}


def load(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text())
    validate(manifest)
    return manifest


def validate(manifest: dict) -> None:
    if set(manifest) != {
        "node_id",
        "public_ipv4",
        "egress_interface",
        "ssh_port",
        "profiles",
    }:
        raise ValueError("invalid manifest fields")
    from uuid import UUID

    UUID(manifest["node_id"])
    IPv4Address(manifest["public_ipv4"])
    interface(manifest["egress_interface"])
    port(manifest["ssh_port"])
    sockets: set[tuple[str, str, int]] = set()
    ids: set[str] = set()
    networks: list[tuple[IPv4Network, dict]] = []
    for profile in manifest["profiles"]:
        if set(profile) != {
            "id",
            "protocol",
            "transport",
            "port",
            "encryption_mode",
            "obfuscation_mode",
            "free_available",
            "enabled",
            "interface",
            "subnet",
            "gateway",
            "mtu",
            "dns",
            "upstream_port",
            "server_name",
        }:
            raise ValueError("invalid profile fields")
        interface(profile["id"])
        interface(profile["interface"])
        if (
            profile["id"] == "routing"
            or profile["interface"] == manifest["egress_interface"]
        ):
            raise ValueError("reserved identity or physical interface used as tunnel")
        if profile["id"] in ids:
            raise ValueError("duplicate profile identity")
        ids.add(profile["id"])
        key = (profile["protocol"], profile["transport"], profile["obfuscation_mode"])
        if MATRIX.get(key) != profile["encryption_mode"]:
            raise ValueError("unsupported protocol/transport/obfuscation")
        port(profile["port"])
        port(profile["upstream_port"])
        if profile["protocol"] != "WIREGUARD" and profile["port"] != 443:
            raise ValueError("TLS and QUIC profiles require port 443")
        if (
            type(profile["enabled"]) is not bool
            or type(profile["free_available"]) is not bool
        ):
            raise ValueError("enabled/free_available must be booleans")
        network = IPv4Network(profile["subnet"])
        gateway = IPv4Address(profile["gateway"])
        if (
            not network.is_private
            or gateway not in network
            or gateway in (network.network_address, network.broadcast_address)
        ):
            raise ValueError("invalid VPN subnet/gateway")
        if profile["mtu"] != 1280 or not profile["dns"]:
            raise ValueError("MTU must be 1280 and DNS must be configured")
        for dns in profile["dns"]:
            IPv4Address(dns)
        import re

        if not re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", profile["server_name"]):
            raise ValueError("invalid server identity")
        if (
            profile["obfuscation_mode"] != "NONE"
            and profile["port"] == profile["upstream_port"]
        ):
            raise ValueError("carrier listener must differ from private upstream")
        if profile["enabled"]:
            socket = (manifest["public_ipv4"], profile["transport"], profile["port"])
            if socket in sockets:
                raise ValueError("public socket collision")
            sockets.add(socket)
            # Shared WireGuard transport variants intentionally share the same wg0 subnet.
            for previous, owner in networks:
                shared = (
                    profile["protocol"] == owner["protocol"] == "WIREGUARD"
                    and profile["interface"] == owner["interface"]
                    and network == previous
                    and profile["gateway"] == owner["gateway"]
                    and profile["upstream_port"] == owner["upstream_port"]
                )
                if (
                    network.overlaps(previous)
                    or profile["interface"] == owner["interface"]
                ) and not shared:
                    raise ValueError("overlapping tunnel networks")
            networks.append((network, profile))


def port(value: object) -> None:
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError("invalid port")


def interface(value: str) -> None:
    import re

    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,14}", value):
        raise ValueError("invalid interface/identity")


def revision(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verified(manifest: dict, profile: dict, report: dict, now: datetime) -> bool:
    """Only trusted operator-imported reports; a service health check cannot mint evidence."""
    try:
        checked = datetime.fromisoformat(report["checked_at"])
        age = now - checked
        return (
            profile["enabled"]
            and report["node_id"] == manifest["node_id"]
            and report["profile"] == profile["id"]
            and report["configuration_sha256"] == revision(manifest)
            and report["status"] == "E2E_VERIFIED"
            and all(
                report[name] is True
                for name in (
                    "transport_established",
                    "tunnel",
                    "dns",
                    "https",
                    "internet",
                    "route_verified",
                )
            )
            and IPv4Address(report["egress_ip"]) == IPv4Address(manifest["public_ipv4"])
            and timedelta(0) <= age <= timedelta(hours=24)
        )
    except (KeyError, TypeError, ValueError):
        return False
