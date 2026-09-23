"""Create root-only standalone client bundles on a node. No secret output.

Creates one temporary WireGuard peer after checking address collisions. Remove
this peer and test client certificates after external verification. The private
server/CA keys are never part of the client bundle.
"""

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
from pathlib import Path

from profiles import load


def output(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()


def prepare(m):
    os.umask(0o077)
    bundle = Path("/etc/prettylisa-profiles/test-client")
    bundle.mkdir(mode=0o700, exist_ok=True)
    (bundle / "node.json").write_text(json.dumps(m))
    for p in m["profiles"]:
        if not p["enabled"]:
            continue
        destination = bundle / p["id"]
        destination.mkdir(mode=0o700, exist_ok=True)
        if p["protocol"] == "WIREGUARD":
            key = bundle / "wireguard.key"
            if not key.exists():
                key.write_text(output("wg", "genkey") + "\n")
            public = (
                subprocess.check_output(["wg", "pubkey"], input=key.read_bytes())
                .decode()
                .strip()
            )
            address = ipaddress.IPv4Network(p["subnet"]).broadcast_address - 1
            for line in output(
                "wg", "show", p["interface"], "allowed-ips"
            ).splitlines():
                fields = line.split()
                if fields[0] != public:
                    for prefix in fields[1:]:
                        if prefix != "(none)" and address in ipaddress.ip_network(
                            prefix
                        ):
                            raise ValueError("test address already allocated")
            subprocess.run(
                [
                    "wg",
                    "set",
                    p["interface"],
                    "peer",
                    public,
                    "allowed-ips",
                    f"{address}/32",
                ],
                check=True,
            )
            server_key = output("wg", "show", p["interface"], "public-key")
            endpoint = (
                f"{m['public_ipv4']}:{p['port']}"
                if p["obfuscation_mode"] == "NONE"
                else "127.0.0.1:51821"
            )
            (destination / "wg0.conf").write_text(f"""[Interface]
PrivateKey = {key.read_text().strip()}
Address = {address}/32
MTU = 1280
Table = off
[Peer]
PublicKey = {server_key}
Endpoint = {endpoint}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 15
""")
            (bundle / "wireguard-public.key").write_text(public + "\n")
        else:
            source = Path("/etc/prettylisa-profiles") / p["id"]
            for name in ["ca.crt", "external-test.crt", "external-test.key"]:
                shutil.copyfile(source / name, destination / name)
            root = f"/run/secrets/{p['id']}"
            if p["protocol"] == "MASQUE":
                (destination / "client.json").write_text(
                    json.dumps(
                        {
                            "mode": "client",
                            "endpoint": f"{m['public_ipv4']}:443",
                            "server_name": p["server_name"],
                            "interface": p["interface"],
                            "address": f"{ipaddress.IPv4Address(p['gateway']) + 1}/24",
                            "certificate": root + "/external-test.crt",
                            "private_key": root + "/external-test.key",
                            "ca": root + "/ca.crt",
                            "clients": {},
                        }
                    )
                )
            else:
                wrapped = p["obfuscation_mode"] == "TLS_TRANSPORT"
                (destination / "client.ovpn").write_text(f"""client
proto tcp-client
remote {"127.0.0.1 1443" if wrapped else m["public_ipv4"] + " 443"}
nobind
dev {p["interface"]}
dev-type tun
tun-mtu 1280
route-nopull
ca {root}/ca.crt
cert {root}/external-test.crt
key {root}/external-test.key
remote-cert-tls server
verify-x509-name {p["server_name"]} name
tls-version-min 1.3
data-ciphers AES-256-GCM
allow-compression no
auth-nocache
verb 0
""")
                if wrapped:
                    (destination / "stunnel.conf").write_text(f"""foreground = yes
client = yes
syslog = no
debug = emerg
sslVersionMin = TLSv1.3
verifyChain = yes
checkHost = {p["server_name"]}
CAfile = {root}/ca.crt
cert = {root}/external-test.crt
key = {root}/external-test.key
[carrier]
accept = 127.0.0.1:1443
connect = {m["public_ipv4"]}:443
sni = {p["server_name"]}
""")
    (bundle / "health-endpoints.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://api.ipify.org",
                    "expected_status": 200,
                    "egress_response": "plain_ip",
                },
                {
                    "url": "https://icanhazip.com",
                    "expected_status": 200,
                    "egress_response": "plain_ip",
                },
            ]
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    try:
        prepare(load(args.manifest))
    except (OSError, ValueError, subprocess.SubprocessError):
        print('{"event":"client_bundle_failed"}')
        raise SystemExit(1) from None
    print('{"event":"client_bundle_prepared"}')
