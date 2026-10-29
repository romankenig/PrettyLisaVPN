"""Disposable official-peer test, without published ports or host networking."""

import hashlib
import json
import os
import pathlib
import secrets
import ssl
import subprocess
import time

os.umask(0o077)
subprocess.run(["vpnserver", "start"], check=True, stdout=subprocess.DEVNULL)
until = time.monotonic() + 15
while True:
    probe = subprocess.run(
        ["vpncmd", "localhost", "/SERVER", "/CMD", "ServerInfoGet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3,
        check=False,
    )
    if probe.returncode == 0:
        break
    if time.monotonic() >= until:
        raise RuntimeError("reference server unavailable")
    time.sleep(0.1)

secret = secrets.token_hex(24)
subprocess.run(
    [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "/run/pl-reference.key",
        "-out",
        "/run/pl-reference.crt",
        "-days",
        "1",
        "-subj",
        "/CN=vpn.example.com",
        "-addext",
        "subjectAltName=DNS:vpn.example.com",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def command(parts: list[str], hub: bool = True) -> None:
    args = ["vpncmd", "localhost", "/SERVER"]
    if hub:
        args.append("/HUB:DEFAULT")
    result = subprocess.run(
        args + ["/CMD"] + parts,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    # vpncmd echoes its arguments, so never include its output in CI artifacts.
    if result.returncode or "The command completed successfully." not in result.stdout:
        raise RuntimeError("reference setup failed: " + parts[0])


command(
    [
        "ServerCertSet",
        "/LOADCERT:/run/pl-reference.crt",
        "/LOADKEY:/run/pl-reference.key",
    ],
    False,
)
command(["SstpEnable", "yes"], False)
command(["LogDisable", "packet"])
command(["LogDisable", "security"])
command(["UserCreate", "vpn", "/GROUP:none", "/REALNAME:none", "/NOTE:none"])
command(["UserPasswordSet", "vpn", "/PASSWORD:" + secret])
command(["SecureNatHostSet", "/MAC:none", "/IP:172.30.252.1", "/MASK:255.255.255.0"])
command(
    [
        "DhcpSet",
        "/START:172.30.252.2",
        "/END:172.30.252.2",
        "/MASK:255.255.255.0",
        "/EXPIRE:3600",
        "/GW:172.30.252.1",
        "/DNS:1.1.1.1",
        "/DNS2:8.8.8.8",
        "/DOMAIN:none",
        "/LOG:no",
        "/PUSHROUTE:none",
    ]
)
command(["SecureNatEnable"])
command(["ServerPasswordSet", secrets.token_hex(24)], False)
der = ssl.PEM_cert_to_DER_cert(pathlib.Path("/run/pl-reference.crt").read_text())
pathlib.Path("/run/pl-reference.json").write_text(
    json.dumps(
        {
            "Address": "127.0.0.1:443",
            "Secret": secret,
            "Name": "vpn.example.com",
            "Pin": hashlib.sha256(der).hexdigest(),
        }
    )
)
result = subprocess.run(
    [
        "/run/reference.test",
        "-test.run",
        "TestOfficialSoftEtherSSTP",
        "-test.v",
        "-test.timeout",
        "45s",
    ],
    env={**os.environ, "PL_SSTP_REFERENCE": "/run/pl-reference.json"},
    check=False,
)
raise SystemExit(result.returncode)
