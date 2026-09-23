# Server profiles (Ubuntu 24.04)

This directory is an operator deployment/test boundary, independent of the desktop
UI. There is no fallback and no new Autopilot selection policy. A declaration,
listening socket, process start, and handshake do not demonstrate Internet access.

## Compatibility

| Protocol | Transport | Obfuscation | Security implementation |
|---|---|---|---|
| WireGuard | UDP, configured port | NONE | Linux WireGuard |
| WireGuard | UDP, configured port | SIMPLE_PACKET_WRAPPER_V1 | Linux WireGuard; wrapper is not cryptographic protection |
| OpenVPN | TCP 443 | NONE | Ubuntu OpenVPN, TLS >=1.3, AES-256-GCM |
| OpenVPN | TCP 443 | TLS_TRANSPORT | OpenVPN plus independent stunnel TLS >=1.3 carrier |
| MASQUE CONNECT-IP | UDP 443 | NONE | connect-ip-go v0.3.0, quic-go v0.62.0, Go TLS |

OpenVPN NONE and TLS_TRANSPORT cannot both listen on the same IP/TCP443.
MASQUE cannot share IP/UDP443 with an existing WireGuard/obfuscator listener.
Do not replace an existing listener without a separate reviewed cutover.
TLS transport is not a claim of browser-identical traffic. These versions are
pinned dependencies, not a claim of a version-specific security audit.

## Render and review

```
python server-profiles/render.py node.json /secure/staging/node
cat /secure/staging/node/routing.sh
```

`profiles.py` validates the exact matrix, port collisions, tunnel subnets and
physical-interface separation. `render.py` does not apply anything. Use a real
server certificate identity instead of `vpn.example.com` in the example.
Use a fresh staging directory when removing profiles. Rendering refuses obsolete
files. The deployment role refuses a changed installed manifest: archive it only
after reviewing and performing the corresponding service/firewall cutover.

Review every generated command before setting `vpn_profiles_apply=true`.
The Ansible role previews commands even in its default preview-only mode.
It adds narrow IPv4 listener/forwarding/NAT rules without flushing chains,
changing global policies, enabling UFW or changing SSH rules. VPN-to-node INPUT
is denied; DNS uses the configured external resolver through the tunnel.
Using a physical interface as a tunnel would lock out management and is rejected.
An existing firewall reload can remove these runtime rules: restart
`prettylisa-profile-routing.service` after a firewall reload. Do not reload UFW
or change host default routes as part of profile deployment.

WireGuard interface/key creation and peer provisioning remain with the existing
WireGuard role/node agent. This extension deliberately does not overwrite wg0,
restart it or remove existing peers. New nodes need that initial provisioning.

Provision certificates in `/etc/prettylisa-profiles/<id>/` before applying:
`ca.crt`, `server.crt`, `server.key` (root-only). OpenVPN requires clientAuth
certificates and a serverAuth server certificate. MASQUE requires mTLS and an
operator-owned SHA256 certificate fingerprint -> IPv4 mapping in `clients.json`.
An empty mapping denies every client. Each client gets one distinct IPv4;
concurrent use of one allocation is refused. Runtime configuration and private
keys must stay outside the repository. Never dump complete VPN configurations.

The mapping lives in the separate root-only `clients.json` referenced by
`clients_file`; rendering never replaces enrollment data. OpenVPN starts under a
systemd DynamicUser with only the two required network capabilities; private
material is passed with `LoadCredential`. The wrapper uses nobody, and stunnel
has only the bind capability. MASQUE retains root with restricted network
capabilities and systemd filesystem/device restrictions.

`bootstrap_test_pki.py` and `prepare_test_client.py` are explicit lab/operator
bootstrap tools, run as root on the node. They provision short-lived test client
certificates and a root-only bundle at `/etc/prettylisa-profiles/test-client`.
The CA private key and server private keys are never included in that bundle.
They are not an account credential issuance or renewal system. Move production
CA signing off-node and implement renewal/revocation before broader enrollment.
From a root-owned copy of this directory on the node:

```sh
python3 bootstrap_test_pki.py nodes/netcup.json
python3 prepare_test_client.py nodes/netcup.json
# Use nodes/nyc.json on NYC. After testing, remove only this test WireGuard peer:
wg pubkey < /etc/prettylisa-profiles/test-client/wireguard.key | xargs -r -I peerkey wg set wg0 peer peerkey remove
```

