"""Closed plan v1, matching engines/managed/node/catalog.go port offsets."""

import base64
import hashlib
from typing import Any

PLAN_PORTS = 20


def derived(secret: str, purpose: str) -> str:
    return base64.b64encode(
        hashlib.sha256(f"PrettyLisaVPN/plan/v1/{purpose}\0{secret}".encode()).digest()
    ).decode()


def profiles(node: dict[str, Any], port: int, secret: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = [
        dict(
            method="VLESS_REALITY",
            port=port,
            secret=secret,
            public_key=node["public_key"],
            server_name=node["server_name"],
            short_id=node["short_id"],
        )
    ]
    for method in ("VLESS_TLS", "VMESS_TLS", "TROJAN_TLS"):
        for transport in ("", "ws", "grpc", "httpupgrade", "xhttp"):
            profile = dict(
                method=method,
                port=port + len(result),
                secret=secret,
                server_name=node["server_name"],
                certificate_pin=node["certificate_pin"],
            )
            if transport:
                profile.update(
                    transport=transport, path="plvpn" if transport == "grpc" else "/plvpn"
                )
            result.append(profile)
    result.append(dict(method="SHADOWSOCKS", port=port + len(result), secret=secret))
    result.append(
        dict(
            method="SHADOWSOCKS_2022",
            port=port + len(result),
            secret=derived(secret, "ss-server") + ":" + derived(secret, "ss-user"),
        )
    )
    for method in ("HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"):
        profile = dict(
            method=method,
            port=port + len(result),
            secret=secret,
            server_name=node["server_name"],
            certificate_pin=node["certificate_pin"],
        )
        if method == "HYSTERIA2_SALAMANDER":
            profile["obfs_secret"] = derived(secret, "salamander")
        result.append(profile)
    return result
