"""Render reviewable node files; this command never changes host networking."""

import argparse
import json
from pathlib import Path

from profiles import load, revision

ROOT = "/etc/prettylisa-profiles"


def unit(
    command: str,
    capabilities: str = "CAP_NET_ADMIN CAP_NET_BIND_SERVICE",
    user: str = "root",
) -> str:
    return f"""[Unit]
Description=PrettyLisaVPN connection profile
After=network-online.target prettylisa-profile-routing.service
Wants=network-online.target
Requires=prettylisa-profile-routing.service
[Service]
Type=simple
ExecStart={command}
Restart=on-failure
RestartSec=5
User={user}
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
CapabilityBoundingSet={capabilities}
AmbientCapabilities={capabilities if user != "root" else ""}
DevicePolicy=closed
DeviceAllow=/dev/net/tun rw
UMask=0077
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
"""


def render(m: dict) -> dict[str, str]:
    files = {"manifest.json": json.dumps(m, indent=2) + "\n"}
    public, egress = m["public_ipv4"], m["egress_interface"]
    # Additive, idempotent rules. No global policies, flushing, or SSH changes.
    routing = [
        "#!/bin/sh",
        "set -eu",
        "sysctl -w net.ipv4.ip_forward=1",
        'add() { table=$1; chain=$2; shift 2; iptables -w -t "$table" -C "$chain" "$@" 2>/dev/null || iptables -w -t "$table" -I "$chain" 1 "$@"; }',
    ]
    seen = set()
    for p in m["profiles"]:
        if not p["enabled"]:
            continue
        name, proto, iface = p["id"], p["protocol"], p["interface"]
        base = f"{ROOT}/{name}"
        routing.append(
            f"add filter INPUT -i {egress} -d {public} -p {p['transport'].lower()} --dport {p['port']} -m comment --comment pl-{name} -j ACCEPT"
        )
        if iface not in seen:
            seen.add(iface)
            routing.extend(
                [
                    f"add filter FORWARD -i {iface} -o {egress} -s {p['subnet']} -m comment --comment pl-{iface} -j ACCEPT",
                    f"add filter FORWARD -i {egress} -o {iface} -d {p['subnet']} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment pl-{iface} -j ACCEPT",
                    f"add nat POSTROUTING -s {p['subnet']} -o {egress} -m comment --comment pl-{iface} -j MASQUERADE",
                    # Refuse VPN access to node administration; Internet DNS is used.
                    f"add filter INPUT -i {iface} -m comment --comment pl-{iface} -j DROP",
                    f"ip link set dev {iface} mtu 1280 2>/dev/null || true",
                ]
            )
        if proto == "WIREGUARD":
            if p["obfuscation_mode"] == "NONE":
                # Existing wg0 and peer configuration must not be overwritten.
                continue
            files[
                f"{name}/environment"
            ] = f"""PRETTYLISA_OBFUSCATION_MODE=SIMPLE_PACKET_WRAPPER_V1
PRETTYLISA_OBFUSCATION_VERSION=1
PRETTYLISA_OBFUSCATION_BIND_HOST={public}
PRETTYLISA_OBFUSCATION_BIND_PORT={p["port"]}
PRETTYLISA_WIREGUARD_HOST=127.0.0.1
PRETTYLISA_WIREGUARD_PORT={p["upstream_port"]}
PRETTYLISA_MAX_DATAGRAM_SIZE=1400
"""
            files[f"prettylisa-profile-{name}.service"] = unit(
                "/opt/prettylisa-profiles/obfuscator/bin/python -m prettylisavpn_obfuscator.main",
                "CAP_NET_BIND_SERVICE",
                "nobody",
            ).replace("[Service]\n", f"[Service]\nEnvironmentFile={base}/environment\n")
        elif proto == "OPENVPN":
            wrapped = p["obfuscation_mode"] == "TLS_TRANSPORT"
            credentials = f"/run/credentials/prettylisa-profile-{name}.service"
            files[
                f"{name}/openvpn.conf"
            ] = f"""local {"127.0.0.1" if wrapped else public}
port {p["upstream_port"] if wrapped else p["port"]}
proto tcp-server
dev {iface}
dev-type tun
topology subnet
server {p["subnet"].split("/")[0]} {__import__("ipaddress").IPv4Network(p["subnet"]).netmask}
ca {credentials}/ca.crt
cert {credentials}/server.crt
key {credentials}/server.key
dh none
remote-cert-tls client
tls-version-min 1.3
data-ciphers AES-256-GCM
allow-compression no
tun-mtu 1280
mssfix 1200
push "redirect-gateway def1"
push "dhcp-option DNS {p["dns"][0]}"
keepalive 10 60
persist-key
persist-tun
verb 0
"""
            files[f"prettylisa-profile-{name}.service"] = unit(
                "/usr/sbin/openvpn --config %d/openvpn.conf",
                "CAP_NET_ADMIN CAP_NET_BIND_SERVICE",
                f"plvpn-{name}",
            ).replace(
                "[Service]\n",
                "[Service]\nDynamicUser=yes\n"
                + "".join(
                    f"LoadCredential={file}:{base}/{file}\n"
                    for file in ("openvpn.conf", "ca.crt", "server.crt", "server.key")
                ),
            )
            if wrapped:
                files[f"{name}/stunnel.conf"] = f"""foreground = yes
syslog = no
debug = emerg
sslVersionMin = TLSv1.3
cert = {base}/server.crt
key = {base}/server.key
CAfile = {base}/ca.crt
verifyChain = yes
[carrier]
accept = {public}:443
connect = 127.0.0.1:{p["upstream_port"]}
"""
                files[f"prettylisa-profile-{name}-tls.service"] = unit(
                    f"/usr/bin/stunnel4 {base}/stunnel.conf", "CAP_NET_BIND_SERVICE"
                )
        else:
            files[f"{name}/masque.json"] = (
                json.dumps(
                    {
                        "mode": "server",
                        "endpoint": f"{public}:443",
                        "server_name": p["server_name"],
                        "interface": iface,
                        "address": f"{p['gateway']}/{p['subnet'].split('/')[1]}",
                        "certificate": f"{base}/server.crt",
                        "private_key": f"{base}/server.key",
                        "ca": f"{base}/ca.crt",
                        "clients_file": f"{base}/clients.json",
                    },
                    indent=2,
                )
                + "\n"
            )
            files[f"prettylisa-profile-{name}.service"] = unit(
                f"/opt/prettylisa-profiles/masque {base}/masque.json"
            )
    files["routing.sh"] = "\n".join(routing) + "\n"
    files["prettylisa-profile-routing.service"] = f"""[Unit]
Description=PrettyLisaVPN additive forwarding and NAT
After=network-online.target ufw.service wg-quick@wg0.service
Before=prettylisa-profile-wg-simple.service
[Service]
Type=oneshot
ExecStart={ROOT}/routing.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
"""
    files["revision"] = revision(m) + "\n"
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("output")
    args = parser.parse_args()
    generated = render(load(args.manifest))
    output = Path(args.output)
    if output.exists() and any(
        str(path.relative_to(output)).replace("\\", "/") not in generated
        for path in output.rglob("*")
        if path.is_file()
    ):
        parser.error(
            "output contains obsolete or unrelated files; use a fresh staging directory"
        )
    for relative, content in generated.items():
        path = Path(args.output) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print("Rendered only; no system changes. Inspect routing.sh before deployment.")