NYC uses the optional bounded `vpn_profiles_swap_mb: 512` because package setup
exhausted its 512 MB RAM; the default does not allocate swap.

Build `masque/` using Go 1.26 (`go test -race ./...`, `go vet ./...`,
`CGO_ENABLED=0 go build -trimpath -o masque .`). The adapter owns Linux TUN and
bounded per-client packet queues; the libraries own QUIC, HTTP/3, RFC 9484,
certificate validation and encryption. It does not implement cryptography.
IPv6 is intentionally unsupported. Only validated public IPv4 destinations are
forwarded by MASQUE, excluding node administration and private/link-local ranges.

## Independent verification

For each enabled profile, substitute its id, interface and actual port:

```
systemctl is-active prettylisa-profile-<id>.service
systemctl is-enabled prettylisa-profile-<id>.service
# Direct WireGuard instead uses:
systemctl is-active wg-quick@wg0.service
ss -H -lnut 'sport = :443'
journalctl -u prettylisa-profile-<id>.service -n 50 --no-pager
sysctl -n net.ipv4.ip_forward
ip -d link show <interface>
ip -4 route get 1.1.1.1
iptables -t nat -C POSTROUTING -s <subnet> -o <egress> -m comment --comment pl-<interface> -j MASQUERADE
iptables -C FORWARD -i <interface> -o <egress> -s <subnet> -m comment --comment pl-<interface> -j ACCEPT
```

To inspect packet arrival, use only an operator-controlled standalone test peer,
not production user traffic. Do not log DNS queries, browsing destinations or
packet payloads. A count-only capture (no pcap file/output) can distinguish
listener ingress from silence, e.g. `tcpdump -i eth0 -n -c 10 'host <test-runner-ip>
and udp port 443' >/dev/null` (interrupt once sufficient samples arrive).
Do not enable verbose OpenVPN or QUIC packet logs. The MASQUE adapter suppresses
upstream logs that may include packet addresses and emits closed diagnostic events.

On another VPS/region/ISP/trusted machine, build the probe Dockerfile and run a
container with `--cap-add NET_ADMIN --device /dev/net/tun`, **without host networking**.
Connect using a minimal standalone client with credentials mounted read-only:

* WireGuard NONE: `wg-quick up /run/secrets/wg0.conf`; confirm a recent handshake
  locally without publishing `wg show ... dump` (it includes secrets).
* SIMPLE_PACKET_WRAPPER_V1: run `wrapper_client.py <node-ip> <port>` with the
  existing `prettylisavpn_obfuscator` package available. Point the WireGuard peer
  endpoint to `127.0.0.1:51821`; preserve an eth0 host route to the real node IP.
* OpenVPN: `openvpn --config /run/secrets/client.ovpn`; use TCP client mode,
  `remote-cert-tls server`, explicit server identity, CA/client certificate/key,
  `tls-version-min 1.3`, `data-ciphers AES-256-GCM`, `allow-compression no`,
  `dev-type tun`, configured interface and `tun-mtu 1280`.
* TLS_TRANSPORT: start stunnel in client mode with mandatory `verifyChain=yes`,
  `checkHost=<certificate-identity>`, trusted CA and client certificate/key;
  connect its loopback accept port to the real node TCP443. Point OpenVPN to
  loopback, keeping the real node IP route on eth0. Do not disable verification.
* MASQUE: `prettylisa-masque /run/secrets/client.json` using mode=client, endpoint
  node-IP:443, certificate server_name, assigned address, interface, CA and client
  certificate/key paths. Install full-tunnel routes only inside the container,
  retaining a physical /32 route to the node endpoint. `tests/lab-probe.sh` shows
  the routing mechanics for the disposable local lab, not a host deployment script.

After checking the authenticated handshake, run:

```
python3 probe.py node.json <profile-id> health-endpoints.json --handshake-confirmed > result.json
```

Endpoints are a configurable JSON array, e.g. an operator-approved HTTPS public-IP
service with `url`, `expected_status: 200`, `egress_response: "plain_ip"`.
Multiple endpoints are supported; redirects and non-HTTPS URLs are not followed.
The probe resolves through the manifest DNS using a VPN-bound socket, pins that
resolved address for HTTPS, binds curl to the VPN interface, checks route selection
before/after, validates the HTTP status and public egress IP, and emits only a
bounded machine-readable report. This strict runner requires a public-egress
response; it fails closed if the network cannot exercise the profile. No ICMP is
used as a health check. Host network egress is not acceptable proof.

