"""Explicit encrypted transport capabilities and private per-lease credentials."""

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import SecretStr

from prettylisavpn.fleet.domain import FleetError


@dataclass(frozen=True)
class ManagedMethod:
    engine: str
    network: Literal["tcp", "udp", "both"]


MANAGED_METHODS = {
    "amneziawg": ManagedMethod("AMNEZIA", "udp"),
    "vless_reality": ManagedMethod("VLESS_REALITY", "tcp"),
    "vless": ManagedMethod("VLESS_TLS", "tcp"),
    "vmess": ManagedMethod("VMESS_TLS", "tcp"),
    "shadowsocks2022": ManagedMethod("SHADOWSOCKS_2022", "both"),
    "hysteria": ManagedMethod("HYSTERIA1_TLS", "udp"),
    "hysteria2": ManagedMethod("HYSTERIA2_TLS", "udp"),
    "hysteria2_salamander": ManagedMethod("HYSTERIA2_SALAMANDER", "udp"),
}
METHODS = frozenset(
    variant for base in ("wireguard", *MANAGED_METHODS) for variant in (base, base + "_relay")
)


def base_method(method: str) -> str:
    if method not in METHODS:
        raise FleetError("VPN_METHOD_UNSUPPORTED", 422)
    return method.removesuffix("_relay")


def lease_credential(key: SecretStr | None, lease_id: UUID, node_id: UUID) -> SecretStr:
    """Stable retries without plaintext credentials in PostgreSQL or logs.

    This dedicated key must remain available until all managed leases are closed.
    It is never reused for OTP, JWT, monitoring or dashboard authentication.
    """
    if key is None or len(key.get_secret_value()) < 32:
        raise FleetError("VPN_ENGINE_UNAVAILABLE", 503)
    digest = hmac.digest(
        key.get_secret_value().encode(),
        b"PrettyLisaVPN/managed-lease/v1\x00" + lease_id.bytes + node_id.bytes,
        hashlib.sha256,
    )
    return SecretStr(str(UUID(bytes=digest[:16], version=4)))


def derived(secret: str, purpose: str) -> str:
    # Same versioned domain separation as the managed engine's SS2022/SALAMANDER adapter.
    digest = hashlib.sha256(
        ("PrettyLisaVPN/plan/v1/" + purpose + "\x00" + secret).encode()
    ).digest()
    return base64.b64encode(digest).decode()


def profile(
    *,
    method: str,
    lease_id: UUID,
    node_id: UUID,
    key: SecretStr | None,
    host: str,
    port: int,
    country: str,
    public_key: str | None,
    configuration: dict[str, object],
) -> dict[str, object]:
    selected = MANAGED_METHODS[base_method(method)]
    secret = lease_credential(key, lease_id, node_id).get_secret_value()
    result: dict[str, object] = {
        "version": 1,
        "session": str(lease_id),
        "country": country,
        "method": selected.engine,
        "server": host,
        "port": port,
        "secret": secret,
    }
    if selected.engine == "AMNEZIA":
        result.update(
            secret=derived(secret, "amnezia-key"),
            public_key=base64.b64encode(base64.urlsafe_b64decode(str(public_key) + "=")).decode(),
            address="172.30.253.2/32",
        )
    elif selected.engine == "SHADOWSOCKS_2022":
        result["secret"] = derived(secret, "ss-server") + ":" + derived(secret, "ss-user")
    else:
        result["server_name"] = configuration["server_name"]
        if selected.engine == "VLESS_REALITY":
            result.update(public_key=public_key, short_id=configuration["short_id"])
        else:
            result["certificate_pin"] = configuration["certificate_pin"]
        if selected.engine == "HYSTERIA2_SALAMANDER":
            result["obfs_secret"] = derived(secret, "salamander")
    return result
