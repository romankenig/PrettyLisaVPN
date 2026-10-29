"""Transport allowlist and independent, stable, redacted authorization material."""

from uuid import uuid4

import pytest
from pydantic import SecretStr

from prettylisavpn.client_vpn.methods import (
    MANAGED_METHODS,
    METHODS,
    base_method,
    lease_credential,
    profile,
)
from prettylisavpn.fleet.domain import FleetError


def test_every_encrypted_method_has_a_relay_and_no_deferred_method_is_admitted():
    for method in ("wireguard", *MANAGED_METHODS):
        assert method in METHODS and method + "_relay" in METHODS
        assert base_method(method) == base_method(method + "_relay") == method
    for method in ("openvpn", "openconnect", "trojan", "ssh", "http", "socks", "vless_relay_relay"):
        with pytest.raises(FleetError, match="VPN_METHOD_UNSUPPORTED"):
            base_method(method)
    assert MANAGED_METHODS["shadowsocks2022"].network == "both"
    assert MANAGED_METHODS["hysteria2"].network == "udp"
    assert MANAGED_METHODS["hysteria"].engine == "HYSTERIA1_TLS"
    assert MANAGED_METHODS["hysteria"].network == "udp"
    assert MANAGED_METHODS["sstp"].engine == "SSTP"
    assert MANAGED_METHODS["sstp"].network == "tcp"
    assert MANAGED_METHODS["softether"].engine == "SOFTETHER"
    assert MANAGED_METHODS["softether"].network == "tcp"
    assert MANAGED_METHODS["vless_reality"].network == "tcp"


def test_credentials_are_stable_scoped_separate_and_redacted():
    key, lease, node = SecretStr("test-only-key-" + "a" * 32), uuid4(), uuid4()
    secret = lease_credential(key, lease, node)
    assert secret == lease_credential(key, lease, node)
    assert secret != lease_credential(key, uuid4(), node)
    assert secret != lease_credential(key, lease, uuid4())
    assert secret != lease_credential(SecretStr("b" * 48), lease, node)
    assert secret.get_secret_value() not in repr(secret)
    for unavailable in (None, SecretStr("short")):
        with pytest.raises(FleetError, match="VPN_ENGINE_UNAVAILABLE"):
            lease_credential(unavailable, lease, node)


def test_amnezia_profile_has_only_its_keys_and_tunnel_address():
    import base64

    key, lease, node = SecretStr("test-only-key-" + "a" * 32), uuid4(), uuid4()
    result = profile(
        method="amneziawg_relay",
        lease_id=lease,
        node_id=node,
        key=key,
        host="9.9.9.9",
        port=25000,
        country="DE",
        public_key="AQ" + "A" * 41,
        configuration={},
    )
    assert result["method"] == "AMNEZIA" and result["address"] == "172.30.253.2/32"
    assert len(base64.b64decode(str(result["secret"]))) == 32
    assert len(base64.b64decode(str(result["public_key"]))) == 32
    assert "server_name" not in result and "certificate_pin" not in result