`--handshake-confirmed` is an explicit operator assertion, not an automatic
handshake detector. Only set it after inspecting the standalone protocol client.
JSON reports are trusted operator inputs, not cryptographic attestations.

Prefer the automated standalone runner, which checks WireGuard's recent handshake,
OpenVPN's local management state, or the MASQUE authenticated connection event:

```sh
# From repository root, after building masque/masque as above:
uv build --wheel --project vpn-obfuscator --out-dir server-profiles/runtime
docker build -t prettylisa-profile-probe server-profiles
docker run -d --name pl-external-test --cap-add NET_ADMIN --device /dev/net/tun \
  prettylisa-profile-probe
docker exec pl-external-test mkdir -m 0700 /run/secrets
# /secure/client-bundle must be transferred over authenticated SSH, never committed.
docker cp /secure/client-bundle/. pl-external-test:/run/secrets/
docker exec pl-external-test python3 /opt/probe/run_profile.py wg-direct > wg-direct.json
docker exec pl-external-test python3 /opt/probe/run_profile.py wg-simple > wg-simple.json
# Run only the variant enabled on this node:
docker exec pl-external-test python3 /opt/probe/run_profile.py ovpn > ovpn.json
docker exec pl-external-test python3 /opt/probe/run_profile.py ovpn-tls > ovpn-tls.json
docker exec pl-external-test python3 /opt/probe/run_profile.py masque > masque.json
docker rm -f pl-external-test
```

Each invocation connects exactly one profile and cleans up its routes/processes.
It exits nonzero on verification failure. Repeating an invocation tests reconnect.
The container owns its VPN routes; no API-host default route is changed. Results
include total DNS/HTTPS verification time (`latency_ms`), not packet RTT or an
isolated estimate of obfuscation overhead.

## Capability evidence

`export.py node.json result1.json ...` produces the backend import document.
The trusted backend operator runs:

```
python -m prettylisavpn.vpn_nodes.import_profiles deployment.json
```

Migration `0017_profile_evidence` adds separate `deployed_profiles` metadata.
Legacy `connection_profiles` declarations are not backfilled as verified evidence.
`VpnNode.verified_profiles(now)` requires enabled, E2E_VERIFIED, all successful
transport/tunnel/DNS/HTTPS/Internet/route checks, matching node/profile/configuration
revision and public egress. Import requires a report no older than 24 hours.
Stored evidence records a demonstrated revision; it is not a live connectivity
guarantee and does not silently disable working nodes the next day.
Reconfiguration or failed checks invalidate the projection. A service check must
only yield SERVER_READY; unit tests only UNIT_TESTED. Neither permits advertising
new runtime capabilities. The import command exposes no public write endpoint.
The existing session issuance path remains WireGuard-only and does not consume
TLS/QUIC declarations. New profile consumers must use `verified_profiles(now)`,
not legacy `connection_profiles` or the client capability catalog. No TLS/QUIC
account credential delivery or new selection policy is introduced here.
For explicitly migrated nodes, existing WireGuard sessions now return only the
verified raw UDP endpoint with obfuscation NONE, preventing legacy local NATIVE
settings from redirecting traffic to MASQUE's UDP/443. Failed/mismatched evidence
removes eligibility; an empty candidate list never restores NATIVE policy.
Unmigrated nodes retain their existing behavior. Older clients without candidate
negotiation need upgrading or an explicit matching local transport configuration.
Evidence import updates only the profile column, preserving concurrent health
updates. Evidence is trusted operator input: import a new test within 24 hours of
running it. Live node-health eligibility and the client's per-connection Internet
verification still apply. Retest after configuration changes or incidents. No
automatic external-test scheduler is installed.

## Verification limits

Unit tests and local Docker tests are not external-node E2E verification. Actual
node deployment and test results must be recorded separately, including time,
runner/network, enabled profile revision, stage booleans and failure code.
Missing network reachability remains UNTESTED/E2E_FAILED, never E2E_VERIFIED.
Client application packaging, TLS/QUIC session credential provisioning, other
platform bridges, IPv6 and automatic fallback are separate unsupported pieces.
The Chrome extension still needs a browser-only proxy implementation.

Primary implementation references:
- https://github.com/quic-go/connect-ip-go/tree/v0.3.0
- https://www.stunnel.org/manual.html
- https://openvpn.net/community-docs/community-articles/openvpn-2-6-manual.html
- https://git.zx2c4.com/wireguard-go/tree/tun/tun_linux.go
