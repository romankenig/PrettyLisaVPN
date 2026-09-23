"""Bootstrap an operator-owned test PKI on a node; never print keys or credentials.

Use only as root on the node. Existing keys/certificates are preserved. The
external test client bundle is root-only and must be transferred securely to the
trusted runner, then removed when testing is finished. Production enrollment and
revocation belong to a separate credential provisioning service.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import ssl
import subprocess
from pathlib import Path

from profiles import load


def command(*args):
    subprocess.run(
        args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def bootstrap(m):
    os.umask(0o077)
    for p in m["profiles"]:
        if not p["enabled"] or p["protocol"] == "WIREGUARD":
            continue
        root = Path("/etc/prettylisa-profiles") / p["id"]
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        ca = root / "authority"
        ca.mkdir(mode=0o700, exist_ok=True)
        if not (root / "ca.crt").exists():
            command(
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-keyout",
                str(ca / "ca.key"),
                "-out",
                str(root / "ca.crt"),
                "-days",
                "365",
                "-subj",
                "/CN=PrettyLisa-profile-CA",
            )
        for name, identity, eku in (
            ("server", p["server_name"], "serverAuth"),
            ("external-test", "PrettyLisa-external-test", "clientAuth"),
        ):
            if (root / f"{name}.crt").exists():
                description = subprocess.check_output(
                    [
                        "openssl",
                        "x509",
                        "-in",
                        str(root / f"{name}.crt"),
                        "-noout",
                        "-text",
                    ]
                ).decode()
                if p["protocol"] != "OPENVPN" or "X509v3 Key Usage" in description:
                    continue
            key_args = (
                ["-key", str(root / f"{name}.key")]
                if (root / f"{name}.key").exists()
                else [
                    "-newkey",
                    "rsa:3072",
                    "-nodes",
                    "-keyout",
                    str(root / f"{name}.key"),
                ]
            )
            command(
                "openssl",
                "req",
                "-new",
                *key_args,
                "-out",
                str(root / f"{name}.csr"),
                "-subj",
                f"/CN={identity}",
            )
            ext = root / f"{name}.ext"
            ext.write_text(
                "basicConstraints=critical,CA:false\n"
                + (
                    "keyUsage=critical,digitalSignature,keyEncipherment\n"
                    if name == "server"
                    else "keyUsage=critical,digitalSignature\n"
                )
                + f"extendedKeyUsage={eku}\n"
                + (f"subjectAltName=DNS:{identity}\n" if name == "server" else "")
            )
            command(
                "openssl",
                "x509",
                "-req",
                "-in",
                str(root / f"{name}.csr"),
                "-CA",
                str(root / "ca.crt"),
                "-CAkey",
                str(ca / "ca.key"),
                "-CAcreateserial",
                "-out",
                str(root / f"{name}.crt"),
                "-days",
                "30",
                "-extfile",
                str(ext),
            )
        if p["protocol"] == "MASQUE":
            registry = root / "clients.json"
            if not registry.exists():
                cert = ssl.PEM_cert_to_DER_cert(
                    (root / "external-test.crt").read_text()
                )
                client_ip = str(ipaddress.IPv4Address(p["gateway"]) + 1)
                registry.write_text(
                    json.dumps({hashlib.sha256(cert).hexdigest(): client_ip})
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args()
    try:
        bootstrap(load(args.manifest))
    except (OSError, ValueError, subprocess.SubprocessError):
        print('{"event":"pki_bootstrap_failed"}')
        raise SystemExit(1) from None
    print('{"event":"pki_bootstrap_complete"}')
